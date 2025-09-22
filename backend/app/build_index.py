# app/build_index.py
import os, json, uuid, re, glob, argparse
import numpy as np
import faiss
from openai import OpenAI
from .config import settings
from .ingest.cleaning import basic_clean  # 若走 docs 模式時仍可用
from .ingest.chunking import split_paragraphs, chunk_by_chars

client = OpenAI(api_key=settings.openai_api_key or None)

def embed(texts):
    resp = client.embeddings.create(model=settings.embed_model, input=texts)
    vecs = np.array([d.embedding for d in resp.data], dtype="float32")
    faiss.normalize_L2(vecs)
    return vecs

def build_from_chunks(chunks_path: str):
    metas, chunks = [], []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            metas.append(o)
            chunks.append(o["text"])
    X = embed(chunks)
    index = faiss.IndexFlatIP(X.shape[1])
    index.add(X)
    faiss.write_index(index, settings.index_path)
    with open(settings.docstore_path, "w", encoding="utf-8") as w:
        for m in metas:
            w.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"✅ 由 chunks 建索引：{settings.index_path} ; docstore：{settings.docstore_path} ; 向量數：{len(metas)}")

def build_from_docs(doc_dir: str):
    # 舊路徑兼容：讀 docs/ 下 txt/md，內建簡單切片
    paths = glob.glob(os.path.join(doc_dir, "**/*"), recursive=True)
    metas, chunks = [], []
    for p in paths:
        if os.path.isdir(p): continue
        if not any(p.lower().endswith(ext) for ext in (".txt", ".md")): continue
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        cleaned = basic_clean(raw)
        paras = split_paragraphs(cleaned)
        for idx, ch in enumerate(chunk_by_chars(paras, max_chars=800, overlap=120)):
            metas.append({"id": f"{p}::chunk-{idx}", "title": os.path.basename(p), "text": ch, "source": p})
            chunks.append(ch)
    X = embed(chunks)
    index = faiss.IndexFlatIP(X.shape[1])
    index.add(X)
    faiss.write_index(index, settings.index_path)
    with open(settings.docstore_path, "w", encoding="utf-8") as w:
        for m in metas:
            w.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"✅ 由 docs 建索引：{settings.index_path} ; docstore：{settings.docstore_path} ; 向量數：{len(metas)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", help="chunks.jsonl 路徑（優先）")
    ap.add_argument("--docs", help="舊模式：純 txt/md 目錄")
    args = ap.parse_args()
    if args.chunks:
        build_from_chunks(args.chunks)
    else:
        doc_dir = args.docs or os.path.join(settings.data_dir, "docs")
        build_from_docs(doc_dir)

if __name__ == "__main__":
    main()
