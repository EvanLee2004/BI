#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试公共引导（唯一入口）。

3.2.0：生产固定 Vue SPA + /api/v1/vm/*；无 SERVE_SHELL / fragments 装运 / user_html。
HTTP 测试断言请走：
  - `/api/v1/vm/*` 与 `has_data` / `summary` / `views.rankings_view`
  - 读 `server._state["summary"]` / views；导出走 snapshot
由 tests/run_test.py 在加载任意测试脚本前 import。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 默认 vue（看端仅 dist）
import os as _os

_os.environ.setdefault("KANBAN_FRONTEND", "vue")

import server  # noqa: E402,F401


def fake_views(mark: str = "USER-MAIN", year_key: str = "2026年") -> dict:
    """测试用 views：标记放在 rankings_view.sales.title（生产 JSON 真字段）。"""
    return {
        "year_key": year_key,
        "period_keys": [year_key],
        "rankings_view": {
            year_key: {
                "visible": True,
                "start": "",
                "end": "",
                "sales": {
                    "title": mark,
                    "dim": "sales",
                    "items": [],
                    "others": None,
                    "empty": True,
                },
                "customer": {
                    "title": "",
                    "dim": "customer",
                    "items": [],
                    "others": None,
                    "empty": True,
                },
            }
        },
        "rankings_monthly_data": {},
    }


def fake_main_frags(mark: str = "USER-MAIN") -> dict:
    """遗留 fragments 形状（仅供断言 404/墓碑路径的测试预置；生产不再 publish）。"""
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
    fr["title"] = "甲骨易经营看板"
    fr["kpi_views"] = mark
    return fr


def fake_bu_page(name: str, mark: str) -> dict:
    """BU 页测试预置：name/summary/views（3.2.0 publish 只保留这三项）。"""
    return {
        "name": name,
        "views": fake_views(mark),
        "summary": {"meta": {"year": 2026, "year_key": "2026年"}, "periods": {}},
    }
