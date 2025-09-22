# app/ingest/chunking.py
from typing import List, Dict
import re
import math

def split_paragraphs(text: str) -> List[str]:
    # 以空行分段，保留自然段
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts

def approx_tokens(chars: int) -> int:
    # 粗略估：中文/英文混合 ~ 4 chars/token
    return max(1, math.ceil(chars / 4))

def chunk_by_chars(paragraphs: List[str], max_chars=800, overlap=120) -> List[str]:
    chunks, buf = [], ""
    for p in paragraphs:
        if len(p) > max_chars:
            # 對超長段落做硬切
            for i in range(0, len(p), max_chars - overlap):
                chunks.append(p[i:i + max_chars])
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + "\n" + p).strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks

def to_records(chunks: List[str], title: str, source: str) -> List[Dict]:
    recs = []
    for i, c in enumerate(chunks):
        recs.append({
            "id": f"{source}::chunk-{i}",
            "title": title,
            "text": c,
            "source": source
        })
    return recs
