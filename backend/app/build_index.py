# app/build_index.py
from __future__ import annotations
import argparse, json, hashlib, os
from pathlib import Path

# Optional deps: 都缺也要能成功退出
try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    import faiss  # type: ignore
except Exception:
    faiss = None  # type: ignore

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

from .config import settings
from .ingest.cleaning import basic_clean
from .ingest.chunking import split_paragraphs, chunk_by_chars


# ---------- Small utilities (無分支或最小分支) ----------

def stable_embed_many(texts: list[str], dim: int) -> list:
    """離線穩定假嵌入；無 numpy 時回傳空 list（上層寫占位 index）"""
    if np is None:
        return []
    out = []
    for t in texts:
        h = hashlib.sha256((t or "").encode("utf-8")).digest()
        seed = int.from_bytes(h[:8], "big") & 0xFFFFFFFF
        v = np.random.default_rng(seed).standard_normal(dim)
        out.append((v / (np.linalg.norm(v) + 1e-9)).astype("float32"))
    return out

def openai_embed_many(texts: list[str], model: str) -> list | None:
    """有套件與金鑰才嘗試；任何失敗回 None（交給 fallback）。"""
    api_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
    if not (OpenAI and api_key and np is not None):
        return None
    try:
        client = OpenAI(api_key=api_key)
        out = []
        for t in texts:
            emb = client.embeddings.create(model=model, input=t).data[0].embedding
            v = np.asarray(emb, dtype="float32")
            out.append(v / (np.linalg.norm(v) + 1e-9))
        return out
    except Exception:
        return None

def get_embedder(model: str, dim: int):
    """回傳一個 callable：texts -> vectors（自動選 OpenAI 或穩定假嵌入）"""
    def _fn(texts: list[str]) -> list:
        vecs = openai_embed_many(texts, model)
        return vecs if vecs else stable_embed_many(texts, dim)
    return _fn

def write_index(index_path: Path, vecs: list) -> None:
    """有 faiss + numpy + 向量才寫真索引；否則寫占位檔。"""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if faiss and np is not None and vecs:
        X = np.vstack(vecs).astype("float32")
        idx = faiss.IndexFlatIP(X.shape[1]); idx.add(X)
        faiss.write_index(idx, str(index_path))
        return
    index_path.write_bytes(b"FAISS_NOT_AVAILABLE_OR_EMPTY")

def write_docstore(docstore_path: Path, metas: list[dict]) -> None:
    docstore_path.parent.mkdir(parents=True, exist_ok=True)
    with docstore_path.open("w", encoding="utf-8") as w:
        for m in metas:
            w.write(json.dumps(m, ensure_ascii=False) + "\n")

def read_chunks_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    """每行 JSON（至少含 text）或純文字行容錯為 {'text': line}。"""
    metas, texts = [], []
    for s in path.read_text(encoding="utf-8").splitlines():
        s = s.strip()
        if not s: 
            continue
        try:
            obj = json.loads(s)
            txt = obj.get("text", "")
            metas.append(obj); texts.append(txt if isinstance(txt, str) else str(txt))
        except Exception:
            metas.append({"id": None, "title": "", "text": s, "source": str(path)})
            texts.append(s)
    return metas, texts

def build_from_docs(doc_dir: Path, max_chars=800, overlap=120) -> tuple[list[dict], list[str]]:
    """舊模式：僅 .txt/.md，做清洗與切片。"""
    metas, texts = [], []
    for p in doc_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".txt", ".md"}:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            paras = split_paragraphs(basic_clean(raw))
            for i, ch in enumerate(chunk_by_chars(paras, max_chars=max_chars, overlap=overlap)):
                metas.append({"id": f"{p}::chunk-{i}", "title": p.name, "text": ch, "source": str(p)})
                texts.append(ch)
    return metas, texts


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", help="chunks.jsonl 路徑（優先）")
    ap.add_argument("--docs", help="舊模式：純 txt/md 目錄")
    ap.add_argument("--docstore", help="輸出 docstore.jsonl；未提供則用 settings")
    ap.add_argument("--index", help="輸出 index.faiss；未提供則用 settings")
    ap.add_argument("--embedding-model", default="text-embedding-3-small")
    ap.add_argument("--dim", type=int, default=384, help="無 OpenAI 時之假嵌入維度")
    args = ap.parse_args()

    docstore_path = Path(args.docstore) if args.docstore else Path(settings.docstore_path)
    index_path    = Path(args.index)    if args.index    else Path(settings.index_path)

    # 來源：chunks 優先，否則 docs（維持最少分支）
    if args.chunks:
        metas, texts = read_chunks_jsonl(Path(args.chunks))
    else:
        doc_dir = Path(args.docs) if args.docs else Path(getattr(settings, "data_dir", ".")) / "docs"
        metas, texts = build_from_docs(doc_dir)

    embed = get_embedder(args.embedding_model, args.dim)
    vecs  = embed(texts)

    write_docstore(docstore_path, metas)
    write_index(index_path, vecs)

    print(
        f"✅ build_index: docstore={docstore_path} index={index_path} "
        f"chunks={len(metas)} openai={'yes' if (OpenAI and (os.environ.get('OPENAI_API_KEY') or getattr(settings,'openai_api_key',None))) else 'no'} "
        f"faiss={'yes' if faiss else 'no'}"
    )

if __name__ == "__main__":
    main()
