# app/reranker.py
from typing import List, Dict
import time
from openai import OpenAI
from .config import settings
from .observability import RERANK_LATENCY, ERROR_COUNT

_client = OpenAI(api_key=settings.openai_api_key or None)

def rerank(query: str, cands: List[Dict]) -> List[Dict]:
    """
    使用 OpenAI Reranker API (gpt-4o-mini-rerank) 對候選文件重新排序
    - 若 API 出錯，回退到原始的前 top_k
    """
    t0 = time.time()
    try:
        if not cands:
            return []

        resp = _client.rerank.create(
            model=settings.rerank_model or "gpt-4o-mini-rerank",
            query=query,
            documents=[c["text"] for c in cands],
            top_n=settings.top_k,
        )

        # OpenAI 回傳的是已排序的 documents
        id2cand = {i: c for i, c in enumerate(cands)}
        ranked = []
        for item in resp.data:
            doc = id2cand[item.index]
            ranked.append({
                **doc,
                "reranker_score": item.score,
            })

        return ranked
    except Exception:
        ERROR_COUNT.labels(stage="rerank").inc()
        # fallback: 用原本的前 top_k
        return cands[:settings.top_k]
    finally:
        RERANK_LATENCY.observe(time.time() - t0)
