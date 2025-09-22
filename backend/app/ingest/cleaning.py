# app/ingest/cleaning.py
import re

def normalize_whitespace(text: str) -> str:
    # 統一換行、空白
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 把多個空白壓成一個（保留段落換行）
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text

def strip_page_noise(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for ln in lines:
        # 去除常見頁碼/頁首頁尾樣式
        if re.fullmatch(r"\s*Page\s+\d+\s*/\s*\d+\s*", ln, flags=re.I):
            continue
        if re.fullmatch(r"\s*\d+\s*/\s*\d+\s*", ln):
            continue
        if re.fullmatch(r"\s*第?\s*\d+\s*頁\s*(?:共\s*\d+\s*頁)?\s*", ln):
            continue
        if len(ln.strip()) == 0:
            cleaned.append("")
            continue
        cleaned.append(ln)
    out = "\n".join(cleaned)
    # 去除連續重複行（粗略 anti header/footer）
    out = re.sub(r"(?m)^(.*)\n\1\n+", r"\1\n", out)
    return out.strip()

def basic_clean(text: str) -> str:
    text = normalize_whitespace(text)
    text = strip_page_noise(text)
    return text
