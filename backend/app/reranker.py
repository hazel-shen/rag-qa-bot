# app/reranker.py
from typing import List, Dict
import os, time, logging, torch
from sentence_transformers import CrossEncoder
from .config import settings
from .observability import RERANK_LATENCY, ERROR_COUNT

log = logging.getLogger(__name__)

# 單例 CrossEncoder，避免每次請求重建模型
_CE = CrossEncoder(settings.rerank_model)
_MAX_LEN = int(os.getenv("RERANK_MAX_CHARS", "1000"))
_BATCH   = int(os.getenv("RERANK_BATCH", "16"))

def rerank(query: str, cands: List[Dict]) -> List[Dict]:
    """
    使用本地 Reranker 模型 BAAI/bge-reranker-v2-m3 
    回傳帶有 reranker_score 的候選文件。
    """
    t0 = time.time()
    try:
        if not cands:
            return []

        # 文字截斷，轉字串避免 None
        pairs = [(query, str(c.get("text", ""))[:_MAX_LEN]) for c in cands]

        with torch.inference_mode():
            scores = _CE.predict(pairs, batch_size=_BATCH, num_workers=0)

        # 統一轉成 list（支援 torch.Tensor / numpy.ndarray / list / tuple）
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        elif isinstance(scores, (list, tuple)):
            scores = list(scores)
        else:
            try:
                import numpy as _np
                scores = _np.asarray(scores).tolist()
            except Exception:
                scores = [float(s) for s in scores]

        k = min(settings.top_k or settings.rerank_top_k, len(cands))
        idxs = sorted(range(len(cands)), key=lambda i: -scores[i])[:k]

        ranked = [{**cands[i], "reranker_score": float(scores[i])} for i in idxs]
        return ranked

    except Exception as e:
        ERROR_COUNT.labels(stage="rerank").inc()
        log.exception("Local rerank failed: %s", e)
        out = []
        for c in cands[: (settings.top_k or settings.rerank_top_k)]:
            cc = dict(c)
            cc.setdefault("reranker_score", None)
            out.append(cc)
        return out
    finally:
        RERANK_LATENCY.observe(time.time() - t0)
