# app/rate_limit.py
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Optional, Tuple
from .config import settings

# ── 簡易 in-memory token bucket，預留未來 Redis backend 介面 ──
# ── 資料結構 ─────────────────────────────────────────────────────
@dataclass
class RateLimitDecision:
    allowed: bool
    scope: Optional[str] = None  # "ip" | "user" | None
    retry_after_sec: Optional[int] = None


class _Bucket:
    __slots__ = ("capacity", "tokens", "refill_rate_per_sec", "last", "lock")
    def __init__(self, capacity: int, refill_rate_per_sec: float) -> None:
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate_per_sec = refill_rate_per_sec
        self.last = time.time()
        self.lock = RLock()

    def take(self, n: int = 1) -> Tuple[bool, int]:
        now = time.time()
        with self.lock:
            elapsed = max(0.0, now - self.last)
            refill = elapsed * self.refill_rate_per_sec
            if refill > 0:
                self.tokens = min(self.capacity, self.tokens + refill)
                self.last = now
            if self.tokens >= n:
                self.tokens -= n
                return True, 0
            # 估算多久後有 1 個 token
            deficit = max(0.0, n - self.tokens)
            wait = int(max(1.0, deficit / self.refill_rate_per_sec))
            return False, wait

# ── RateLimiter 本體 ────────────────────────────────────────────
class RateLimiter:
    def __init__(self) -> None:
        # 預設值；會在 configure_from_settings() 被覆蓋
        self._per_ip_per_min = 30
        self._per_user_per_min = 60
        self._burst = 10
        self._disabled = False

        self._ip_buckets: dict[str, _Bucket] = {}
        self._user_buckets: dict[str, _Bucket] = {}
        self._lock = RLock()
        
        # 依環境變數初始化
        self.configure_from_settings()

    # --- 對外設定介面 ---
    def configure(self, per_ip_per_min: int, per_user_per_min: int, burst: int, *, disabled: bool = False) -> None:
        self._per_ip_per_min = max(1, per_ip_per_min)
        self._per_user_per_min = max(1, per_user_per_min)
        self._burst = max(1, int(burst))
        self._disabled = bool(disabled)


    def configure_from_settings(self) -> None:
        self.configure(
            per_ip_per_min=getattr(settings, "rate_limit_per_ip_per_min", 30),
            per_user_per_min=getattr(settings, "rate_limit_per_user_per_min", 60),
            burst=getattr(settings, "rate_limit_burst", 10),
            disabled=getattr(settings, "disable_rate_limit", False) or getattr(settings, "env", "") == "test",
        )

    def reset_buckets(self) -> None:
        # 測試用：清空所有桶，避免跨測試互相影響
        with self._lock:
            self._ip_buckets.clear()
            self._user_buckets.clear()

    # --- 內部工具 ---
    def _get_bucket(self, table: dict[str, _Bucket], key: str, refill_per_min: int) -> _Bucket:
        with self._lock:
            b = table.get(key)
            if b is None:
                b = _Bucket(capacity=self._burst, refill_rate_per_sec=max(0.1, refill_per_min / 60.0))
                table[key] = b
            return b

    # --- 主流程 ---
    def check(self, ip: str | None, user_id: str | None) -> RateLimitDecision:
        if self._disabled:
            return RateLimitDecision(True)

        # 先檢查 user，再檢查 ip（順序固定即可）
        if user_id:
            b_user = self._get_bucket(self._user_buckets, user_id, self._per_user_per_min)
            ok, wait = b_user.take(1)
            if not ok:
                return RateLimitDecision(False, scope="user", retry_after_sec=wait)
            return RateLimitDecision(True)

        # 沒帶 user id 才落回 IP 桶
        if ip:
            b_ip = self._get_bucket(self._ip_buckets, ip, self._per_ip_per_min)
            ok, wait = b_ip.take(1)
            if not ok:
                return RateLimitDecision(False, scope="ip", retry_after_sec=wait)

        return RateLimitDecision(True)


# ── 全域單例 ─────────────────────────────────────────────────────

rate_limiter = RateLimiter()


# ── 相容舊呼叫點的 helper（可留著，之後移除） ─────────────────────
def init_rate_limiter(policy: dict | None) -> None:
    """
    兼容舊版：若外部仍呼叫 init_rate_limiter(policy)，
    我們優先採用環境變數 settings；policy 僅在沒設 env 時作為 fallback。
    """
    if getattr(settings, "disable_rate_limit", False) or getattr(settings, "env", "") == "test":
        rate_limiter.configure_from_settings()
        return

    rl = (policy or {}).get("rate_limit", {}) if policy else {}
    per_ip = int(rl.get("per_ip_per_min", getattr(settings, "rate_limit_per_ip_per_min", 30)))
    per_user = int(rl.get("per_user_per_min", getattr(settings, "rate_limit_per_user_per_min", 60)))
    burst = int(rl.get("burst", getattr(settings, "rate_limit_burst", 10)))
    rate_limiter.configure(per_ip, per_user, burst, disabled=False)