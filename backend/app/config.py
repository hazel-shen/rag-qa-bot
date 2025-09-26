# app/config.py
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import os

# 先嘗試尋找並且載入 .env（方便本地 dev）
load_dotenv(find_dotenv())

# 判斷 APP_ENV
APP_ENV = os.getenv("APP_ENV", "dev")

# 只有在 prod 環境才去讀 Secrets Manager
if APP_ENV == "prod" and os.getenv("AWS_SECRETS_ID"):
    try:
        from .aws_secrets import load_from_secrets_manager
        load_from_secrets_manager(os.environ["AWS_SECRETS_ID"])
    except Exception:
        # 這裡可加 logger.warning
        pass


class Settings(BaseModel):
    # === OpenAI / 模型 ===
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    rerank_provider: str = os.getenv("RERANK_PROVIDER", "local")
    rerank_model: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "3"))
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")

    # === 檔案路徑 ===
    data_dir: str = os.getenv("DATA_DIR", "backend/data")
    index_path: str = os.getenv("INDEX_PATH", "backend/data/index.faiss")
    docstore_path: str = os.getenv("DOCSTORE_PATH", "backend/data/docstore.jsonl")

    # === 檢索 / 回答 ===
    top_k: int = int(os.getenv("TOP_K") or os.getenv("RERANK_TOP_K", "3"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "1800"))
    answer_single_line: bool = False
    answer_max_tokens: int = int(os.getenv("ANSWER_MAX_TOKENS", "400"))

    # === Rate Limit ===
    rate_limit_per_ip_per_min: int = int(os.getenv("RATE_LIMIT_PER_IP_PER_MIN", "30"))
    rate_limit_per_user_per_min: int = int(os.getenv("RATE_LIMIT_PER_USER_PER_MIN", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "10"))
    disable_rate_limit: bool = bool(int(os.getenv("DISABLE_RATE_LIMIT", "0")))

    # === Cache ===
    cache_backend: str = os.getenv("CACHE_BACKEND", "memory")
    cache_namespace: str = os.getenv("CACHE_NAMESPACE", "ragqa")
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    index_version: str = os.getenv("INDEX_VERSION", "v1")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # === 環境 ===
    env: str = APP_ENV


settings = Settings()
