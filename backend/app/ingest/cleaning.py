# app/ingest/cleaning.py
import re
from bs4 import BeautifulSoup

_MULTI_WS  = re.compile(r"\s+")

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

def _strip_html_blocks_and_tags(text: str) -> str:
    # 使用 BeautifulSoup 來移除 <script>/<style> 標籤以及所有 HTML 標籤
    soup = BeautifulSoup(text, "html.parser")
    # 移除所有 <script> 與 <style> 標籤
    for tag in soup(["script", "style"]):
        tag.extract()
    s = soup.get_text(separator=" ")
    # 壓縮空白避免留下大量空格
    s = _MULTI_WS.sub(" ", s).strip()
    return s

def basic_clean(text: str) -> str:
    """
    最小可用清洗流程：
    - 先移除 HTML 的 <script>/<style> 區塊與所有標籤（若非 HTML 也安全）
    - 再做空白正規化與頁碼/頁首頁尾噪音移除
    """
    if not text:
        return ""
    # 先處理 HTML（即使是純文字也只會做輕量替換）
    text = _strip_html_blocks_and_tags(text)
    # 你的既有兩步：空白正規化 + 頁碼噪音移除
    text = normalize_whitespace(text)
    text = strip_page_noise(text)
    return text
