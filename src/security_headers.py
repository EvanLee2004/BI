# -*- coding: utf-8 -*-
"""安全响应头（3.6.0 G3）。"""

from __future__ import annotations

from typing import Any


def default_security_headers(*, https: bool = False) -> dict[str, str]:
    # 3.7.14 AUDIT-007：在不破坏 Vue/ECharts 的前提下收紧。
    # 仍保留 script/style 'unsafe-inline'（内联启动/主题与 ECharts 依赖；去之会白屏）→ 施工报告残余说明。
    # 本轮可安全加：object-src / frame-src / worker-src 限制。
    h = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-src 'none'; "
            "worker-src 'self' blob:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
    }
    if https:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return h


def apply_headers(response: Any, *, https: bool = False) -> Any:
    for k, v in default_security_headers(https=https).items():
        try:
            response.headers.setdefault(k, v)
        except Exception:
            pass
    return response
