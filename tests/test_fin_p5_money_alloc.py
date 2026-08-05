# -*- coding: utf-8 -*-
"""P5 FIN：金额入口语义、坏金额拒入、分摊尾差与超摊闸。

FIN-001/002 直驱 shipped money/record_amounts/normalize 路径，禁止假绿。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import money  # noqa: E402
from ingest.normalize import _amt  # noqa: E402
from profit.bu_alloc import _shares_for_detail_item, _shares_pct_rules  # noqa: E402
from profit.expense_period import _fen_amount  # noqa: E402


class TestFin001NoBareFloatInAsFen(unittest.TestCase):
    def test_as_fen_int_is_fen(self):
        self.assertEqual(money.as_fen(100), 100)
        self.assertEqual(money.as_fen(10050), 10050)

    def test_as_fen_rejects_float(self):
        with self.assertRaises(TypeError):
            money.as_fen(100.5)

    def test_fen_amount_float_is_fen_shell_not_yuan(self):
        """_fen_amount(float) 仍是历史分壳 round，不得 ×100。"""
        self.assertEqual(_fen_amount(100.5), 100)
        self.assertEqual(_fen_amount(10050.0), 10050)

    def test_yuan_to_fen_is_yuan_path(self):
        self.assertEqual(money.yuan_to_fen(100.5), 10050)

    def test_amount_cell_to_fen_boundary(self):
        """边界：int=分，float=元；as_fen 仍拒 float。"""
        self.assertEqual(money.amount_cell_to_fen(10050), 10050)
        self.assertEqual(money.amount_cell_to_fen(100.5), 10050)
        with self.assertRaises(TypeError):
            money.as_fen(100.5)


class TestFin002RejectBadAmountsOnIngress(unittest.TestCase):
    def test_yuan_to_fen_rejects_garbage(self):
        with self.assertRaises(ValueError):
            money.yuan_to_fen("not-a-number")
        with self.assertRaises(ValueError):
            money.yuan_to_fen("N/A")

    def test_record_amounts_to_fen_rejects_bad(self):
        with self.assertRaises(ValueError):
            money.record_amounts_to_fen("std_下单", {"下单预估额": "bad"})

    def test_record_amounts_to_fen_accepts_valid_yuan(self):
        out = money.record_amounts_to_fen("std_下单", {"下单预估额": 12.34})
        self.assertEqual(out["下单预估额"], 1234)

    def test_normalize_amt_rejects_bad(self):
        """进料规范化 _amt 走 parse_amount(on_invalid=raise)。"""
        with self.assertRaises(ValueError):
            _amt("N/A")
        with self.assertRaises(ValueError):
            loaders.parse_amount("N/A", on_invalid="raise")
        # 软路径仍可 zero（校验计数）
        self.assertEqual(loaders.parse_amount("N/A", on_invalid="zero"), 0.0)
        self.assertTrue(loaders.amount_parse_fails("N/A"))


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
