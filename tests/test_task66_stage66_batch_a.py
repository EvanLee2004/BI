#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·A：金额分整数 / Decimal ROUND_HALF_UP / API 解析。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import money  # noqa: E402
from profit.tax_revenue import split_tax  # noqa: E402


class TestSplitTaxFenHalfUp(unittest.TestCase):
    def test_conservation(self):
        for g in (0, 1, 99, 100, 1005, 60050, 12_345_678, 99_999_999):
            for rate in (0.0, 0.06, 0.09, 0.13):
                s = split_tax(g, rate)
                self.assertEqual(
                    s["revenue_net"] + s["vat"],
                    s["revenue_gross"],
                    msg=f"g={g} rate={rate} {s}",
                )

    def test_half_up_divide(self):
        # 5/2 → 3 (ROUND_HALF_UP)
        self.assertEqual(money.divide_fen(5, 2), 3)
        self.assertEqual(money.divide_fen(4, 2), 2)
        # 1.06 路径：1005 / 1.06 = 948.113… → 948
        s = split_tax(1005, 0.06)
        self.assertEqual(s["revenue_net"], 948)
        self.assertEqual(s["vat"], 57)

    def test_known_60050(self):
        s = split_tax(60050, 0.06)
        self.assertEqual(s["revenue_gross"], 60050)
        self.assertEqual(s["revenue_net"] + s["vat"], 60050)


class TestMoneyParse(unittest.TestCase):
    def test_yuan_to_fen_half_up(self):
        self.assertEqual(money.yuan_to_fen("12.345"), 1235)
        self.assertEqual(money.yuan_to_fen("12.344"), 1234)
        self.assertEqual(money.yuan_to_fen(12.345), 1235)

    def test_parse_decimal_str_and_float(self):
        self.assertEqual(money.parse_decimal("3.14"), money.parse_decimal(3.14))
        self.assertIsNone(money.parse_decimal(""))
        with self.assertRaises(ValueError):
            money.parse_decimal("not-a-number")

    def test_quantize_rate(self):
        self.assertEqual(money.quantize_rate("33.35", places=1), 33.4)
        self.assertEqual(money.quantize_rate(12.345, places=2), 12.35)

    def test_mul_rates_fen(self):
        # 10000 分 × 0.06 × 0.12 = 72 分
        self.assertEqual(money.mul_rates_fen(10000, 0.06, 0.12), 72)


class TestProfitNoFenToYuanInCorePath(unittest.TestCase):
    def test_tax_revenue_no_fen_to_yuan(self):
        t = (ROOT / "src" / "profit" / "tax_revenue.py").read_text(encoding="utf-8")
        self.assertNotIn("fen_to_yuan", t)

    def test_budget_manual_surtax_no_fen_to_yuan(self):
        t = (ROOT / "src" / "profit" / "budget_manual.py").read_text(encoding="utf-8")
        # surtax 行不得再用 fen_to_yuan
        for line in t.splitlines():
            if "surtax" in line and "=" in line and "fen_to_yuan" in line:
                self.fail(f"surtax still uses fen_to_yuan: {line}")


if __name__ == "__main__":
    unittest.main()
