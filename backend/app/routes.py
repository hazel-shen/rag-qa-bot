# app/routes.py
from fastapi import APIRouter, Request
import time, hashlib
from .security import validate_query
from .reranker import rerank 
from .observability import (
    REQUEST_COUNT, REQUEST_LATENCY,
    CACHE_REQUESTS, CACHE_RESULTS,
    RETRIEVAL_LATENCY, LLM_LATENCY, ERROR_COUNT,
    RERANK_LATENCY
)
from .cache import result_cache
from .config import settings
from . import retrieval, llm

router = APIRouter()

def _cache_key_for_query(query: str) -> str:
    base = f"{query}|{settings.top_k}|{settings.chat_model}|{settings.rerank_model}"
    return "ask:" + hashlib.sha256(base.encode("utf-8")).hexdigest()


@router.post("/ask")
async def ask(req: Request):
    data = await req.json()
    query = (data.get("query") or "").strip()

    # 簡單的空字串保護
    if not query:
        REQUEST_COUNT.labels(route="/ask", status="error").inc()
        ERROR_COUNT.labels(stage="route").inc()
        return {"error": "query must not be empty"}
    
    validate_query(query)
    

    t0 = time.time()
    status = "success"
    try:
        # 1) 查快取
        CACHE_REQUESTS.labels(route="/ask").inc()
        ck = _cache_key_for_query(query)
        cached = result_cache.get(ck)
        if cached:
            CACHE_RESULTS.labels(route="/ask", result="hit").inc()
            return {"answer": cached["answer"], "meta": {**cached["meta"], "cached": True}}
        else:
            CACHE_RESULTS.labels(route="/ask", result="miss").inc()

        # 2) 檢索（量測 FAISS 延遲；embedding 延遲在 retrieval.py）

        # 2-1) 先從向量庫取「較大的候選集合」（例如 k 的 3~5 倍，至少 20）
        candidate_k = max(settings.top_k * 4, 20) # 粗選 20 個
        t_ret = time.time()
        cands = retrieval.retrieve_topk(query, candidate_k) 
        RETRIEVAL_LATENCY.observe(time.time() - t_ret)

        # 2-2) 呼叫 OpenAI Reranker，取最終要餵給 LLM 的 top_k
        t_rer = time.time()
        try:
            topk = rerank(query, cands)
        except Exception:
            ERROR_COUNT.labels(stage="rerank").inc()
            topk = cands[:settings.top_k]
        finally:
            RERANK_LATENCY.observe(time.time() - t_rer)

        # 2-3) 組裝 context
        context = retrieval.build_context(topk, settings.max_context_chars)

        # 3) LLM（量測 LLM 延遲）
        t_llm = time.time()
        out = llm.answer_with_context(query, context)
        LLM_LATENCY.labels(model=settings.chat_model).observe(time.time() - t_llm)

        answer = out["text"]
        payload = {
            "answer": answer,
            "meta": {
                "cached": False,
                "context_preview": context[:240],
                "sources": [
                    {
                        "id": c["id"], 
                        "title": c["title"], 
                        "source": c["source"], 
                        "score": c["score"], 
                        "reranker_score": c.get("reranker_score")
                    } for c in topk
                ],
                "usage": out["usage"],
                "cost_usd": out["cost_usd"],
                "rerank_model": settings.rerank_model,
                "top_k": settings.top_k
            }
        }

        # 4) 寫入快取
        result_cache.set(ck, payload)
        CACHE_RESULTS.labels(route="/ask", result="write").inc()

        return payload

    except Exception:
        status = "error"
        ERROR_COUNT.labels(stage="route").inc()
        raise
    finally:
        REQUEST_COUNT.labels(route="/ask", status=status).inc()
        REQUEST_LATENCY.labels(route="/ask").observe(time.time() - t0)