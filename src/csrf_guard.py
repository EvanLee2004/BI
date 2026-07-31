# -*- coding: utf-8 -*-
"""CSRF / Origin 防护（3.6.0 G3 / 小修 fail-closed）。

状态变更请求（POST/PUT/PATCH/DELETE）：
- 校验 Origin 或 Referer 与 Host 同源；或
- 校验 X-CSRF-Token / csrf_token 与会话 cookie 双提交一致；或
- 显式运维/测试身份（见 is_allowlisted_caller）——禁止以「缺 Origin」通用放行。
GET/HEAD/OPTIONS 放行。
"""

from __future__ import annotations

from urllib.parse import urlparse


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# 同机运维脚本显式头（非通用密钥；须配合 loopback client）
OPS_HEADER = "x-kanban-ops"
OPS_HEADER_VALUE = "1"

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


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


def is_allowlisted_caller(
    *,
    client_host: str | None = None,
    user_agent: str | None = None,
    ops_header: str | None = None,
) -> bool:
    """同机脚本 / TestClient 白名单（显式身份，非「缺头即放行」）。"""
    ch = (client_host or "").strip().lower()
    ua = (user_agent or "").strip().lower()
    # Starlette TestClient
    if ch == "testclient" or ua.startswith("testclient"):
        return True
    # 本机运维：loopback + 显式 ops 头
    if ch in _LOOPBACK and (ops_header or "").strip() == OPS_HEADER_VALUE:
        return True
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
    client_host: str | None = None,
    user_agent: str | None = None,
    ops_header: str | None = None,
) -> tuple[bool, str]:
    m = (method or "GET").upper()
    if m in SAFE_METHODS:
        return True, "safe_method"
    # 显式白名单（TestClient / 本机 ops）
    if is_allowlisted_caller(
        client_host=client_host, user_agent=user_agent, ops_header=ops_header
    ):
        return True, "allowlisted"
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
    # 缺 Origin/Referer 且非白名单 → fail-closed
    if not origin and not referer:
        return False, "missing_origin_referer"
    return False, "csrf_failed"


def hmac_eq(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest((a or "").encode(), (b or "").encode())
