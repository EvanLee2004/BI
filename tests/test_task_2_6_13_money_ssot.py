# -*- coding: utf-8 -*-
"""2.6.13：算账金额 SSOT + int 分契约守卫。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestExpenseTotalsSsot(unittest.TestCase):
    def test_returns_all_int(self):
        from profit.expense_period import expense_totals_from_man_led

        man = {
            "营销人力成本": 100_00,
            "管理人力成本": 20_00,
            "研发人力成本": 30_00,
            "财务费用补充": 5_00,
            "房租物业": 10_00,
        }
        led = {
            "市场费用": 40_00,
            "管理费用": 15_00,
            "固定运营费用": 8_00,
            "技术服务费": 12_00,
            "财务费用": 3_00,
        }
        exp = expense_totals_from_man_led(man, led, None)
        for k, v in exp.items():
            self.assertIsInstance(v, int)
            self.assertNotIsInstance(v, bool)
        # 营销 = 10000 + 4000 + 0 mac市场 = 14000
        self.assertEqual(exp["营销费用"], 140_00)
        # 固定 = 800 + 1000 房租物业 mac = 1800
        self.assertEqual(exp["固定运营费用"], 18_00)
        self.assertEqual(
            exp["total"],
            exp["营销费用"]
            + exp["管理费用"]
            + exp["固定运营费用"]
            + exp["研发费用"]
            + exp["财务费用"],
        )

    def test_build_period_source_uses_ssot_no_inline(self):
        text = (ROOT / "src/profit/budget_manual.py").read_text(encoding="utf-8")
        self.assertIn("expense_totals_from_man_led", text)
        self.assertIn("pretax_profit_fen", text)
        self.assertNotIn('sales_exp = int(man["营销人力成本"]', text)
        self.assertNotIn("sales_exp = int(man[", text)

    def test_bu_apply_no_round_float_exp(self):
        text = (ROOT / "src/profit/bu_alloc.py").read_text(encoding="utf-8")
        self.assertNotIn("round(float(exp[", text)
        self.assertIn("pretax_profit_fen", text)
        self.assertIn("mul_rates_fen", text)

    def test_pretax_identity(self):
        from profit.expense_period import pretax_profit_fen

        self.assertEqual(pretax_profit_fen(1_000_00, 200_00, 12_00, 5_00), 793_00)
        self.assertEqual(pretax_profit_fen(0, 0, 0, 0), 0)

    def test_ledger_expenses_int(self):
        from profit.expense_period import compute_ledger_expenses
        import loaders

        cfg = loaders.load_config(ROOT)
        # empty → zeros int
        led, n = compute_ledger_expenses([], 2026, __import__("datetime").date(2026, 1, 1), __import__("datetime").date(2026, 12, 31), cfg, {"含税金额": 0})
        self.assertEqual(n, 0)
        for v in led.values():
            self.assertIsInstance(v, int)


if __name__ == "__main__":
    unittest.main()
