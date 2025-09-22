# app/retrieval.py
from typing import List, Dict, Any, Tuple
import json, os
import numpy as np
import faiss
from openai import OpenAI
from .config import settings
from .observability import EMBEDDING_LATENCY, ERROR_COUNT
import time

_client = None
_index = None
_idmap: List[str] = []
_meta: Dict[str, Dict[str, Any]] = {}

def _client_lazy() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key or None)
    return _client

def load_index() -> None:
    """載入 FAISS index 與對應的文件中繼資料"""
    global _index, _idmap, _meta
    if _index is not None:
        return
    if not os.path.exists(settings.index_path):
        raise RuntimeError(f"FAISS index not found: {settings.index_path}. 請先執行 build_index.py")
    if not os.path.exists(settings.docstore_path):
        raise RuntimeError(f"Docstore not found: {settings.docstore_path}. 請先執行 build_index.py")

    _index = faiss.read_index(settings.index_path)

    # 讀 docstore（jsonl：每行 {id, text, title, source}）
    _idmap = []
    _meta = {}
    with open(settings.docstore_path, "r", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            _idmap.append(o["id"])
            _meta[o["id"]] = {
                "title": o.get("title", f"doc-{o['id']}"),
                "text": o.get("text", ""),
                "source": o.get("source", ""),
            }

def embed_text(texts: List[str]) -> np.ndarray:
    """OpenAI Embeddings → numpy array (L2 normalized)"""
    t0 = time.time()
    try:
        client = _client_lazy()
        resp = client.embeddings.create(model=settings.embed_model, input=texts)
    except Exception:
        ERROR_COUNT.labels(stage="embedding").inc()
        raise
    finally:
        EMBEDDING_LATENCY.labels(stage="query" if len(texts) == 1 else "chunks").observe(time.time() - t0)

    vecs = np.array([d.embedding for d in resp.data], dtype="float32")
    faiss.normalize_L2(vecs)
    return vecs

def search(query: str, k: int) -> List[Tuple[str, float]]:
    load_index()
    qv = embed_text([query])
    D, I = _index.search(qv, k)
    ids_scores: List[Tuple[str, float]] = []
    for idx, score in zip(I[0].tolist(), D[0].tolist()):
        if idx == -1: 
            continue
        doc_id = _idmap[idx]
        ids_scores.append((doc_id, float(score)))
    return ids_scores

def retrieve_topk(query: str, k: int) -> List[Dict[str, Any]]:
    ids_scores = search(query, k)
    results = []
    for doc_id, score in ids_scores:
        m = _meta[doc_id]
        results.append({
            "id": doc_id,
            "title": m["title"],
            "text": m["text"],
            "source": m["source"],
            "score": score,
        })
    return results

def build_context(chunks: List[Dict[str, Any]], max_chars: int) -> str:
    pieces, total = [], 0
    for c in chunks:
        t = f"[{c['title']}] {c['text']} (source: {c['source']})"
        if total + len(t) > max_chars: 
            break
        pieces.append(t); total += len(t)
    return "\n---\n".join(pieces)
