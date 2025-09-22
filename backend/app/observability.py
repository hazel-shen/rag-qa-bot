# app/observability.py
# app/observability.py
from prometheus_client import Counter, Histogram

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
