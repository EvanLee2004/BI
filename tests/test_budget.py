#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年度预算（P-A）：db 读写留痕 / summary budget 块有无 / 渲染开关（没填数页面一分不变=红线）。"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db  # noqa: E402
import schema  # noqa: E402
from profit import build_budget_block  # noqa: E402


def mem_conn():
    conn = sqlite3.connect(":memory:")
    for ddl in list(schema.STD_TABLES.values()) + list(schema.HUMAN_TABLES.values()):
        conn.execute(ddl)
    return conn


class TestBudgetDb(unittest.TestCase):
    def test_set_get_and_history(self):
        conn = mem_conn()
        db.set_budget(conn, "2026", "下单年预算", 8000_0000, "明昊")
        db.set_budget(conn, "2026", "下单年预算", 9000_0000, "陆总")  # 年中改一次
        rows = db.get_budget(conn, "2026")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["金额"], 9000_0000)
        self.assertEqual(rows[0]["经手人"], "陆总")
        hist = conn.execute("SELECT 旧值,新值 FROM manual_预算历史 ORDER BY id").fetchall()
        self.assertEqual(hist, [(None, 8000_0000), (8000_0000, 9000_0000)])

    def test_load_budget_shape_and_scope(self):
        conn = mem_conn()
        db.set_budget(conn, "2026", "回款年预算", 100.0, "明昊")
        db.set_budget(conn, "2026", "回款年预算", 999.0, "明昊", 范围="语言")  # BU 目标
        self.assertEqual(db.load_budget(conn), {"2026": {"回款年预算": 100.0}})
        self.assertEqual(db.load_budget(conn, scope="语言"), {"2026": {"回款年预算": 999.0}})

    def test_empty(self):
        conn = mem_conn()
        self.assertEqual(db.load_budget(conn), {})
        self.assertEqual(db.get_budget(conn), [])


class TestBudgetBlock(unittest.TestCase):
    YEAR_P = {"orders": 500.0, "receipts": 300.0, "gross_margin_pct": 40.0}

    def test_none_when_not_filled(self):
        self.assertIsNone(build_budget_block(None, 2026, self.YEAR_P))
        self.assertIsNone(build_budget_block({}, 2026, self.YEAR_P))
        self.assertIsNone(build_budget_block({"2025": {"下单年预算": 1}}, 2026, self.YEAR_P))  # 别的年份不串

    def test_pct(self):
        b = build_budget_block({"2026": {"下单年预算": 1000.0, "回款年预算": 600.0}}, 2026, self.YEAR_P)
        self.assertAlmostEqual(b["order"]["pct"], 50.0)
        self.assertAlmostEqual(b["receipt"]["pct"], 50.0)
        self.assertEqual(b["order"]["done"], 500.0)

    def test_partial_and_zero_target(self):
        b = build_budget_block({"2026": {"回款年预算": 0.0}}, 2026, self.YEAR_P)
        self.assertIsNone(b["order"])            # 没填下单 → 该项 None
        self.assertIsNone(b["receipt"]["pct"])   # 目标 0 → 完成率 None 不除零


class TestRenderSwitch(unittest.TestCase):
    def test_no_budget_renders_identical(self):
        """红线：没填预算时，回款卡 HTML 与传 None 完全一致（页面一分不变）。"""
        import render
        series = [("1月", 10.0, 20.0, 50.0), ("2月", 12.0, 24.0, 50.0)]
        self.assertEqual(render.render_receipts(series, None), render.render_receipts(series))
        self.assertNotIn("预算", render.render_receipts(series, None))

    def test_budget_renders_line_and_tag(self):
        import render
        series = [("1月", 10.0, 20.0, 50.0), ("2月", 12.0, 24.0, 50.0)]
        budget = {"year": 2026,
                  "order": {"target": 1200.0, "done": 600.0, "pct": 50.0},
                  "receipt": {"target": 2400.0, "done": 600.0, "pct": 25.0}}
        html = render.render_receipts(series, budget)
        self.assertIn("月均预算", html)          # 图上预算线（2400/12=200万/月）
        self.assertIn("回款年预算", html)
        self.assertIn("25.0%", html)
        self.assertIn("下单年预算", html)


class TestBudgetFollowsTopFilter(unittest.TestCase):
    """业绩目标改跟顶部统一「范围/年份」（明昊 2026-07-14）：管理端控制台不再有独立的 bY/bScope 下拉。"""
    def test_console_has_no_own_budget_selectors(self):
        import server
        tpl = server.admin_ui_source()
        self.assertNotIn('id="bY"', tpl)
        self.assertNotIn('id="bScope"', tpl)
        self.assertNotIn("bFillScopes", tpl)
        self.assertIn("跟随顶部", tpl)                       # 说明文案已改
        # bLoad 取顶部 mY/mScope（不再读自有下拉）
        i = tpl.find("async function bLoad(")
        self.assertNotEqual(i, -1)
        body = tpl[i:i + 400]
        self.assertIn('getElementById("mY")', body)
        self.assertIn('getElementById("mScope")', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
