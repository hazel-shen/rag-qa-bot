# app/cache.py
from time import time
from typing import Any, Dict, Optional

class TTLCache:
    """
    最小可用 TTL 快取（純記憶體）。
    之後可換成 Redis：把 get/set 實作改成 redis.get / redis.setex。
    """
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

# 全域單例（之後可改成依賴注入）
result_cache = TTLCache(default_ttl_seconds=300, max_size=1000)
