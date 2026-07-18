#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试公共引导（唯一入口）。

B-P5 后生产固定 shell+fragments，无 SERVE_SHELL 化石开关。
HTTP 测试断言页面内容请走：
  - `/api/v1/cockpit/fragments` / `/api/v1/cockpit/bu/{name}/fragments`
    · fragments 卡字段须为空（client strip）
    · 内容在 views.kpi_body / views.rankings_view 等
  - 或直接读 `server._state["user_html"]` / `bu_pages[n]["html"]`
由 tests/run_test.py 在加载任意测试脚本前 import。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 任务书54.4·C：默认 vue（看端仅 dist）；需测旧壳时显式 KANBAN_FRONTEND=legacy（壳已删后应 410）
import os as _os

_os.environ.setdefault("KANBAN_FRONTEND", "vue")

import server  # noqa: E402,F401


def fake_views(mark: str = "USER-MAIN", year_key: str = "2026年") -> dict:
    """测试用 views：标记放在 kpi_body（HTTP strip 后仍可在 views 读到）。"""
    return {
        "year_key": year_key,
        "period_keys": [year_key],
        "rankings_view": {
            year_key: {
                "visible": True,
                "start": "",
                "end": "",
                "sales": {"title": "", "dim": "sales", "items": [], "others": None, "empty": True},
                "customer": {"title": "", "dim": "customer", "items": [], "others": None, "empty": True},
            }
        },
        "kpi_body": {year_key: mark},
        "pl_body": {year_key: ""},
        "donut_body": {year_key: ""},
        "profit_rank_body": {year_key: ""},
        "trend_html": "",
        "receipts_budget": "",
        "period_bar": "",
        "daily_html": "",
    }


def fake_main_frags(mark: str = "USER-MAIN") -> dict:
    """模拟 publish 缓存：卡字段有预拼串（HTTP 必须 strip 掉）。"""
    keys = (
        "title",
        "particles",
        "logo",
        "version",
        "generated_at",
        "pw_modal",
        "period_bar",
        "kpi_views",
        "trend_html",
        "donut_views",
        "pl_views",
        "profit_rank_views",
        "receipts_budget",
        "daily_html",
        "rank_views",
        "expense_trend_html",
        "drawer",
    )
    fr = {k: "" for k in keys}
    fr["title"] = "甲骨易智能经营罗盘"
    fr["kpi_views"] = mark  # 预拼；HTTP 须清空
    return fr


def fake_bu_page(name: str, mark: str) -> dict:
    fr = {
        "title": f"甲骨易智能经营罗盘 · {name}",
        "particles": "",
        "logo": "",
        "name": name,
        "version": "",
        "generated_at": "",
        "export_url": f"/bu/{name}/export.png",
        "pw_modal": "",
        "period_bar": "",
        "kpi_views": mark,
        "trend_html": "",
        "donut_views": "",
        "pl_tag": "",
        "pl_views": "",
        "profit_rank_views": "",
        "receipts_html": "",
        "daily_html": "",
        "rank_views": "",
        "expense_trend_html": "",
        "drawer": "",
        "rk_modal": "",
    }
    return {
        "name": name,
        "html": f'<html><div class="wrap">{mark}</div></html>',
        "fragments": fr,
        "views": fake_views(mark),
        "summary": {"meta": {"year": 2026, "year_key": "2026年"}, "periods": {}},
    }
