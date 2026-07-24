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

# 2.6.0：唯一会话 cookie（OWASP：HttpOnly + SameSite；不硬开 Secure——外网仍 HTTP）
SID_COOKIE = "kanban_sid"
# 遗留名：兼容读 21 天（见 session_ctx）；登录不再写入
COOKIE = "kanban_session"  # legacy admin
VCOOKIE = "kanban_view"  # legacy viewer
SESSION_TTL = 12 * 3600  # 任务书63·H-05/H-06 过渡：管理端会话 ≤12h
SESSION_LEGACY_COMPAT_DAYS = 21
# 兼容锚点文件名（相对 data_dir）：内容 YYYY-MM-DD = 2.6.0 上生产日
SESSION_LEGACY_COMPAT_SINCE_FILE = "session_legacy_compat_since.txt"

# 服务内存态：汇总 + 碎片 + 原始记录（秒级重算）+ 刷新状态
# publish-once：fragments=已 strip 的 client 碎片；views=client-ready（HTTP 直接取，不再 rebuild）
# 任务书65·L2：不再每次刷新预装整页 HTML；user_html 仅兼容/测试缓存；导出按需装配。
_state: dict = {
    "summary": None,
    "user_html": "",  # 默认空；导出按需装配；测试可注入短串
    "admin_html": "",  # 兼容旧「有数据」标记；以 has_data 为准
    "has_data": False,
    "built_at": None,
    "records": None,
    "refreshing": None,
    "last_refresh": None,
    "bu_pages": {},  # {name: {summary,fragments,views}}；html 按需
    "fragments": None,
    "views": None,
    # 导出 HTML 缓存：同 built_at 复用，防连点
    "export_html_cache": None,  # {"built_at": str, "main": str, "bu": {name: html}}
}
_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()
