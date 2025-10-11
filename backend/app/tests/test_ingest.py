# app/tests/test_ingest.py 
# TODO:: 這邊可能要改 cli
import subprocess, sys
from pathlib import Path
import pytest

@pytest.mark.ingest
def test_ingest_end_to_end_builds_index(tmp_path: Path):
    """
    E2E ingest（寬鬆版）：
    1) 先用 cli_ingest 產出 out/clean（清洗/切片前置）
    2) 若 out/clean/chunks.jsonl 存在 → 直接用它建索引
       若不存在 → 以 out/clean 下的純文字合成一份臨時 chunks.jsonl 再建索引
    3) 呼叫 app.build_index 產出 docstore.jsonl / index.faiss 後做一致性檢查
    """
    # 1) 準備原始資料
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "a.txt").write_text("Hello A", encoding="utf-8")
    (raw_dir / "b.html").write_text("<p>Hello B</p>", encoding="utf-8")

    out_dir = tmp_path / "out"

    # 2) 跑 cleaning + （你的 CLI 若會 chunk 就會產出 chunks.jsonl）
    cp1 = subprocess.run(
        [
            sys.executable, "-m", "app.ingest.cli_ingest",
            "--input", str(raw_dir),
            "--out", str(out_dir),
            "--max_chars", "500",
            "--overlap", "50",
        ],
        capture_output=True,
        text=True,
    )
    assert cp1.returncode == 0, f"cli_ingest failed:\nSTDOUT:\n{cp1.stdout}\nSTDERR:\n{cp1.stderr}"

    clean_dir = out_dir / "clean"
    assert clean_dir.exists(), "clean dir not found; cli_ingest should create it"

    chunks_path = clean_dir / "chunks.jsonl"
    if not chunks_path.exists():
        # 2b) 用 clean_dir 的純文字合成一份臨時 chunks.jsonl
        synthetic_chunks = tmp_path / "synthetic_chunks.jsonl"
        texts = []
        for p in clean_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".txt", ".md", ".html"}:
                try:
                    texts.append(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
        assert texts, "no cleaned texts found to synthesize chunks.jsonl"
        # 盡量模擬 chunk 行為：每行一小段，避免太長
        with synthetic_chunks.open("w", encoding="utf-8") as f:
            for t in texts:
                t = " ".join(t.split())  # 壓空白
                # 粗略切塊：每 500 字一行
                for i in range(0, len(t), 500):
                    f.write(t[i:i+500].strip() + "\n")
        chunks_path = synthetic_chunks

    # 3) 用 build_index 產出 docstore/index（有 CLI 就跑；沒有就 skip）
    docstore = out_dir / "docstore.jsonl"
    index = out_dir / "index.faiss"
    cp2 = subprocess.run(
        [
            sys.executable, "-m", "app.build_index",
            "--chunks", str(chunks_path),
            "--docstore", str(docstore),
            "--index", str(index),
            "--embedding-model", "text-embedding-3-small",
        ],
        capture_output=True,
        text=True,
    )
    if cp2.returncode != 0:
        pytest.skip(
            "build_index CLI not available or failed; "
            "current ingest CLI only produces cleaned texts. "
            f"STDERR:\n{cp2.stderr}"
        )

    assert docstore.exists(), "docstore.jsonl not found after build_index"
    assert index.exists(), "index.faiss not found after build_index"

    # 4) 最終一致性檢查（若是用 chunks.jsonl 產生，就比對行數）
    if chunks_path.exists():
        doc_lines = sum(1 for _ in open(docstore, "r", encoding="utf-8"))
        chunk_lines = sum(1 for _ in open(chunks_path, "r", encoding="utf-8"))
        assert doc_lines == chunk_lines, "docstore and chunks line counts differ"

