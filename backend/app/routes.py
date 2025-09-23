# app/routes.py
from __future__ import annotations

import time
import hashlib
from uuid import uuid4
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .utils.text_cleaner import clean_answer, squash_whitespace
from .security import validate_input, load_policy
from .rate_limit import rate_limiter, init_rate_limiter
from .reranker import rerank
from .observability import (
    REQUEST_COUNT, REQUEST_LATENCY,
    CACHE_REQUESTS, CACHE_RESULTS,
    RETRIEVAL_LATENCY, LLM_LATENCY, ERROR_COUNT,
    RERANK_LATENCY, record_throttle
)
from .cache import result_cache
from .config import settings
from . import retrieval, llm

router = APIRouter()
_ROUTE = "/ask"

# 啟動時載入 policy 並初始化速率限制
_POLICY = load_policy()
init_rate_limiter(_POLICY)

# ----------------- helpers -----------------
def _ids(req: Request, payload: dict):
    user = (payload.get("user") or {})
    return {
        "user_id": user.get("id") or "",
        "user_role": user.get("role") or "guest",
        "ip": (req.client.host if req and req.client else "0.0.0.0"),
    }

def _error_response(status: int, meta_type: str, req_id: str, policy_version: str, retry_after: int | None = None):
    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return JSONResponse(
        status_code=status,
        content={
            "error": "invalid_input",
            "message": "Input rejected by policy.",
            "meta": {
                "type": meta_type,
                "redacted": True,
                "policy_version": policy_version,
                "request_id": req_id,
            },
        },
        headers=headers,
    )


def _cache_key_for_query(query: str) -> str:
    base = f"{query}|{settings.top_k}|{settings.chat_model}|{settings.rerank_model}"
    return "ask:" + hashlib.sha256(base.encode("utf-8")).hexdigest()

def _skip_rate_limit() -> bool:
    # 若設定檔宣告 env=test，或顯式 disable_rate_limit=True，則跳過
    return getattr(settings, "env", "") == "test" or getattr(settings, "disable_rate_limit", False)

def _rate_limit_guard(ip: str, user_id: str, req_id: str):
    rl = rate_limiter.check(ip=ip, user_id=user_id)
    if not rl.allowed:
        record_throttle(rl.scope or "ip")
        raise _ThrottleError(retry_after=rl.retry_after_sec or 1, req_id=req_id)

def _validate_guard(query: str, user_role: str) -> str:
    v = validate_input(query, user_role=user_role, content_type="text/plain")
    if not v.ok:
        raise _PolicyError(http_status=(403 if v.type == "role" else 400), meta_type=(v.type or "format"), policy_version=(v.policy_version or ""))
    return v.policy_version or ""

def _lookup_cache(query: str) -> Dict[str, Any] | None:
    CACHE_REQUESTS.labels(route=_ROUTE).inc()
    ck = _cache_key_for_query(query)
    cached = result_cache.get(ck)
    if cached:
        CACHE_RESULTS.labels(route=_ROUTE, result="hit").inc()
        return cached
    CACHE_RESULTS.labels(route=_ROUTE, result="miss").inc()
    return None

def _retrieve_candidates(query: str, candidate_k: int) -> List[Dict[str, Any]]:
    t0 = time.time()
    cands = retrieval.retrieve_topk(query, candidate_k)
    RETRIEVAL_LATENCY.observe(time.time() - t0)
    return cands

def _rerank_candidates(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    t0 = time.time()
    try:
        topk = rerank(query, cands)
    except Exception:
        ERROR_COUNT.labels(stage="rerank").inc()
        topk = cands[:settings.top_k]
    finally:
        RERANK_LATENCY.observe(time.time() - t0)
    return topk

def _answer_with_context(query: str, topk: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any], str]:
    context = retrieval.build_context(topk, settings.max_context_chars)
    t0 = time.time()
    out = llm.answer_with_context(query, context)
    LLM_LATENCY.labels(model=settings.chat_model).observe(time.time() - t0)
    return out["text"], out, context

def _write_cache(query: str, payload: Dict[str, Any]):
    ck = _cache_key_for_query(query)
    result_cache.set(ck, payload)
    CACHE_RESULTS.labels(route=_ROUTE, result="write").inc()


# ----------------- custom exceptions -----------------
class _PolicyError(Exception):
    def __init__(self, http_status: int, meta_type: str, policy_version: str):
        self.http_status = http_status
        self.meta_type = meta_type
        self.policy_version = policy_version

class _ThrottleError(Exception):
    def __init__(self, retry_after: int, req_id: str):
        self.retry_after = retry_after
        self.req_id = req_id



# ----------------- route -----------------

@router.post(_ROUTE)
async def ask(req: Request):
    t0 = time.time()
    status = "success"
    req_id = str(uuid4())

    try:
        data = await req.json()
        query = (data.get("query") or "").strip()

        # 空字串 → 統一錯誤格式（type=length）
        if not query:
            REQUEST_COUNT.labels(route=_ROUTE, status="error").inc()
            ERROR_COUNT.labels(stage="route").inc()
            return _error_response(400, "length", req_id, _POLICY.get("policy_version", ""))

        ids = _ids(req, data)

        # 速率限制
        try:
            _rate_limit_guard(ids["ip"], ids["user_id"], req_id)
        except _ThrottleError as th:
            return _error_response(429, "rate_limit", th.req_id, _POLICY.get("policy_version", ""), th.retry_after)

        # 輸入限制（policy）
        try:
            policy_version = _validate_guard(query, ids["user_role"])
        except _PolicyError as pe:
            return _error_response(pe.http_status, pe.meta_type, req_id, pe.policy_version)

        # 快取
        cached = _lookup_cache(query)
        if cached:
            meta = {**cached.get("meta", {}), "cached": True, "policy_version": policy_version, "request_id": req_id}
            return {"answer": cached["answer"], "meta": meta}

        # 檢索 → 重排 → LLM
        candidate_k = max(settings.top_k * 4, 20)
        cands = _retrieve_candidates(query, candidate_k)
        topk = _rerank_candidates(query, cands)
        answer_text, out, context = _answer_with_context(query, topk)
        answer_text = clean_answer(
            answer_text,
            single_line=getattr(settings, "answer_single_line", False)
        )
        payload = {
            "answer": answer_text,
            "meta": {
                "cached": False,
                "context_preview": squash_whitespace(context)[:240],
                "sources": [
                    {
                        "id": c["id"],
                        "title": c["title"],
                        "source": c["source"],
                        "score": c["score"],
                        "reranker_score": c.get("reranker_score"),
                    } for c in topk
                ],
                "usage": out["usage"],
                "cost_usd": out["cost_usd"],
                "rerank_model": settings.rerank_model,
                "top_k": settings.top_k,
                "policy_version": policy_version,
                "request_id": req_id,
            },
        }

        _write_cache(query, payload)
        return payload

    except Exception:
        status = "error"
        ERROR_COUNT.labels(stage="route").inc()
        raise
    finally:
        REQUEST_COUNT.labels(route=_ROUTE, status=status).inc()
        REQUEST_LATENCY.labels(route=_ROUTE).observe(time.time() - t0)