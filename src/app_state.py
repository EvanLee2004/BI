#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内看板缓存与锁（C：从 server 抽出；行为零变）。

依赖铁律：本模块不 import render/profit/core（避免环依赖）。
server / refresh_pipeline / 路由读同一套 _state。
"""
from __future__ import annotations

import threading
from pathlib import Path

# v1.4 静态资源根：与 run.py 同级 static/
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# B-P5：不再提供 SERVE_SHELL 化石开关；看端固定 shell + fragments。

COOKIE = "kanban_session"
VCOOKIE = "kanban_view"
SESSION_TTL = 24 * 3600

# 服务内存态：汇总 + 渲染页 + 碎片 + 原始记录（秒级重算）+ 刷新状态
_state: dict = {
    "summary": None,
    "user_html": "",
    "admin_html": "",
    "built_at": None,
    "records": None,
    "refreshing": None,
    "last_refresh": None,
    "bu_pages": {},
    "fragments": None,
}
_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()
