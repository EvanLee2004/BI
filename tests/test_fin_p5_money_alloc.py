# -*- coding: utf-8 -*-
"""P5 FIN：金额入口语义、坏金额、分摊尾差与超摊闸。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import money  # noqa: E402
from profit.bu_alloc import _shares_for_detail_item, _shares_pct_rules  # noqa: E402
from profit.expense_period import _fen_amount  # noqa: E402


class TestFin001DualSemanticsDocumented(unittest.TestCase):
    def test_as_fen_int_is_fen_float_is_yuan(self):
        self.assertEqual(money.as_fen(100), 100)
        self.assertEqual(money.as_fen(100.5), 10050)
        self.assertEqual(_fen_amount(100.5), 100)  # float 分壳

    def test_as_fen_rejects_non_finite(self):
        with self.assertRaises(ValueError):
            money.as_fen(float("nan"))


class TestFin002InvalidAmount(unittest.TestCase):
    def test_zero_compat(self):
        self.assertEqual(money.yuan_to_fen("not-a-number"), 0)

    def test_strict_raise(self):
        with self.assertRaises(ValueError):
            money.yuan_to_fen("N/A", on_invalid="raise")


class TestFin004Residual(unittest.TestCase):
    def test_hundred_pct_residual_to_last_bu(self):
        shares = _shares_pct_rules(
            "x",
            10001,
            {
                "A": {"mode": "比例", "value": 33.3},
                "B": {"mode": "比例", "value": 33.3},
                "C": {"mode": "比例", "value": 33.4},
            },
        )
        self.assertEqual(sum(s for _, s in shares), 10001)


class TestFin005OverAllocGate(unittest.TestCase):
    def test_default_ratios_over_100_raises(self):
        with self.assertRaises(ValueError):
            _shares_for_detail_item("x", 10000, {}, {"A": 60.0, "B": 50.0})


if __name__ == "__main__":
    unittest.main()
