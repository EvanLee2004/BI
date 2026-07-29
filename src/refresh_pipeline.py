#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据刷新与重算管道（C：从 server 抽出）。

任务书65·L2：刷新只发布 summary/views/bu 数据；不预装整页 HTML。
2.7.7 G2：刷新不再 build_dashboard_fragments；SPA 只靠 VM；导出按需装配。
"""

from __future__ import annotations

import time
from typing import Callable

import assets
import core
import db
import ingest
import loaders
from app_state import _LOCK, _state

# 由 server 在 import 后注入（兼容）；L2 起不再用于拼整页
_admin_page_fn: Callable | None = None


def set_admin_page_builder(fn: Callable) -> None:
    global _admin_page_fn
    _admin_page_fn = fn


def publish(cfg, summary, html=None, bu_pages=None, fragments=None, views=None):
    """写入进程缓存（3.1.0：只发 summary/views/bu_pages；不预装整页/HTML 碎片）。

    html / fragments 参数吞掉（兼容旧调用），运行态不写入。
    bu_pages 条目只保留 name/summary/views。

    2.6.3·C2：构造完整快照 dict 后 **一次引用替换** 发布字段，避免逐键 update
    导致读侧拿到「新 summary + 旧 views」撕裂窗口。
    """
    _ = html, fragments  # 整页/HTML 碎片不进运行态
    has = summary is not None
    slim_bu = None
    if bu_pages is not None:
        slim_bu = {}
        for name, page in bu_pages.items():
            if not isinstance(page, dict):
                continue
            slim_bu[name] = {
                "name": page.get("name") or name,
                "summary": page.get("summary"),
                "views": page.get("views"),
            }
    built = time.strftime("%Y-%m-%d %H:%M:%S")
    prev = dict(_state)
    snap = {
        **prev,
        "summary": summary,
        "has_data": has,
        "admin_html": "ready" if has else "",  # 兼容旧引导页判断
        "user_html": "",  # 不预装
        "built_at": built,
        "export_html_cache": None,  # 失效
    }
    # 去掉历史 fragments 键（若旧进程态残留）
    snap.pop("fragments", None)
    if views is not None:
        snap["views"] = views
    if slim_bu is not None:
        snap["bu_pages"] = slim_bu    # 2.6.7 C-2：原子替换——先构造新 dict，再整体 swap，避免 clear→update 空窗
    # _state 是模块级可变 dict：用 clear+update 但先在 snap 上凑齐后一次写入键集合
    # 真正无空窗：替换引用（若 _state 被其他模块 from-import 绑死则退化为 bulk update without clear）
    import app_state as _as

    if getattr(_as, "_state", None) is _state:
        # 同对象：用新映射覆盖键，不 clear
        stale = [k for k in list(_state.keys()) if k not in snap]
        _state.update(snap)
        for k in stale:
            _state.pop(k, None)
    else:
        _state.clear()
        _state.update(snap)


def snapshot_state() -> dict:
    """2.6.3·C2：读侧一次取引用副本，避免跨键撕裂。"""
    return dict(_state)


def _fp_parts(paths) -> list[str]:
    parts = []
    for p in paths:
        try:
            st = p.stat()
            parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{p.name}:missing")
    return parts


def source_data_fingerprint(cfg, root=None) -> str:
    """数据源指纹：喂 std 的本地文件 mtime+size（任务书66·B）。"""
    from pathlib import Path

    try:
        data = loaders.data_dir(cfg, root)
    except Exception:
        data = Path(cfg.get("data_dir") or "数据")
    seen: set[Path] = set()
    paths: list[Path] = []
    for key in ("ledger", "orders", "receipts", "inhouse", "project", "project_detail"):
        name = ((cfg or {}).get("files") or {}).get(key)
        if not name:
            continue
        p = data / name
        if p.is_file() and p not in seen:
            seen.add(p)
            paths.append(p)
    if data.is_dir():
        for pat in ("*.xlsx", "zhiyun_*.json"):
            for p in sorted(data.glob(pat)):
                if p not in seen:
                    seen.add(p)
                    paths.append(p)
    parts = _fp_parts(paths)
    return "|".join(parts) if parts else "empty"


def do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    # 2.6.3·C3：root 贯通 generate，禁止默认落到程序 数据/
    summary, html, ing, bu_pages = core.generate(cfg, today, trigger=trigger, root=root)
    _state["records"] = ing.get("records")
    _state["source_fp"] = source_data_fingerprint(cfg, root)
    # 3.1.0：仅 views + summary（不 publish HTML fragments）
    summary.pop("_fragments", None)
    publish(
        cfg,
        summary,
        html,
        bu_pages,
        views=summary.pop("_views", None) or _state.get("views"),
    )
    return ing


def do_recompute(cfg, root, *, rebuild_std: bool = False) -> None:
    """手填/配置后重算。

    任务书66·B：
    - 源文件指纹变了 → 全量 do_full
    - rebuild_std=True（调整写入）→ reapply（重建 std+重放调整）→ summary
    - 默认（手填/预算/分摊/去税）→ **跳过 std 重建**，只 summary→publish
    """
    if not _state.get("records"):
        do_full(cfg, root, "manual")
        return
    fp = source_data_fingerprint(cfg, root)
    if fp != _state.get("source_fp"):
        do_full(cfg, root, "manual")
        return
    import api_v1

    today = loaders.pinned_today(cfg)
    logo = assets.load_logo_base64(cfg)
    conn = db.connect(cfg, root)
    try:
        if rebuild_std:
            ingest.reapply(cfg, conn, _state["records"], today)
        summary = core.summary_from_conn(cfg, conn, today)
        bu_pages = core.build_bu_pages(cfg, conn, today, logo, root)
        core.attach_unassigned(cfg, conn, today, summary, root)
    finally:
        conn.close()
    # 3.1.0 / G4：生产 JSON views only；禁 HTML 装运
    views = api_v1.build_json_views(summary, cfg)
    publish(
        cfg,
        summary,
        None,
        bu_pages,
        views=views,
    )


def recompute(cfg, root=None, *, rebuild_std: bool = False, already_locked: bool = False) -> None:
    """同步重算。调整类写入传 rebuild_std=True；手填默认 False。

    already_locked=True：调用方已持有 _LOCK（2.6.3·C1 with_write_lock），不再 acquire，避免死锁。
    """
    if already_locked:
        do_recompute(cfg, root, rebuild_std=rebuild_std)
        return
    with _LOCK:
        do_recompute(cfg, root, rebuild_std=rebuild_std)


# 3.1.0：导出走 export_html.assemble_export_pack + build_export_html（routes/export.py）；
# 已删除误导名 assemble_export_html。
