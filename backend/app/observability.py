# app/observability.py
from prometheus_client import Counter, Histogram, Gauge

# 請求層級
REQUEST_COUNT = Counter(
    "llm_requests_total",
    "Total number of requests",
    ["route", "status"]  # status: success|error
)
REQUEST_LATENCY = Histogram(
    "llm_request_latency_seconds",
    "Request latency",
    ["route"]
)

# Token / 成本
TOKENS_COUNTER = Counter(
    "llm_tokens_total",
    "Tokens by kind and model",
    ["kind", "model"]  # kind: input|output
)
COST_COUNTER = Counter(
    "llm_cost_total_usd",
    "Total cost (USD) by model",
    ["model"]
)

# 快取
CACHE_REQUESTS = Counter(
    "rag_cache_requests_total",
    "Total cache lookups",
    ["route"]
)
CACHE_RESULTS = Counter(
    "rag_cache_results_total",
    "Cache results by outcome",
    ["route", "result"]  # result: hit|miss|write
)

# 檢索/嵌入/重排/LLM 分段延遲
EMBEDDING_LATENCY = Histogram(
    "rag_embedding_latency_seconds",
    "Latency for embedding generation",
    ["stage"]  # stage: query|chunks (預留)
)
RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_latency_seconds",
    "Latency for vector retrieval (FAISS)",
    []
)
RERANK_LATENCY = Histogram(
    "rag_rerank_latency_seconds",
    "Latency for reranking stage",
    []
)
LLM_LATENCY = Histogram(
    "rag_llm_latency_seconds",
    "Latency for LLM completion",
    ["model"]
)

# 錯誤
ERROR_COUNT = Counter(
    "rag_errors_total",
    "Errors by stage",
    ["stage"]  # stage: cache|embedding|retrieval|rerank|llm|route
)

# Input policy metrics
input_rejected_total = Counter(
    "input_rejected_total",
    "Total rejected inputs by type",
    ["type"],  # length|format|keyword|regex|url|role
)

input_rate_limited_total = Counter(
    "input_rate_limited_total",
    "Total rate-limited requests by scope",
    ["scope"],  # ip|user
)

input_accepted_total = Counter(
    "input_accepted_total",
    "Total accepted inputs",
)

input_chars_histogram = Histogram(
    "input_chars_histogram",
    "Histogram of input length in characters",
    buckets=(50, 100, 200, 400, 800, 1200, 1600, 2000, 3000, 5000),
)

# 若目前暫不計算 tokens，也可以保留但先不呼叫
input_tokens_histogram = Histogram(
    "input_tokens_histogram",
    "Histogram of input length in tokens",
    buckets=(64, 128, 256, 512, 768, 1024, 1536, 2048),
)

input_violation_last_seen_timestamp = Gauge(
    "input_violation_last_seen_timestamp",
    "Epoch seconds of last seen violation for a given type",
    ["type"],
)

# --- 便捷記錄函式（給 security.py / routes.py 呼叫） ---
def record_accept(len_chars: int, len_tokens: int | None = None) -> None:
    input_accepted_total.inc()
    if len_chars is not None:
        input_chars_histogram.observe(len_chars)
    if len_tokens is not None:
        input_tokens_histogram.observe(len_tokens)

def record_reject(reject_type: str) -> None:
    input_rejected_total.labels(reject_type).inc()
    import time as _t
    input_violation_last_seen_timestamp.labels(reject_type).set(int(_t.time()))

def record_throttle(scope: str) -> None:
    input_rate_limited_total.labels(scope).inc()