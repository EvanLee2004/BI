# -*- coding: utf-8 -*-
"""3.3.3：KPI 目标进度条彻底去掉「目标待校准」；超目标显示真实%或 >999% 软顶。"""
from __future__ import annotations

import unittest
from pathlib import Path

from domain.pl.structure import kpi_target_bar
from viewmodels import _attach_year_budget_bars

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FORBIDDEN = "目标待校准"


class _FakeCharts:
    @staticmethod
    def fmt_wan(v):
        return f"{float(v) / 1e6:.1f}"


class TestNoTargetCalibrationLabel333(unittest.TestCase):
    def test_src_business_code_has_no_calibration_label(self):
        hits: list[str] = []
        for path in SRC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if FORBIDDEN in text:
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [], msg=f"src 业务代码仍含「{FORBIDDEN}」: {hits}")

    def test_kpi_target_bar_over_target_shows_real_pct(self):
        # margin 类：100 < pct < 1000 → 真实进度（.0f%）
        budget = {"margin": {"target": 20.0, "done": 30.0, "pct": 150.0}}
        bar = kpi_target_bar("margin", "2026年", {"gross_margin_pct": 30.0}, budget)
        self.assertFalse(bar.get("empty"))
        self.assertEqual(bar["pct_disp"], "150%")
        self.assertIn("%", bar["pct_disp"])
        self.assertNotIn("待校准", bar["pct_disp"])
        self.assertLessEqual(float(bar["bar_w"]), 100.0)

        # amount 类：pct=150 → 150.0%
        budget_a = {"order": {"target": 100.0, "done": 150.0, "pct": 150.0}}
        bar_a = kpi_target_bar("order", "2026年", {"orders": 150.0}, budget_a)
        self.assertEqual(bar_a["pct_disp"], "150.0%")
        self.assertNotIn("待校准", bar_a["pct_disp"])
        self.assertEqual(float(bar_a["bar_w"]), 100.0)

    def test_kpi_target_bar_extreme_soft_cap(self):
        budget = {"order": {"target": 1.0, "done": 50.0, "pct": 5000.0}}
        bar = kpi_target_bar("order", "2026年", {"orders": 50.0}, budget)
        self.assertEqual(bar["pct_disp"], ">999%")
        self.assertNotIn("待校准", bar["pct_disp"])
        self.assertLessEqual(float(bar["bar_w"]), 100.0)

    def test_attach_year_budget_bars_over_and_extreme(self):
        row: dict = {}
        budget = {
            "order": {"target": 100.0, "done": 125.0, "pct": 125.0},
            "receipt": {"target": 100.0, "done": 5000.0, "pct": 5000.0},
        }
        _attach_year_budget_bars(row, budget, _FakeCharts)
        self.assertEqual(row["order_pct_disp"], "125.0%")
        self.assertEqual(row["receipt_pct_disp"], ">999%")
        for k in ("order_pct_disp", "receipt_pct_disp"):
            self.assertNotIn("待校准", row[k])
            self.assertNotIn(FORBIDDEN, row[k])
        self.assertEqual(row["order_bar_w"], "100.0")
        self.assertEqual(row["receipt_bar_w"], "100.0")

    def test_pct_none_and_within_100(self):
        bar_none = kpi_target_bar(
            "order", "2026年", {"orders": 10.0}, {"order": {"target": 100.0, "done": 10.0, "pct": None}}
        )
        # done present but pct None → amount branch recomputes? done is not None so pct stays None
        # If pct is None and done is set: condition `if done is None` is false, so pct stays None → "—"
        self.assertEqual(bar_none["pct_disp"], "—")

        bar_ok = kpi_target_bar(
            "margin", "2026年", {"gross_margin_pct": 25.0}, {"margin": {"target": 30.0, "done": 25.0, "pct": 83.3}}
        )
        self.assertEqual(bar_ok["pct_disp"], "83%")
        self.assertLess(float(bar_ok["bar_w"]), 100.0)


if __name__ == "__main__":
    unittest.main()
