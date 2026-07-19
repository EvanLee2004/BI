#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书57·B-6：domain 覆盖冲刺（kpi_target_bar / peak / 白名单边界）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.expense.chart_whitelist import (  # noqa: E402
    filter_expense_monthly_raw_for_charts,
    merge_ledger_caliber_filters,
    period_expense_chart_categories,
)
from domain.pl.structure import kpi_peak_for, kpi_target_bar  # noqa: E402


class TestDomainCoverageB6(unittest.TestCase):
    def test_kpi_target_bar_empty_and_amount(self):
        self.assertIsNone(kpi_target_bar(None, "2026年", {}, {}))
        self.assertIsNone(kpi_target_bar("order", "2026年", {}, None))
        # budget 空 dict 时：无 tkey 项 → empty 态
        bar = kpi_target_bar("order", "2026年", {"orders": 50}, {"order": None}) or kpi_target_bar(
            "order", "2026年", {"orders": 50}, {"other": 1}
        )
        # 无 order 键 → empty True
        bar = kpi_target_bar("order", "2026年", {"orders": 50}, {"x": 1})
        self.assertIsNotNone(bar)
        self.assertTrue(bar.get("empty"))
        budget = {"order": {"target": 100.0, "done": 50.0, "pct": 50.0}}
        bar2 = kpi_target_bar("order", "2026年", {"orders": 50}, budget)
        self.assertFalse(bar2["empty"])
        self.assertEqual(bar2["kind"], "amount")
        self.assertEqual(bar2["cls"], "low")

    def test_kpi_target_bar_h1_and_margin_and_over999(self):
        budget = {
            "order_h1": {"target": 40.0, "done": 40.0, "pct": 100.0},
            "margin": {"target": 30.0, "done": 30.0, "pct": 100.0},
            "pretax_margin": {"target": 10.0, "done": None, "pct": 1200.0},
        }
        b_h1 = kpi_target_bar("order", "2026年1-6月", {"orders": 40}, budget)
        self.assertEqual(b_h1["label"], "H1目标")
        self.assertEqual(b_h1["cls"], "ok")
        b_m = kpi_target_bar("margin", "2026年", {"gross_margin_pct": 30.0}, budget)
        self.assertEqual(b_m["kind"], "margin")
        b_pt = kpi_target_bar("pretax_margin", "2026年", {"pretax_margin_pct": 12.0}, budget)
        self.assertIn(">999", b_pt["pct_disp"])

    def test_kpi_peak_for(self):
        summary = {
            "meta": {"year": 2026, "tab_groups": {"月": ["2026年1月", "2026年2月"]}},
            "periods": {
                "2026年1月": {"orders": 10.0},
                "2026年2月": {"orders": 30.0},
            },
        }
        peak = kpi_peak_for(summary, "orders")
        self.assertIsNotNone(peak)
        self.assertEqual(peak["label"], "2月")
        self.assertTrue(str(peak["value_disp"]).endswith("万"))
        z = {
            "meta": {"year": 2026, "tab_groups": {"月": ["2026年1月"]}},
            "periods": {"2026年1月": {"orders": 0.0}},
        }
        self.assertIsNone(kpi_peak_for(z, "orders"))
        self.assertIsNone(kpi_peak_for({"meta": {}, "periods": {}}, "orders"))

    def test_whitelist_filter_empty_and_merge_str(self):
        cfg = {"expense_categories_included": ["管理费用"]}
        self.assertEqual(period_expense_chart_categories(cfg), ["管理费用", "其他"])
        out = filter_expense_monthly_raw_for_charts(None, cfg)
        self.assertEqual(out["categories"], [])
        # invalid json filters → still apply caliber
        merged = merge_ledger_caliber_filters("{not-json", cfg, show_all=False)
        self.assertIsInstance(merged, str)
        self.assertIn("管理费用", merged)
        # included 空时仍保留「其他」
        m2 = merge_ledger_caliber_filters(None, {"expense_categories_included": []}, show_all=False)
        self.assertIn("其他", m2)


if __name__ == "__main__":
    unittest.main()
