#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心生成流程（run.py 批处理 与 server.py 服务 共用）：跑更新管道 → 算 summary → 渲染 HTML。
独立成模块以免 run↔server 循环导入。"""
from __future__ import annotations

import bu
import profit
import render
import assets
import db
import ingest


def summary_from_conn(cfg, conn, today):
    """计算层只吃库：标准表 + 手填表 → summary（profit 不再自己扫文件）。"""
    return profit.build_summary(
        cfg, db.load_project_detail(cfg, conn), db.load_orders(cfg, conn),
        db.load_receipts(cfg, conn), db.load_inhouse(cfg, conn),
        *db.load_ledger(cfg, conn), today.year, today,
        manual_raw=db.load_manual(cfg, conn), budget_raw=db.load_budget(conn),
        dept_budget_raw=db.load_dept_budget(conn))


def build_bu_pages(cfg, conn, today, logo_b64, root=None) -> dict[str, dict]:
    """BU 分页（迭代 14·v7.9 账号制）：读 BU 配置 → 每 BU 按销售名单过滤四源行 → 独立 summary → 独立 HTML。
    返回 {BU名: {"name": BU名, "html": 页面}}；没配置/配置无效 → {}（功能不启用，主看板照旧）。
    严格保密由此保证：每页只吃本 BU 过滤后的行，渲染层拿不到其他 BU 的任何数据。"""
    bucfg = bu.load_bu_config(cfg, root)
    if not bucfg:
        return {}
    project = db.load_project_detail(cfg, conn)
    orders = db.load_orders(cfg, conn)
    receipts = db.load_receipts(cfg, conn)
    inhouse = db.load_inhouse(cfg, conn)
    pages: dict[str, dict] = {}
    for b in bucfg["bus"]:
        s = profit.build_bu_summary(cfg, project, orders, receipts, inhouse, today, set(b["销售"]))
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
    conn.close()
    html = render.render_dashboard(summary, cfg, logo)
    try:  # 页面快照失败（磁盘满等）不影响出页面
        ing["page_snapshot"] = ingest.archive.snapshot_page(cfg, html, today)
    except OSError as e:
        ing["page_snapshot"] = {"status": "error", "detail": str(e)}
    return summary, html, ing, bu_pages
