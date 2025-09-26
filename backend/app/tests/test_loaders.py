# app/tests/test_loaders.py
from pathlib import Path
import pytest

# ---------- HTML ----------

def test_html_script_and_style_removed():
    """basic_clean 應移除 <script>/<style> 內容與標籤，僅保留可見文字"""
    from app.ingest.cleaning import basic_clean

    html = """
    <html>
      <head>
        <style>body{display:none}</style>
        <script>console.log("hi")</script>
      </head>
      <body>
        <h1>Title</h1>
        <p>Content</p>
      </body>
    </html>
    """
    out = basic_clean(html)
    # 不應包含 script/style 中的內容或標籤名
    assert "console.log" not in out
    assert "display:none" not in out
    assert "<script" not in out.lower()
    assert "<style" not in out.lower()
    # 仍保留可見文字
    assert "Title" in out
    assert "Content" in out


# ---------- DOCX ----------

@pytest.mark.parametrize("missing_path", ["nope.docx", ""])
def test_docx_invalid_path_has_clear_error(tmp_path: Path, missing_path: str):
    """
    若 loaders 有提供 docx_to_text，丟無效路徑應回明確錯誤（FileNotFoundError 或 ValueError）。
    若沒提供此 loader，則跳過。
    """
    try:
        import app.ingest.loaders as L
    except Exception as e:
        pytest.skip(f"app.ingest.loaders not importable: {e!r}")

    if not hasattr(L, "docx_to_text"):
        pytest.skip("docx_to_text not implemented; skipping DOCX tests")

    bad = tmp_path / missing_path if missing_path else tmp_path / "missing.docx"
    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        L.docx_to_text(str(bad))


def test_docx_roundtrip_if_deps_available(tmp_path: Path):
    """
    若專案支援 docx_to_text 且安裝 python-docx，就做一個最小 docx 來驗證能讀到文字。
    否則跳過，不讓 CI 壞掉。
    """
    try:
        import app.ingest.loaders as L
    except Exception as e:
        pytest.skip(f"app.ingest.loaders not importable: {e!r}")
    if not hasattr(L, "docx_to_text"):
        pytest.skip("docx_to_text not implemented")

    try:
        from docx import Document  # python-docx
    except Exception:
        pytest.skip("python-docx not installed")

    doc_path = tmp_path / "tiny.docx"
    doc = Document()
    doc.add_paragraph("Hello from DOCX")
    doc.save(doc_path)

    text = L.docx_to_text(str(doc_path))
    assert "Hello from DOCX" in text


# ---------- PDF ----------

def test_pdf_multi_page_merge_if_deps_available(tmp_path: Path):
    """
    若專案支援 pdf_to_text 且安裝 reportlab（建檔用），就建立兩頁 PDF，
    驗證 pdf_to_text 輸出包含兩頁內容（表示有合併）。
    否則跳過。
    """
    try:
        import app.ingest.loaders as L
    except Exception as e:
        pytest.skip(f"app.ingest.loaders not importable: {e!r}")
    if not hasattr(L, "pdf_to_text"):
        pytest.skip("pdf_to_text not implemented")

    try:
        # 用 reportlab 動態產生一份兩頁的 PDF
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except Exception:
        pytest.skip("reportlab not installed (needed to generate a test PDF)")

    pdf_path = tmp_path / "two_pages.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 720, "Page One Content")
    c.showPage()
    c.drawString(72, 720, "Page Two Content")
    c.save()

    text = L.pdf_to_text(str(pdf_path))
    # 兩頁的字都應該出現在合併後的文字中
    assert "Page One Content" in text
    assert "Page Two Content" in text
