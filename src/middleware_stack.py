#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 中间件安装（3.2.0：从 server.create_app 抽出）。

行为与 3.1.0 一致：GZip + RequestId + Maintenance。
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

GZIP_MINIMUM_SIZE = 1000


def install_middleware(app: FastAPI, *, cfg, root) -> None:  # noqa: C901  # 纯中间件装配壳
    """在 app 上安装 gzip / request-id / security / CSRF / maintenance 中间件。"""
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)

    class _RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            rid = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:16]
            request.state.request_id = rid
            resp = await call_next(request)
            resp.headers["X-Request-ID"] = rid
            return resp

    app.add_middleware(_RequestIdMiddleware)

    class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            try:
                from security_headers import apply_headers

                https = (request.url.scheme or "").lower() == "https" or (
                    request.headers.get("x-forwarded-proto") or ""
                ).lower() == "https"
                apply_headers(resp, https=https)
            except Exception:
                pass
            return resp

    app.add_middleware(_SecurityHeadersMiddleware)

    class _CsrfOriginMiddleware(BaseHTTPMiddleware):
        """状态变更：Origin/Referer 同源、CSRF 双提交，或显式运维/测试白名单。

        3.6.0 小修：缺 Origin/Referer 不再通用放行；校验异常记日志并 403（fail-closed）。
        """

        async def dispatch(self, request, call_next):
            method = (request.method or "GET").upper()
            if method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
                from fastapi.responses import JSONResponse

                try:
                    from csrf_guard import OPS_HEADER, csrf_ok

                    host = request.headers.get("host")
                    origin = request.headers.get("origin")
                    referer = request.headers.get("referer")
                    tok = request.headers.get("x-csrf-token")
                    cookie = request.cookies.get("csrf_token")
                    try:
                        client_host = (
                            request.client.host if request.client else ""
                        ) or ""
                    except Exception:
                        client_host = ""
                    ok, reason = csrf_ok(
                        method=method,
                        origin=origin,
                        referer=referer,
                        host=host,
                        csrf_header=tok,
                        csrf_cookie=cookie,
                        client_host=client_host,
                        user_agent=request.headers.get("user-agent"),
                        ops_header=request.headers.get(OPS_HEADER),
                    )
                    if not ok:
                        return JSONResponse(
                            {"detail": f"CSRF blocked: {reason}"},
                            status_code=403,
                        )
                except Exception as e:
                    try:
                        import logging

                        logging.getLogger("kanban.csrf").warning(
                            "csrf check error → 403: %s", e
                        )
                    except Exception:
                        pass
                    return JSONResponse(
                        {"detail": "CSRF blocked: check_error"},
                        status_code=403,
                    )
            return await call_next(request)

    app.add_middleware(_CsrfOriginMiddleware)

    class _MaintenanceMiddleware(BaseHTTPMiddleware):
        _expire_every = 32
        _expire_n = 0

        async def dispatch(self, request, call_next):
            try:
                import maintenance_mode as _mm

                _MaintenanceMiddleware._expire_n += 1
                if _MaintenanceMiddleware._expire_n >= _MaintenanceMiddleware._expire_every:
                    _MaintenanceMiddleware._expire_n = 0
                    _mm.maybe_expire(max_minutes=10, cfg=cfg, root=root)
                path = request.url.path or ""
                if path.startswith("/api"):
                    return await call_next(request)
                if request.method in ("GET", "HEAD") and _mm.is_on(cfg, root):
                    accept = (request.headers.get("accept") or "").lower()
                    wants_html = (
                        "text/html" in accept
                        or accept in ("", "*/*")
                        or "text/*" in accept
                    )
                    if "application/json" in accept and "text/html" not in accept:
                        wants_html = False
                    if wants_html and not path.startswith("/openapi"):
                        body = _mm.load_maintenance_html(root)
                        return HTMLResponse(
                            body,
                            status_code=503,
                            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
                        )
            except Exception:
                pass
            return await call_next(request)

    app.add_middleware(_MaintenanceMiddleware)
