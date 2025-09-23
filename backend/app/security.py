# app/security.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

import yaml

from .observability import record_accept, record_reject

# === 載入 policy ===
_policy_path = Path(__file__).parent / "policies" / "input_policy.yaml"

def load_policy(path: Path | None = None) -> Dict[str, Any]:
    """載入 YAML policy，回傳 dict。"""
    p = path or _policy_path
    if not p.exists():
        raise FileNotFoundError(f"Policy file not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# 預載一次（避免每次呼叫都打檔案）；若你要熱重載可改成每次 load_policy()
_POLICY = load_policy()

@dataclass
class ValidationResult:
    ok: bool
    type: Optional[str] = None       # length|format|keyword|regex|url|role
    policy_version: Optional[str] = None

# ---- 檢查子模組：違規回傳 type，否則回 None ----
def check_length(text: str, policy: Dict[str, Any]) -> Optional[str]:
    max_chars = int((policy.get("length") or {}).get("max_chars", 2000))
    if not text or len(text) > max_chars:
        return "length"
    return None

_HTML_LIKE = re.compile(r"<(script|iframe|img|a|on\w+)", re.I)
_CODE_BLOCK = re.compile(r"```", re.M | re.S)
# 只把 '||'、'&&' 視為 shell pipeline；分號需跟常見指令才判定
_SHELL_PIPE = re.compile(r"(\|\||&&|;\s*(rm|curl|wget|bash|sh|nc|python3?|cat|ls)\b)", re.I)

def check_format(text: str, policy: Dict[str, Any]) -> Optional[str]:
    fmt = policy.get("format") or {}
    if fmt.get("strip_html", True) and _HTML_LIKE.search(text):
        return "format"
    if fmt.get("reject_code_blocks", True) and (_CODE_BLOCK.search(text) or _SHELL_PIPE.search(text)):
        return "format"
    return None

_URL_RE = re.compile(r"(?i)\b(?:https?|file|ftp)://[^\s]+")

def check_urls(text: str, policy: Dict[str, Any]) -> Optional[str]:
    url_cfg = policy.get("url") or {}
    urls = _URL_RE.findall(text or "")
    if not urls:
        return None
    if not url_cfg.get("allow_urls", False):
        return "url"
    whitelist = set(url_cfg.get("url_whitelist") or [])
    for u in urls:
        if not any(u.startswith(prefix) for prefix in whitelist):
            return "url"
    return None

def check_blacklist(text: str, policy: Dict[str, Any]) -> Optional[str]:
    bl = policy.get("blacklist") or {}
    lowered = text.lower()
    for kw in (bl.get("blocked_keywords") or []):
        if kw and kw.lower() in lowered:
            return "keyword"
    for pat in (bl.get("blocked_regex") or []):
        try:
            if re.search(pat, text, re.I):
                return "regex"
        except re.error:
            # 忽略不合法 regex
            continue
    return None

def check_role(text: str, user_role: str, policy: Dict[str, Any]) -> Optional[str]:
    roles_cfg = (policy.get("roles") or {}).get("role_whitelist", {}) or {}
    role_entry = roles_cfg.get(user_role or "", {})
    # 這裡僅預留掛勾；若你有「內部主題」檢測，可在此擋掉
    # 例如：if is_internal_topic(text) and not role_entry.get("allow_internal_topics", False): return "role"
    return None

# ---- 主流程：回傳 ValidationResult，而不是丟 HTTPException ----
def validate_input(query: str, user_role: str = "guest", content_type: str = "text/plain") -> ValidationResult:
    policy = _POLICY  # 若要熱重載可改成：policy = load_policy()
    version = str(policy.get("policy_version", ""))

    text = (query or "").strip()

    for checker in (check_length, check_format, check_urls, check_blacklist):
        reason = checker(text, policy)
        if reason:
            record_reject(reason)
            return ValidationResult(ok=False, type=reason, policy_version=version)

    reason = check_role(text, user_role, policy)
    if reason:
        record_reject(reason)
        return ValidationResult(ok=False, type=reason, policy_version=version)

    record_accept(len(text))
    return ValidationResult(ok=True, type=None, policy_version=version)

# 舊函式保留為 no-op（避免舊 import 失敗；之後可刪）
def validate_query(query: str):
    return query
