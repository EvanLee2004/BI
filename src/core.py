#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心生成流程（run.py 批处理 与 server.py 服务 共用）：跑更新管道 → 算 summary → 渲染 HTML。
独立成模块以免 run↔server 循环导入。"""
from __future__ import annotations

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


def generate(cfg, today, trigger="manual"):
    """跑一次更新管道 → 算 summary → 渲染 HTML → 存当日页面快照（历史回看用）。
    返回 (summary, html, ing报告)。"""
    conn = db.connect(cfg)
    ing = ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger=trigger,
                              archive_backups=True)
    summary = summary_from_conn(cfg, conn, today)
    conn.close()
    html = render.render_dashboard(summary, cfg, assets.load_logo_base64(cfg))
    try:  # 页面快照失败（磁盘满等）不影响出页面
        ing["page_snapshot"] = ingest.archive.snapshot_page(cfg, html, today)
    except OSError as e:
        ing["page_snapshot"] = {"status": "error", "detail": str(e)}
    return summary, html, ing
