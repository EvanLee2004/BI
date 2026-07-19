#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书56·R-45：费用明细默认期间费用口径 + 显示全部开关。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.expense.chart_whitelist import (  # noqa: E402
    merge_ledger_caliber_filters,
    period_expense_chart_categories,
)


class TestLedgerCaliberR45(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "expense_categories_included": ["销售费用", "管理费用", "研发费用", "财务费用", "固定费用"],
            "expense_categories_excluded": ["成本", "非利润表"],
        }

    def test_default_excludes_cost_and_non_pl(self):
        out = merge_ledger_caliber_filters(None, self.cfg, show_all=False)
        self.assertIsInstance(out, str)
        f = json.loads(out)
        cats = f["对应报表大类"]["in"]
        self.assertNotIn("成本", cats)
        self.assertNotIn("非利润表", cats)
        self.assertIn("销售费用", cats)
        self.assertIn("其他", cats)

    def test_show_all_passthrough(self):
        raw = json.dumps({"事项": {"q": "差旅"}}, ensure_ascii=False)
        self.assertEqual(merge_ledger_caliber_filters(raw, {}, show_all=True), raw)
        self.assertIsNone(merge_ledger_caliber_filters(None, {}, show_all=True))

    def test_intersects_user_in_filter(self):
        raw = {"对应报表大类": {"in": ["销售费用", "成本"]}}
        out = merge_ledger_caliber_filters(raw, self.cfg, show_all=False)
        self.assertIsInstance(out, dict)
        self.assertEqual(out["对应报表大类"]["in"], ["销售费用"])

    def test_period_expense_categories_ban_cost(self):
        cfg = {"expense_categories_included": ["销售费用", "成本", "非利润表"]}
        cats = period_expense_chart_categories(cfg)
        self.assertNotIn("成本", cats)
        self.assertNotIn("非利润表", cats)
        self.assertIn("销售费用", cats)


if __name__ == "__main__":
    unittest.main()
