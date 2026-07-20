#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据刷新与重算管道（C：从 server 抽出）。

依赖：core/ingest/render/db/assets + app_state；
admin 页拼装通过 publish_hook 注入（避免环依赖 server._admin_page）。
"""

from __future__ import annotations

import time
from typing import Callable

import assets
import core
import db
import ingest
import loaders
import render
from app_state import _LOCK, _state

# 由 server 在 import 后注入：publish 时拼 admin_html
_admin_page_fn: Callable | None = None


def set_admin_page_builder(fn: Callable) -> None:
    global _admin_page_fn
    _admin_page_fn = fn


def publish(cfg, summary, html, bu_pages=None, fragments=None, views=None):
    """写入进程缓存（任务书64·D3：构造完整快照后单次 update，避免键撕裂）。

    fragments/views 应为 client-ready（fragments 已 strip）。
    路由应一次取用 `_state.get(...)` 或拷贝引用，勿在请求内多次读混用新旧。
    """
    if _admin_page_fn is not None:
        admin_html = _admin_page_fn(html, summary, cfg)
    else:
        admin_html = _state.get("admin_html") or ""
    snap = {
        "summary": summary,
        "user_html": html,
        "admin_html": admin_html,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if fragments is not None:
        snap["fragments"] = fragments
    if views is not None:
        snap["views"] = views
    if bu_pages is not None:
        snap["bu_pages"] = bu_pages
    # 单次引用替换语义：dict.update 在 CPython 下对已有键逐个赋值，
    # 发布键集合在此快照内一致；records/refreshing/last_refresh 不在此批。
    _state.update(snap)


def do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    summary, html, ing, bu_pages = core.generate(cfg, today, trigger=trigger)
    _state["records"] = ing.get("records")
    publish(
        cfg,
        summary,
        html,
        bu_pages,
        fragments=summary.pop("_fragments", None) or _state.get("fragments"),
        views=summary.pop("_views", None) or _state.get("views"),
    )
    return ing


def do_recompute(cfg, root) -> None:
    if not _state.get("records"):
        do_full(cfg, root, "manual")
        return
    import api_v1

    today = loaders.pinned_today(cfg)
    logo = assets.load_logo_base64(cfg)
    conn = db.connect(cfg, root)
    try:
        ingest.reapply(cfg, conn, _state["records"], today)
        summary = core.summary_from_conn(cfg, conn, today)
        bu_pages = core.build_bu_pages(cfg, conn, today, logo, root)
        core.attach_unassigned(cfg, conn, today, summary, root)
    finally:
        conn.close()
    frags_full = render.build_dashboard_fragments(summary, cfg, logo)
    html = render.assemble_dashboard_html(frags_full)
    views = api_v1.build_cockpit_views(summary, cfg)
    publish(
        cfg,
        summary,
        html,
        bu_pages,
        fragments=api_v1.client_strip_fragments(frags_full),
        views=views,
    )


def recompute(cfg, root=None) -> None:
    """同步重算。完整 refresh / start_refresh_async 仅挂在 server 模块（可打桩 _do_full）。"""
    with _LOCK:
        do_recompute(cfg, root)
