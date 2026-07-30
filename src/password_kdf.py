# -*- coding: utf-8 -*-
"""密码 KDF（3.6.0 G3）：stdlib PBKDF2-HMAC-SHA256 + 版本前缀。

格式：pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
禁止自创加密；常量时间比对。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCHEME = "pbkdf2_sha256"
DEFAULT_ITERS = 310_000  # OWASP 2023 量级；离线可接受
ALGO_VERSION = 1


def is_hashed(stored: str | None) -> bool:
    s = (stored or "").strip()
    return s.startswith(f"{SCHEME}$")


def hash_password(plain: str, *, iterations: int = DEFAULT_ITERS) -> str:
    if not plain:
        raise ValueError("empty_password")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return (
        f"{SCHEME}${iterations}$"
        f"{base64.urlsafe_b64encode(salt).decode()}$"
        f"{base64.urlsafe_b64encode(dk).decode()}"
    )


def verify_password(stored: str | None, plain: str) -> bool:
    """支持 hash 与遗留明文；比对恒为常量时间。"""
    s = stored or ""
    p = plain or ""
    if is_hashed(s):
        try:
            _, iters_s, salt_b64, hash_b64 = s.split("$", 3)
            iters = int(iters_s)
            salt = base64.urlsafe_b64decode(salt_b64.encode())
            expected = base64.urlsafe_b64decode(hash_b64.encode())
            dk = hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), salt, iters)
            return hmac.compare_digest(dk, expected)
        except Exception:
            return False
    # 遗留明文
    return hmac.compare_digest(s.encode("utf-8"), p.encode("utf-8"))


def needs_rehash(stored: str | None) -> bool:
    return not is_hashed(stored)
