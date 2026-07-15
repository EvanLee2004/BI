#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据刷新与重算管道（C：从 server 抽出）。

依赖：core/ingest/render/db/assets + app_state；
admin 页拼装通过 publish_hook 注入（避免环依赖 server._admin_page）。
"""
from __future__ import annotations

import threading
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
    """写入进程缓存。fragments/views 应为 client-ready（fragments 已 strip）。"""
    _state["summary"] = summary
    _state["user_html"] = html
    if fragments is not None:
        _state["fragments"] = fragments
    if views is not None:
        _state["views"] = views
    if _admin_page_fn is not None:
        _state["admin_html"] = _admin_page_fn(html, summary, cfg)
    else:
        _state["admin_html"] = _state.get("admin_html") or ""
    if bu_pages is not None:
        _state["bu_pages"] = bu_pages
    _state["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    summary, html, ing, bu_pages = core.generate(cfg, today, trigger=trigger)
    _state["records"] = ing.get("records")
    publish(
        cfg, summary, html, bu_pages,
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
        cfg, summary, html, bu_pages,
        fragments=api_v1.client_strip_fragments(frags_full),
        views=views,
    )


def refresh(cfg, root=None, trigger="manual") -> dict:
    with _LOCK:
        return do_full(cfg, root, trigger)


def start_refresh_async(cfg, root=None, trigger="manual") -> bool:
    if not _LOCK.acquire(blocking=False):
        return False
    _state["refreshing"] = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger}

    def _job():
        t0 = time.time()
        try:
            ing = do_full(cfg, root, trigger)
            _state["last_refresh"] = {
                "status": "ok", "result": ing.get("result"),
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            _state["last_refresh"] = {
                "status": "error", "detail": f"{type(e).__name__}: {e}",
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        finally:
            _state["refreshing"] = None
            _LOCK.release()

    threading.Thread(target=_job, daemon=True).start()
    return True


def recompute(cfg, root=None) -> None:
    with _LOCK:
        do_recompute(cfg, root)
