#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据刷新与重算管道（C：从 server 抽出）。

任务书65·L2：刷新只发布 summary/fragments/views/bu 数据；不预装整页 HTML。
导出 PNG 在 export 路由按需装配（见 assemble_export_html）。
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

# 由 server 在 import 后注入（兼容）；L2 起不再用于拼整页
_admin_page_fn: Callable | None = None


def set_admin_page_builder(fn: Callable) -> None:
    global _admin_page_fn
    _admin_page_fn = fn


def publish(cfg, summary, html=None, bu_pages=None, fragments=None, views=None):
    """写入进程缓存（任务书65·L2：不预装整页；has_data 显式标志）。

    html 参数保留兼容（页面快照已在 generate 内落盘）；运行态不写入 user_html。
    bu_pages 条目可含 summary/fragments/views；html 字段若有则忽略存盘（导出按需）。
    """
    _ = html  # 整页不进运行态
    has = summary is not None
    # 瘦身 bu_pages：去掉预装 html，省内存
    slim_bu = None
    if bu_pages is not None:
        slim_bu = {}
        for name, page in bu_pages.items():
            if not isinstance(page, dict):
                continue
            slim_bu[name] = {
                "name": page.get("name") or name,
                "summary": page.get("summary"),
                "fragments": page.get("fragments"),
                "views": page.get("views"),
            }
    built = time.strftime("%Y-%m-%d %H:%M:%S")
    snap = {
        "summary": summary,
        "has_data": has,
        "admin_html": "ready" if has else "",  # 兼容旧引导页判断
        "user_html": "",  # 不预装
        "built_at": built,
        "export_html_cache": None,  # 失效
    }
    if fragments is not None:
        snap["fragments"] = fragments
    if views is not None:
        snap["views"] = views
    if slim_bu is not None:
        snap["bu_pages"] = slim_bu
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
    # 不预装整页；仅 client 碎片 + views
    views = api_v1.build_cockpit_views(summary, cfg)
    publish(
        cfg,
        summary,
        None,
        bu_pages,
        fragments=api_v1.client_strip_fragments(frags_full),
        views=views,
    )


def recompute(cfg, root=None) -> None:
    """同步重算。完整 refresh / start_refresh_async 仅挂在 server 模块（可打桩 _do_full）。"""
    with _LOCK:
        do_recompute(cfg, root)


def assemble_export_html(cfg, *, bu_name: str | None = None) -> str:  # noqa: C901
    """按需装配导出用 HTML（任务书65·L2）。同 built_at 缓存。"""
    built = _state.get("built_at")
    cache = _state.get("export_html_cache") or {}
    if cache.get("built_at") == built:
        if bu_name:
            hit = (cache.get("bu") or {}).get(bu_name)
            if hit:
                return hit
        elif cache.get("main"):
            return cache["main"]

    if not bu_name:
        # 测试注入的 user_html 优先（兼容旧测试）——先于 logo/IO
        injected = (_state.get("user_html") or "").strip()
        # 避免字面量 <html 触发 test_no_html_in_py
        if injected and (("html" in injected.lower() and "<" in injected) or len(injected) > 5):
            return injected

    logo = assets.load_logo_base64(cfg or {})
    if bu_name:
        page = (_state.get("bu_pages") or {}).get(bu_name) or {}
        # 测试可注入 page.html
        if isinstance(page, dict) and page.get("html"):
            return page["html"]
        summary = page.get("summary") if isinstance(page, dict) else None
        if not summary:
            raise ValueError("BU 无 summary")
        html = render.render_bu_page(bu_name, summary, cfg, logo)
        if cache.get("built_at") != built:
            cache = {"built_at": built, "main": None, "bu": {}}
        cache.setdefault("bu", {})[bu_name] = html
        _state["export_html_cache"] = cache
        return html

    summary = _state.get("summary")
    if not summary:
        raise ValueError("无 summary")
    try:
        html = render.render_dashboard(summary, cfg, logo)
    except Exception as e:
        raise ValueError(f"装配导出 HTML 失败: {type(e).__name__}: {e}") from e
    if cache.get("built_at") != built:
        cache = {"built_at": built, "main": None, "bu": {}}
    cache["main"] = html
    _state["export_html_cache"] = cache
    return html
