# backend/app/cache.py
from __future__ import annotations
import os, re, json, zlib, hashlib
from time import time
from typing import Any, Dict, Optional

try:
    import redis  # redis-py (同步版)
except Exception:
    redis = None

# ---------- 設定 ----------
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")  # memory | redis
CACHE_NAMESPACE = os.getenv("CACHE_NAMESPACE", "ragqa")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# 版本標記（避免髒命中）
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")
RERANKER_VERSION = os.getenv("RERANKER_VERSION", "none")
MODEL_VERSION = os.getenv("MODEL_VERSION", "none")

# Redis URL (本機 / 雲端)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ---------- Key 產生器 ----------
_space = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _space.sub(" ", s.strip().lower())



def build_cache_key(
    kind: str,
    query: str,
    *,
    params: dict | None = None,
    model_version: str | None = None,
    reranker_version: str | None = None,
    index_version: str | None = None,
) -> str:
    payload = {
        "q": _norm(query),
        "params": params or {},
        "index": index_version or INDEX_VERSION,
        "reranker": reranker_version or RERANKER_VERSION,
        "model": model_version or MODEL_VERSION,
        "kind": kind,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()[:16]
    return f"{CACHE_NAMESPACE}:{kind}:{h}"


# ---------- 簡單壓縮 ----------
def _dumps(obj: Any) -> bytes:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return zlib.compress(data)


def _loads(buf: bytes) -> Any:
    data = zlib.decompress(buf)
    return json.loads(data.decode("utf-8"))


# ---------- 記憶體 TTLCache ----------
class TTLCache:
    """最小可用 TTL 快取（純記憶體）。"""

    def __init__(self, default_ttl_seconds: int = 300, max_size: int = 1000):
        self.ttl = default_ttl_seconds
        self.max_size = max_size
        self.store: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        now = time()
        exp = self.expiry.get(key)
        if exp is None:
            return None
        if now > exp:
            # 過期清理
            self.store.pop(key, None)
            self.expiry.pop(key, None)
            return None
        return self.store.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        if len(self.store) >= self.max_size:
            # 簡單丟棄策略：移除第一個（之後可換 LRU）
            k, _ = next(iter(self.store.items()))
            self.store.pop(k, None)
            self.expiry.pop(k, None)

        ttl = ttl_seconds if ttl_seconds is not None else self.ttl
        self.store[key] = value
        self.expiry[key] = time() + ttl


# ---------- Redis 版 ----------
class RedisCache:
    """同步版 Redis 快取。"""

    def __init__(self, url: str, default_ttl_seconds: int = 3600):
        if redis is None:
            raise RuntimeError("redis-py 未安裝，請先 pip install redis")
        # decode_responses=False → bytes，搭配自家 _dumps/_loads
        self.r = redis.from_url(url, decode_responses=False)
        self.ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        b = self.r.get(key)
        if b is None:
            return None
        try:
            return _loads(b)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl
        self.r.setex(key, ttl, _dumps(value))


# ---------- 單例與門面 ----------
_result_cache_singleton: TTLCache | RedisCache | None = None


def _get_result_cache():
    global _result_cache_singleton
    if _result_cache_singleton is not None:
        return _result_cache_singleton

    if CACHE_BACKEND.lower() == "redis":
        print(f"[cache] Using Redis backend @ {REDIS_URL}")
        _result_cache_singleton = RedisCache(
            REDIS_URL, default_ttl_seconds=CACHE_TTL_SECONDS
        )
    else:
        print(f"[cache] Using in-memory TTLCache (ttl={CACHE_TTL_SECONDS}s)")
        _result_cache_singleton = TTLCache(
            default_ttl_seconds=CACHE_TTL_SECONDS, max_size=10000
        )
    return _result_cache_singleton


def cache_get(key: str) -> Optional[Any]:
    return _get_result_cache().get(key)


def cache_set(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    return _get_result_cache().set(key, value, ttl_seconds=ttl_seconds)


# 舊名保留（相容舊 import）
result_cache = _get_result_cache()
