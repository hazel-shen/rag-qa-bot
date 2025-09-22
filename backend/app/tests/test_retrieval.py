from app.retrieval import build_context

def test_build_context_respects_max_chars():
    chunks = [
        {"title": "A", "text": "x"*150, "source": "s1"},
        {"title": "B", "text": "y"*150, "source": "s2"},
        {"title": "C", "text": "z"*150, "source": "s3"},
    ]
    ctx = build_context(chunks, max_chars=320)  # 中間包含分隔符與標頭
    assert len(ctx) <= 320
    # 仍應包含第一段，通常第二段會被截斷或放不下
    assert "[A]" in ctx



def test_build_context_unicode_and_separator():
    chunks = [
        {"title": "一號📘", "text": "甲乙丙丁" * 40 + "🙂", "source": "s1"},
        {"title": "二號（全形）", "text": "ＡＢＣＤ" * 40 + "🚀", "source": "s2"},
        {"title": "Three", "text": "Lorem ipsum " * 40, "source": "s3"},
    ]
    max_chars = 420
    ctx = build_context(chunks, max_chars=max_chars)
    assert len(ctx) <= max_chars
    # 分隔符存在而且不會破壞編碼
    assert "\n---\n" in ctx
    # 至少包含第一段標題
    assert "[一號📘]" in ctx
