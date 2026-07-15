#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试公共引导（唯一入口）。

B-P5 后生产固定 shell+fragments，无 SERVE_SHELL 化石开关。
HTTP 测试断言页面内容请走：
  - `/api/v1/cockpit/fragments` / `/api/v1/cockpit/bu/{name}/fragments`
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

import server  # noqa: E402,F401


def fake_main_frags(mark: str = "USER-MAIN") -> dict:
    keys = (
        "title", "particles", "logo", "version", "generated_at", "pw_modal",
        "period_bar", "kpi_views", "trend_html", "donut_views", "pl_views",
        "profit_rank_views", "receipts_budget", "daily_html", "rank_views", "drawer",
    )
    fr = {k: "" for k in keys}
    fr["title"] = "甲骨易智能经营罗盘"
    fr["kpi_views"] = mark
    return fr


def fake_bu_page(name: str, mark: str) -> dict:
    fr = {
        "title": f"甲骨易智能经营罗盘 · {name}",
        "particles": "", "logo": "", "name": name, "version": "",
        "generated_at": "", "export_url": f"/bu/{name}/export.png",
        "pw_modal": "", "period_bar": "", "kpi_views": mark,
        "trend_html": "", "donut_views": "", "pl_tag": "", "pl_views": "",
        "profit_rank_views": "", "receipts_html": "", "rank_views": "",
        "drawer": "", "rk_modal": "",
    }
    return {
        "name": name,
        "html": f'<html><div class="wrap">{mark}</div></html>',
        "fragments": fr,
        "summary": {"meta": {"year": 2026, "year_key": "2026年"}, "periods": {}},
    }
