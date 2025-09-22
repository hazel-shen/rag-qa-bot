# app/ingest/cli_ingest.py
"""
用法：
  python -m app.ingest.cli_ingest \
    --input backend/data/raw \
    --out backend/data/clean/chunks.jsonl
"""
import argparse, os, json
from tqdm import tqdm
from .loaders import iter_raw_docs
from .cleaning import basic_clean
from .chunking import split_paragraphs, chunk_by_chars, to_records

def run(input_dir: str, out_path: str, max_chars=800, overlap=120):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    total = 0
    with open(out_path, "w", encoding="utf-8") as w:
        for rd in tqdm(iter_raw_docs(input_dir), desc="Ingest"):
            cleaned = basic_clean(rd.text)
            paras = split_paragraphs(cleaned)
            chunks = chunk_by_chars(paras, max_chars=max_chars, overlap=overlap)
            recs = to_records(chunks, title=rd.title, source=rd.path)
            for r in recs:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1
    print(f"✅ 輸出 {total} 個 chunks → {out_path}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="原始文件目錄，例如 backend/data/raw")
    ap.add_argument("--out", required=True, help="輸出 chunks.jsonl 路徑")
    ap.add_argument("--max_chars", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=120)
    args = ap.parse_args()
    run(args.input, args.out, args.max_chars, args.overlap)

if __name__ == "__main__":
    main()
