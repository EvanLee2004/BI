# -*- coding: utf-8 -*-
"""CSRF / Origin 防护（3.6.0 G3）。

状态变更请求（POST/PUT/PATCH/DELETE）：
- 校验 Origin 或 Referer 与 Host 同源；或
- 校验 X-CSRF-Token / csrf_token 与会话 cookie 双提交一致。
GET/HEAD/OPTIONS 放行。
"""

from __future__ import annotations

from urllib.parse import urlparse


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def origin_matches_host(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    try:
        o = urlparse(origin)
        # Host 可能含端口
        origin_host = o.netloc or ""
        return origin_host.lower() == host.lower()
    except Exception:
        return False


def referer_matches_host(referer: str | None, host: str | None) -> bool:
    if not referer or not host:
        return False
    try:
        r = urlparse(referer)
        return (r.netloc or "").lower() == host.lower()
    except Exception:
        return False


def csrf_ok(
    *,
    method: str,
    origin: str | None,
    referer: str | None,
    host: str | None,
    csrf_header: str | None = None,
    csrf_cookie: str | None = None,
    require_token: bool = False,
) -> tuple[bool, str]:
    m = (method or "GET").upper()
    if m in SAFE_METHODS:
        return True, "safe_method"
    # 同源 Origin
    if origin_matches_host(origin, host):
        return True, "origin_ok"
    # 无 Origin 时退 Referer
    if not origin and referer_matches_host(referer, host):
        return True, "referer_ok"
    # 双提交 token
    if csrf_header and csrf_cookie and hmac_eq(csrf_header, csrf_cookie):
        return True, "token_ok"
    if require_token:
        return False, "csrf_required"
    if origin and not origin_matches_host(origin, host):
        return False, "origin_mismatch"
    return False, "csrf_failed"


def hmac_eq(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest((a or "").encode(), (b or "").encode())
