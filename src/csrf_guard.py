# -*- coding: utf-8 -*-
"""CSRF / Origin 防护（3.6.0 G3 / 小修 fail-closed / S-13 端口同源）。

状态变更请求（POST/PUT/PATCH/DELETE）：
- 校验 Origin 或 Referer 与请求 authority 同源（scheme + hostname + effective port）；或
- 校验 X-CSRF-Token / csrf_token 与会话 cookie 双提交一致；或
- 显式运维/测试身份（见 is_allowlisted_caller）——禁止以「缺 Origin」通用放行。

S-13：公网入口 :8001 时 nginx 须传 $http_host；后端仅在 loopback 客户端时信任
X-Forwarded-Host / X-Forwarded-Proto，规范化默认端口（http→80、https→443）。
禁止 hostname 后缀匹配、通配 Origin、缺头通用放行。
GET/HEAD/OPTIONS 放行。
"""

from __future__ import annotations

from urllib.parse import urlparse


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# 同机运维脚本显式头（非通用密钥；须配合 loopback client）
OPS_HEADER = "x-kanban-ops"
OPS_HEADER_VALUE = "1"

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def is_loopback_client(client_host: str | None) -> bool:
    ch = (client_host or "").strip().lower()
    if not ch:
        return False
    if ch in _LOOPBACK:
        return True
    # IPv4-mapped IPv6
    if ch.startswith("::ffff:"):
        return ch[7:] in ("127.0.0.1", "localhost")
    return False


def effective_port(port: int | None, scheme: str) -> int:
    """显式端口优先；缺省：https→443，其它→80。"""
    if port is not None:
        return int(port)
    return 443 if (scheme or "http").lower() == "https" else 80


def parse_host_header(raw: str | None) -> tuple[str | None, int | None]:
    """解析 Host / X-Forwarded-Host：hostname + 可选端口（IPv6 [addr]:port）。"""
    s = (raw or "").strip()
    if not s:
        return None, None
    # 多值取首
    s = s.split(",")[0].strip()
    if not s:
        return None, None
    # 伪 URL 形态
    if "://" in s:
        p = urlparse(s)
        return (p.hostname or None), p.port
    # [ipv6]:port 或 [ipv6]
    if s.startswith("["):
        end = s.find("]")
        if end < 0:
            return None, None
        host = s[1:end]
        rest = s[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host.lower(), int(rest[1:])
        return host.lower(), None
    # hostname:port（仅最后一个 : 且右侧为数字）
    if s.count(":") == 1:
        h, p = s.rsplit(":", 1)
        if p.isdigit():
            return h.lower() or None, int(p)
    return s.lower() or None, None


def resolve_request_authority(
    *,
    host: str | None,
    client_host: str | None = None,
    forwarded_host: str | None = None,
    forwarded_proto: str | None = None,
) -> tuple[str, str | None, int]:
    """返回 (scheme, hostname, effective_port)。

    仅 loopback 客户端信任 X-Forwarded-*（受控 nginx）；外部伪造忽略。
    """
    trust = is_loopback_client(client_host)
    scheme = "http"
    if trust and forwarded_proto:
        scheme = (forwarded_proto.split(",")[0].strip() or "http").lower()
        if scheme not in ("http", "https"):
            scheme = "http"
    raw_host = host
    if trust and forwarded_host and str(forwarded_host).strip():
        raw_host = forwarded_host
    hostname, port = parse_host_header(raw_host)
    return scheme, hostname, effective_port(port, scheme)


def origin_authority(origin: str | None) -> tuple[str, str | None, int] | None:
    if not origin:
        return None
    try:
        o = urlparse(origin)
    except Exception:
        return None
    scheme = (o.scheme or "").lower()
    if scheme not in ("http", "https"):
        return None
    if not o.hostname:
        return None
    return scheme, o.hostname.lower(), effective_port(o.port, scheme)


def authorities_match(
    left: tuple[str, str | None, int] | None,
    right: tuple[str, str | None, int] | None,
) -> bool:
    if not left or not right:
        return False
    ls, lh, lp = left
    rs, rh, rp = right
    if not lh or not rh:
        return False
    return ls == rs and lh == rh and lp == rp


def origin_matches_host(
    origin: str | None,
    host: str | None,
    *,
    client_host: str | None = None,
    forwarded_host: str | None = None,
    forwarded_proto: str | None = None,
) -> bool:
    """Origin 与请求 authority 同源（含默认端口规范化）。"""
    oa = origin_authority(origin)
    ra = resolve_request_authority(
        host=host,
        client_host=client_host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
    )
    return authorities_match(oa, ra)


def referer_matches_host(
    referer: str | None,
    host: str | None,
    *,
    client_host: str | None = None,
    forwarded_host: str | None = None,
    forwarded_proto: str | None = None,
) -> bool:
    """Referer 与请求 authority 同源。"""
    # Referer 是完整 URL，复用 origin 解析
    return origin_matches_host(
        referer,
        host,
        client_host=client_host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
    )


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
    if is_loopback_client(ch) and (ops_header or "").strip() == OPS_HEADER_VALUE:
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
    forwarded_host: str | None = None,
    forwarded_proto: str | None = None,
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
    if origin_matches_host(
        origin,
        host,
        client_host=client_host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
    ):
        return True, "origin_ok"
    # 无 Origin 时退 Referer
    if not origin and referer_matches_host(
        referer,
        host,
        client_host=client_host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
    ):
        return True, "referer_ok"
    # 双提交 token
    if csrf_header and csrf_cookie and hmac_eq(csrf_header, csrf_cookie):
        return True, "token_ok"
    if require_token:
        return False, "csrf_required"
    if origin and not origin_matches_host(
        origin,
        host,
        client_host=client_host,
        forwarded_host=forwarded_host,
        forwarded_proto=forwarded_proto,
    ):
        return False, "origin_mismatch"
    # 缺 Origin/Referer 且非白名单 → fail-closed
    if not origin and not referer:
        return False, "missing_origin_referer"
    return False, "csrf_failed"


def hmac_eq(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest((a or "").encode(), (b or "").encode())
