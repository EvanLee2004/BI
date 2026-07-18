# -*- coding: utf-8 -*-
"""任务书54.4·B4：回款 summary_by_period / receipts_budget 显示串填充守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestReceiptsB4Packer(unittest.TestCase):
    def test_pack_side_from_summary_display_only(self):
        from viewmodels import _pack_receipts_side_and_budget

        summary = {
            "meta": {
                "year_key": "2026年",
                "budget": {
                    "receipt": {"target": 1200000.0, "done": 600000.0, "pct": 50.0},
                    "order": {"target": 2400000.0, "done": 1200000.0, "pct": 50.0},
                },
            },
            "periods": {
                "2026年": {
                    "label": "2026年",
                    "orders": 1200000.0,
                    "receipts": 600000.0,
                    "receipt_order_ratio_pct": 50.0,
                },
                "2026年Q1": {
                    "label": "2026年Q1",
                    "orders": 300000.0,
                    "receipts": 100000.0,
                    "receipt_order_ratio_pct": 33.3,
                },
            },
        }
        out = _pack_receipts_side_and_budget(summary)
        self.assertTrue(out["receipts_budget"].startswith("月均预算"))
        self.assertAlmostEqual(out["budget_month"], 100000.0)  # 120万/12
        self.assertTrue(out["budget_month_disp"])
        sp = out["summary_by_period"]
        self.assertIn("2026年", sp)
        self.assertIn("2026年Q1", sp)
        y = sp["2026年"]
        self.assertEqual(y["ratio_disp"], "50.0%")
        self.assertIn("orders_disp", y)
        self.assertIn("receipts_disp", y)
        self.assertIn("gap_disp", y)
        self.assertEqual(y["gap_hint"], "尚待回款")
        self.assertIn("receipt_target_disp", y)
        self.assertIn("order_target_disp", y)
        # Q1 无年目标条
        q = sp["2026年Q1"]
        self.assertNotIn("receipt_target_disp", q)
        self.assertEqual(q["ratio_disp"], "33.3%")

    def test_no_budget_ok(self):
        from viewmodels import _pack_receipts_side_and_budget

        out = _pack_receipts_side_and_budget(
            {
                "meta": {"year_key": "2026年", "budget": None},
                "periods": {
                    "2026年": {
                        "orders": 100.0,
                        "receipts": 100.0,
                        "receipt_order_ratio_pct": 100.0,
                    }
                },
            }
        )
        self.assertEqual(out["receipts_budget"], "")
        self.assertEqual(out["budget_month"], 0.0)
        self.assertEqual(out["summary_by_period"]["2026年"]["gap_hint"], "持平")


if __name__ == "__main__":
    unittest.main()
