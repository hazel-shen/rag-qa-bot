# app/config.py
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import os

# 嘗試尋找並載入 .env（例如 backend/.env）
load_dotenv(find_dotenv())

class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    rerank_model: str = os.getenv("RERANK_MODEL", "gpt-4o-mini-rerank")
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "3"))
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    data_dir: str = os.getenv("DATA_DIR", "backend/data")
    index_path: str = os.getenv("INDEX_PATH", "backend/data/index.faiss")
    docstore_path: str = os.getenv("DOCSTORE_PATH", "backend/data/docstore.jsonl")
    top_k: int = int(os.getenv("TOP_K", "3"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "1800"))
    answer_single_line: bool = False
    answer_max_tokens: int = int(os.getenv("ANSWER_MAX_TOKENS", "400"))
    # === Rate Limit 相關 ===
    rate_limit_per_ip_per_min: int = int(os.getenv("RATE_LIMIT_PER_IP_PER_MIN", "30"))
    rate_limit_per_user_per_min: int = int(os.getenv("RATE_LIMIT_PER_USER_PER_MIN", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "10"))
    disable_rate_limit: bool = bool(int(os.getenv("DISABLE_RATE_LIMIT", "0")))

    env: str = os.getenv("APP_ENV", "production")
settings = Settings()
