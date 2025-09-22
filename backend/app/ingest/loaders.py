# app/ingest/loaders.py
from dataclasses import dataclass
from typing import Iterable, Tuple
import os, pathlib

from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from docx import Document as DocxDocument

@dataclass
class RawDoc:
    path: str
    title: str
    text: str

def load_txt_md(path: str) -> str:
    # 文字／Markdown 直接讀；有需要可額外移除 md 標記
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def load_pdf(path: str) -> str:
    doc = fitz.open(path)
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    return "\n".join(texts)

def load_docx(path: str) -> str:
    d = DocxDocument(path)
    return "\n".join(p.text for p in d.paragraphs)

def load_html(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "lxml")
        # 移除 script/style
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n")

def iter_raw_docs(root: str):
    for p in pathlib.Path(root).rglob("*"):
        if p.is_dir():
            continue
        ext = p.suffix.lower()
        if ext not in {".txt", ".md", ".pdf", ".docx", ".html", ".htm"}:
            continue
        title = os.path.basename(p)
        try:
            if ext in {".txt", ".md"}:
                text = load_txt_md(str(p))
            elif ext == ".pdf":
                text = load_pdf(str(p))
            elif ext == ".docx":
                text = load_docx(str(p))
            else:
                text = load_html(str(p))
        except Exception as e:
            print(f"[WARN] skip file due to error: {p} ({e})")
            continue
        yield RawDoc(path=str(p), title=title, text=text)
