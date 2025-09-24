# app/ingest/cli_ingest.py
"""
用法：
  # 目錄模式（建議；會輸出到 <out>/clean/chunks.jsonl）
  python -m app.ingest.cli_ingest --input backend/data/raw --out backend/data \
    --max_chars 500 --overlap 50

  # 檔案模式（向後相容；直寫到 .jsonl）
  python -m app.ingest.cli_ingest --input backend/data/raw \
    --out backend/data/clean/chunks.jsonl
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Iterable

from tqdm import tqdm

from .loaders import iter_raw_docs
from .cleaning import basic_clean
from .chunking import split_paragraphs, chunk_by_chars, to_records


def _fallback_iter_files(input_dir: str) -> Iterable:
    """
    保險掃描：當 iter_raw_docs 無產出時，撿常見文字格式（.txt/.md/.html）。
    你已經有 pdf/docx 的 loader，就不在 fallback 處理，避免額外依賴。
    """
    import re
    try:
        from bs4 import BeautifulSoup  # type: ignore
        has_bs4 = True
    except Exception:
        has_bs4 = False
        BeautifulSoup = None  # type: ignore

    for p in Path(input_dir).rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in {".txt", ".md", ".html", ".htm"}:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if ext in {".html", ".htm"}:
            if has_bs4 and BeautifulSoup is not None:
                text = BeautifulSoup(raw, "html.parser").get_text(" ")
            else:
                text = re.sub(r"<[^>]+>", " ", raw)
        else:
            text = raw
        yield type("RawDoc", (), {"path": str(p), "title": p.name, "text": text})


def run(
    input_dir: str,
    out_arg: str,
    max_chars: int = 800,
    overlap: int = 120,
    keep_clean_txt: bool = True,
    verbose: bool = True,
    enable_fallback: bool = False,
) -> Path:
    in_dir = Path(input_dir).resolve()
    if not in_dir.exists():
        raise FileNotFoundError(f"[ingest] input_dir not found: {in_dir}\nCWD={os.getcwd()}")

    out_path = Path(out_arg)

    # 模式判斷：檔案（舊）/ 目錄（新）
    if out_path.suffix.lower() == ".jsonl":
        # 檔案模式：直接寫到指定檔案
        chunks_path = out_path.resolve()
        clean_dir = chunks_path.parent
        clean_dir.mkdir(parents=True, exist_ok=True)
        mode = "file"
    else:
        # 目錄模式：寫到 <out>/clean/chunks.jsonl
        root_dir = out_path.resolve()
        clean_dir = root_dir / "clean"
        chunks_path = clean_dir / "chunks.jsonl"
        clean_dir.mkdir(parents=True, exist_ok=True)
        mode = "dir"

    # 主要使用你的自訂 loader
    docs = list(iter_raw_docs(str(in_dir)))

    if verbose:
        cnt = Counter(Path(getattr(d, "path", "")).suffix.lower() for d in docs)
        print(f"[ingest] CWD={os.getcwd()}")
        print(f"[ingest] input_dir={in_dir} (exists={in_dir.exists()})")
        print(f"[ingest] output={chunks_path} (mode={mode})")
        print(f"[ingest] loader found {len(docs)} docs by ext: {dict(cnt)}")

    used_fallback = False
    if not docs and enable_fallback:
        used_fallback = True
        if verbose:
            print("[ingest] loader returned 0 docs -> enable fallback scan for .txt/.md/.html")
        docs = list(_fallback_iter_files(str(in_dir)))
        if verbose:
            print(f"[ingest] fallback found {len(docs)} docs")

    if not docs:
        raise RuntimeError(
            f"[ingest] no documents found under: {in_dir}\n"
            f"         (CWD={os.getcwd()}). Check your working directory or path."
        )

    total = 0
    with open(chunks_path, "w", encoding="utf-8") as w:
        for rd in tqdm(docs, desc="Ingest"):
            cleaned = basic_clean(getattr(rd, "text", "") or "")

            if keep_clean_txt:
                fname = Path(getattr(rd, "path", "doc.txt")).name or "doc.txt"
                txt_path = (clean_dir / fname).with_suffix(".txt")
                txt_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    txt_path.write_text(cleaned, encoding="utf-8")
                except Exception:
                    # 不讓個別寫檔失敗中斷整體流程
                    pass

            paras = split_paragraphs(cleaned)
            chunks = chunk_by_chars(paras, max_chars=max_chars, overlap=overlap)
            for r in to_records(chunks, title=getattr(rd, "title", ""), source=getattr(rd, "path", "")):
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1

    if verbose:
        fb_msg = " + fallback" if used_fallback else ""
        msg = "目錄模式（<out>/clean/chunks.jsonl）" if mode == "dir" else "檔案模式（直寫 .jsonl）"
        print(f"✅ Ingest 完成：{msg}{fb_msg}，共 {total} 個 chunks → {chunks_path}")

    return chunks_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="原始文件目錄，例如 backend/data/raw")
    ap.add_argument("--out", required=True, help="輸出位置：可為 <目錄> 或 <chunks.jsonl 檔案>")
    ap.add_argument("--max_chars", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=120)
    ap.add_argument("--no_keep_clean_txt", action="store_true", help="不輸出清洗後 .txt（降低 I/O）")
    ap.add_argument("--quiet", action="store_true", help="安靜模式（減少日誌）")
    ap.add_argument("--fallback", action="store_true", help="若 loader 無產出，啟用簡易掃描 .txt/.md/.html")
    args = ap.parse_args()

    run(
        input_dir=args.input,
        out_arg=args.out,
        max_chars=args.max_chars,
        overlap=args.overlap,
        keep_clean_txt=not args.no_keep_clean_txt,
        verbose=not args.quiet,
        enable_fallback=args.fallback,
    )


if __name__ == "__main__":
    main()
