# app/llm.py
from typing import Dict, Any
from openai import OpenAI
from .config import settings
from .observability import COST_COUNTER, TOKENS_COUNTER, ERROR_COUNT


_client = None

def _client_lazy() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key or None)
    return _client

# 參考價（USD / 1M tokens）
PRICE = {
    "gpt-5.4-mini":  {"input": 0.75,  "output": 4.50},
    "gpt-4.1-mini":  {"input": 0.40,  "output": 1.60},
    "gpt-4o-mini":   {"input": 0.150, "output": 0.600},
}
_DEFAULT_PRICE = {"input": 0.75, "output": 4.50}

def _estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = PRICE.get(model, _DEFAULT_PRICE)
    return (in_tokens/1_000_000)*p["input"] + (out_tokens/1_000_000)*p["output"]


def answer_with_context(query: str, context: str) -> Dict[str, Any]:
    client = _client_lazy()
    system = (
        "請用繁體中文回答。"
        "答案必須只用一句完整的句子表達。"
        "不要加開場白或結語，不要使用條列符號，不要多段落。"
        "不要在答案中附加任何來源或 (source: ...)，來源由系統在 meta 中提供。"
        "若答案涉及端點/指標/模型名，請原樣輸出（大小寫與符號不改），多個項目以「、」分隔。"
        "若資訊不足，請直接回答「資訊不足」。"
    )
    user = f"問題：{query}\n\n已檢索到的相關內容：\n{context}"

    try:
        resp = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {"role":"system","content": system},
                {"role":"user","content": user},
            ],
            temperature=0.2,
            max_completion_tokens=settings.answer_max_tokens,
        )
    except Exception:
        ERROR_COUNT.labels(stage="llm").inc()
        raise

    msg = resp.choices[0].message.content or ""
    usage = resp.usage  # type: ignore
    in_toks = getattr(usage, "prompt_tokens", 0) or 0
    out_toks = getattr(usage, "completion_tokens", 0) or 0
    TOKENS_COUNTER.labels(kind="input", model=settings.chat_model).inc(in_toks)
    TOKENS_COUNTER.labels(kind="output", model=settings.chat_model).inc(out_toks)
    cost = _estimate_cost(settings.chat_model, in_toks, out_toks)
    COST_COUNTER.labels(model=settings.chat_model).inc(cost)

    return {
        "text": msg,
        "usage": {"input_tokens": in_toks, "output_tokens": out_toks, "total_tokens": (in_toks + out_toks)},
        "cost_usd": cost,
    }