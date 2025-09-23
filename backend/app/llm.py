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

# 參考價（可依實際更新）
PRICE = {
    # USD / 1M tokens 估算（請依官方更新）
    "gpt-4o-mini": {"input": 0.150, "output": 0.600}
}

def _estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = PRICE.get(model, PRICE["gpt-4o-mini"])
    return (in_tokens/1_000_000)*p["input"] + (out_tokens/1_000_000)*p["output"]


def answer_with_context(query: str, context: str) -> Dict[str, Any]:
    client = _client_lazy()
    system = (
        "請用繁體中文回答，直接給出重點與步驟。"
        "不要加開場白或結語，不要出現「以下」「如下」等過場詞。"
        "不要在答案中附加任何來源或 (source: ...)，來源由系統在 meta 中提供。"
        "若需要列點，最多 5 點，避免重複同義句。"
        "若資訊不足，請坦承不足。"
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
            max_tokens=settings.answer_max_tokens,
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