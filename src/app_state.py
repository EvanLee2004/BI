#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内看板缓存与锁（C：从 server 抽出；行为零变）。

依赖铁律：本模块不装载 HTML 装运层 / profit / core（避免环依赖）。
server / refresh_pipeline / 路由读同一套 _state。
"""

from __future__ import annotations

import threading
from pathlib import Path

# v1.4 静态资源根：与 run.py 同级 static/
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 3.1.0：看端 Vue + /api/v1/vm/*；无 SERVE_SHELL / fragments 装运。

# 2.7.1：唯一会话 cookie（OWASP：HttpOnly + SameSite；不硬开 Secure——外网仍 HTTP）
SID_COOKIE = "kanban_sid"
# 遗留名：2.7.1 起不再读；登录/退出时 delete 清浏览器残留
COOKIE = "kanban_session"  # legacy name — delete only
VCOOKIE = "kanban_view"  # legacy name — delete only
SESSION_TTL = 7 * 24 * 3600  # 3.7.20：统一 7 天（原 12h / 任务书63）

# 服务内存态：summary + views + bu_pages；不预装整页 HTML。
# 3.2.0：无 user_html；有 summary/has_data 即 ready。导出走 kanban_snapshot。
_state: dict = {
    "summary": None,
    "admin_html": "",  # 兼容旧「有数据」标记；以 has_data 为准
    "has_data": False,
    "built_at": None,
    "records": None,
    "refreshing": None,
    "last_refresh": None,
    "bu_pages": {},  # {name: {name, summary, views}}
    "views": None,
    # 导出 HTML 缓存：同 built_at 复用，防连点
    "export_html_cache": None,  # {"built_at": str, "main": str, "bu": {name: html}}
    # BE-005：publish 写入的一致读包 {summary, views, bu_pages, built_at, has_data}
    "pub": None,
}
# 注意：start_refresh_async 主线程 acquire、后台线程 release → 必须用 Lock 不能用 RLock
_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()


def published_snapshot() -> dict:
    """BE-005：读侧一致视图。优先 pub 包；否则从扁平键组装（兼容未 publish 冷态）。"""
    pub = _state.get("pub")
    if isinstance(pub, dict) and pub.get("built_at") is not None:
        return dict(pub)
    return {
        "summary": _state.get("summary"),
        "views": _state.get("views"),
        "bu_pages": _state.get("bu_pages") or {},
        "built_at": _state.get("built_at"),
        "has_data": bool(_state.get("has_data")),
    }
