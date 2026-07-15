#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内看板缓存与开关（C 阶段从 server 抽出；行为零变）。"""
from __future__ import annotations

import threading
from pathlib import Path

# v1.4 静态资源根：与 run.py 同级 static/
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
# 已登录整体页是否走 shell.html（fetch 像素级 HTML）。生产默认 True；测试引导入口置 False。
SERVE_SHELL: bool = True

COOKIE = "kanban_session"
VCOOKIE = "kanban_view"
SESSION_TTL = 24 * 3600

_state: dict = {
    "summary": None, "user_html": "", "admin_html": "", "built_at": None, "records": None,
    "refreshing": None, "last_refresh": None, "bu_pages": {},
}
_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()
