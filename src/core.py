#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心生成流程（run.py 批处理 与 server.py 服务 共用）：跑更新管道 → 算 summary → 渲染 HTML。
独立成模块以免 run↔server 循环导入。"""
from __future__ import annotations

import bu
import profit
import render
import charts
import assets
import db
import ingest


def _assigned_sales(bucfg) -> set[str]:
    """所有 BU 名单里的销售名（去空白去空）。未配置 → 空集。"""
    out: set[str] = set()
    for b in (bucfg or {}).get("bus", []):
        for s in b.get("销售") or []:
            s = str(s).strip()
            if s:
                out.add(s)
    return out


def _unassigned_wan(v: float) -> str:
    """未归属金额展示串（万，负数全角−；服务端算好=铁律2）。"""
    return "¥" + ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"


def unassigned_snapshot(cfg, conn, today, root=None) -> dict:
    """管理端 A3 快照（不依赖 summary）：未归属人数 + 当年未归属下单额展示串。
    未归属人数=四源出现、非空、不在任何 BU；金额=当年（含销售空行）未归属下单额（精确差额）。"""
    import datetime
    assigned = _assigned_sales(bu.load_bu_config(cfg, root))
    people = db.list_salespeople(conn)
    n = sum(1 for p in people if p["name"] not in assigned)
    unassigned = [r for r in db.load_orders(cfg, conn)
                  if str(r.get("销售") or "").strip() not in assigned]
    amt = profit.compute_orders(unassigned, cfg["columns"],
                                datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31))
    return {"unassigned_count": n, "unassigned_orders_disp": _unassigned_wan(amt)}


def attach_unassigned(cfg, conn, today, summary, root=None) -> None:
    """A3 未归属显式提示：把「未归属人数 + 每周期未归属下单金额展示串」挂进 summary.meta.unassigned。
    人数=四源出现过、非空、不在任何 BU 名单的销售数（与管理端归属池同口径）；N=0 → 整体页/管理端都不渲染该行。
    金额=每周期未归属销售（含销售空行）下单额，随周期预渲染供前端零运算切换。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg:
        # BU 分页未启用（没配任何 BU）→ 不提示、不判黄（整体页入口条本身也不出现）；
        # 管理端归属页仍显示真实未归属（走 unassigned_snapshot，那页正是用来配的）。
        summary.setdefault("meta", {})["unassigned"] = {"count": 0, "by_period": {}}
        return
    assigned = _assigned_sales(bucfg)
    people = db.list_salespeople(conn)                       # [{name(TRIM), rows}]
    n = sum(1 for p in people if p["name"] not in assigned)
    by_amt = profit.compute_unassigned_orders_by_period(
        db.load_orders(cfg, conn), assigned, cfg["columns"], today)
    summary.setdefault("meta", {})["unassigned"] = {
        "count": n,
        "by_period": {k: _unassigned_wan(v) for k, v in by_amt.items()},
    }


def summary_from_conn(cfg, conn, today):
    """计算层只吃库：标准表 + 手填表 → summary（profit 不再自己扫文件）。"""
    return profit.build_summary(
        cfg, db.load_project_detail(cfg, conn), db.load_orders(cfg, conn),
        db.load_receipts(cfg, conn), db.load_inhouse(cfg, conn),
        *db.load_ledger(cfg, conn), today.year, today,
        manual_raw=db.load_manual(cfg, conn), budget_raw=db.load_budget(conn),
        dept_budget_raw=db.load_dept_budget(conn))


def build_bu_pages(cfg, conn, today, logo_b64, root=None) -> dict[str, dict]:
    """BU 分页（迭代 14·v7.9 账号制 · 迭代17 分摊）：读 BU 配置 → 每 BU 按销售名单过滤四源行
    → 独立 summary（分摊开时注入全公司台账公共×比例）→ 独立 HTML。
    返回 {BU名: {"name": BU名, "html": 页面}}；没配置/配置无效 → {}（功能不启用，主看板照旧）。
    严格保密由此保证：每页只吃本 BU 过滤后的行，渲染层拿不到其他 BU 的任何数据。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg:
        return {}
    project = db.load_project_detail(cfg, conn)
    orders = db.load_orders(cfg, conn)
    receipts = db.load_receipts(cfg, conn)
    inhouse = db.load_inhouse(cfg, conn)
    alloc_on = bool(bucfg.get("公共费用分摊启用"))
    company_led = None
    if alloc_on:
        # 全公司台账公共费用（按周期）：只取 ledger_expenses，供各 BU × 比例
        lh, lr = db.load_ledger(cfg, conn)
        full = profit.build_summary(
            cfg, project, orders, receipts, inhouse, lh, lr, today.year, today,
            manual_raw={}, budget_raw=None, dept_budget_raw=None)
        company_led = {k: p.get("ledger_expenses") or {} for k, p in full["periods"].items()}
    pages: dict[str, dict] = {}
    for b in bucfg["bus"]:
        s = profit.build_bu_summary(
            cfg, project, orders, receipts, inhouse, today, set(b["销售"]),
            company_ledger_by_period=company_led,
            alloc_ratio_pct=b.get("分摊比例"),
            alloc_enabled=alloc_on)
        pages[b["name"]] = {"name": b["name"],
                            "html": render.render_bu_page(b["name"], s, cfg, logo_b64)}
    return pages


def generate(cfg, today, trigger="manual"):
    """跑一次更新管道 → 算 summary → 渲染 HTML（主页 + BU 分页）→ 存当日页面快照（历史回看用）。
    返回 (summary, html, ing报告, bu_pages)。"""
    conn = db.connect(cfg)
    ing = ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger=trigger,
                              archive_backups=True)
    summary = summary_from_conn(cfg, conn, today)
    logo = assets.load_logo_base64(cfg)
    bu_pages = build_bu_pages(cfg, conn, today, logo)
    attach_unassigned(cfg, conn, today, summary)
    conn.close()
    html = render.render_dashboard(summary, cfg, logo)
    try:  # 页面快照失败（磁盘满等）不影响出页面
        ing["page_snapshot"] = ingest.archive.snapshot_page(cfg, html, today)
    except OSError as e:
        ing["page_snapshot"] = {"status": "error", "detail": str(e)}
    return summary, html, ing, bu_pages
