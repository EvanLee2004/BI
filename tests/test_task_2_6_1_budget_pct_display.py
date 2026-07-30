# -*- coding: utf-8 -*-
"""2.6.1/3.3.3：业绩目标进度展示——≤100 正常%、(100,1000) 真实%、≥1000 软顶 >999%。"""
from __future__ import annotations

import unittest

from domain.pl.structure import kpi_target_bar
from viewmodels import _attach_year_budget_bars


class _FakeCharts:
    @staticmethod
    def fmt_wan(v):
        return f"{float(v) / 1e6:.1f}"


class TestBudgetPctDisplay261(unittest.TestCase):
    def test_kpi_target_bar_extreme_soft_cap_gt999(self):
        budget = {"order": {"target": 1.0, "done": 100_000.0, "pct": 48178.0}}
        bar = kpi_target_bar("order", "2026年", {"orders": 100_000.0}, budget)
        self.assertFalse(bar.get("empty"))
        self.assertEqual(bar["pct_disp"], ">999%")
        self.assertLessEqual(float(bar["bar_w"]), 100.0)

    def test_attach_year_budget_bars_soft_cap_and_normal(self):
        row: dict = {}
        budget = {
            "order": {"target": 100.0, "done": 1_000_000.0, "pct": 5000.0},
            "receipt": {"target": 100.0, "done": 50.0, "pct": 50.0},
        }
        _attach_year_budget_bars(row, budget, _FakeCharts)
        self.assertEqual(row["order_pct_disp"], ">999%")
        self.assertEqual(row["receipt_pct_disp"], "50.0%")


if __name__ == "__main__":
    unittest.main()
