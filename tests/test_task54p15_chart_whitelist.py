#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.15 R-30：费用两图白名单剔「成本」；环形/PL 不受影响（结构测）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.expense.chart_whitelist import (  # noqa: E402
    filter_expense_monthly_raw_for_charts,
    period_expense_chart_categories,
)


class TestChartWhitelist(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "expense_categories_included": ["市场费用", "管理费用", "固定运营费用", "技术服务费", "财务费用", "其他"],
            "expense_categories_excluded": ["成本", "非利润表", "工资"],
        }

    def test_ban_cost(self):
        cats = period_expense_chart_categories(self.cfg, ["市场费用", "成本", "管理费用", "非利润表", "其他"])
        self.assertEqual(cats, ["市场费用", "管理费用", "其他"])
        self.assertNotIn("成本", cats)

    def test_filter_raw_recomputes_total(self):
        raw = {
            "categories": ["市场费用", "成本", "管理费用"],
            "months": [
                {"m": 1, "total": 300, "by_cat": {"市场费用": 100, "成本": 150, "管理费用": 50}},
            ],
        }
        out = filter_expense_monthly_raw_for_charts(raw, self.cfg)
        self.assertNotIn("成本", out["categories"])
        self.assertAlmostEqual(out["months"][0]["total"], 150.0)
        self.assertNotIn("成本", out["months"][0]["by_cat"])

    def test_single_module_source(self):
        """白名单只在 chart_whitelist 一处定义（防两图各写一份）。"""
        text = (ROOT / "src" / "viewmodels" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("filter_expense_monthly_raw_for_charts", text)
        self.assertIn("chart_whitelist", text)


if __name__ == "__main__":
    unittest.main()
