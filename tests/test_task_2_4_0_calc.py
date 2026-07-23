#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.4.0 Stage C：公共费用明细分摊计算（超额挡、不双计、与默认层等价）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from profit.bu_alloc import (  # noqa: E402
    allocate_public_details_for_month,
    allocate_public_details_lines_for_month,
    alloc_amounts_by_period,
)
from profit.constants import _LEDGER_TO_EXPENSE  # noqa: E402


class TestAllocatePublicDetails(unittest.TestCase):
    def test_default_layer_equals_cat_ratio(self):
        """无精配时：明细×默认比例 ≡ 大类合计×默认比例。"""
        details = {
            "打印费": {"amount": 8000.0, "cat": "管理费用"},  # 80 元
            "办公用品": {"amount": 2000.0, "cat": "管理费用"},  # 20 元
            "差旅费": {"amount": 10000.0, "cat": "市场费用"},
        }
        ratios = {"数据部": 50.0, "游戏部": 30.0}
        got = allocate_public_details_for_month(details, {}, ratios, ["数据部", "游戏部"])
        self.assertAlmostEqual(got["数据部"]["管理费用"], 5000.0, places=2)
        self.assertAlmostEqual(got["数据部"]["市场费用"], 5000.0, places=2)
        self.assertAlmostEqual(got["游戏部"]["管理费用"], 3000.0, places=2)
        # 残留 20% 留公司：已摊 80%
        total_admin = sum(got[b].get("管理费用", 0) for b in got)
        self.assertAlmostEqual(total_admin, 8000.0, places=2)

    def test_fine_ratio_over_100_raises(self):
        details = {"打印费": {"amount": 10000.0, "cat": "管理费用"}}
        rules = {
            "打印费": {
                "数据部": {"mode": "比例", "value": 80},
                "游戏部": {"mode": "比例", "value": 30},
            }
        }
        with self.assertRaises(ValueError) as cm:
            allocate_public_details_for_month(details, rules, {}, ["数据部", "游戏部"])
        self.assertIn("100", str(cm.exception))

    def test_fine_amount_over_total_raises(self):
        details = {"装修费": {"amount": 100000.0, "cat": "固定运营费用"}}  # 1000 元
        rules = {
            "装修费": {
                "数据部": {"mode": "金额", "value": 800.0},  # 元
                "游戏部": {"mode": "金额", "value": 300.0},
            }
        }
        with self.assertRaises(ValueError) as cm:
            allocate_public_details_for_month(details, rules, {}, ["数据部", "游戏部"])
        self.assertIn("超过", str(cm.exception))

    def test_fine_ratio_preferred_over_default(self):
        details = {
            "打印费": {"amount": 10000.0, "cat": "管理费用"},
            "茶歇费": {"amount": 10000.0, "cat": "管理费用"},
        }
        rules = {"打印费": {"数据部": {"mode": "比例", "value": 100}}}
        defaults = {"游戏部": 100.0}
        got = allocate_public_details_for_month(
            details, rules, defaults, ["数据部", "游戏部"]
        )
        # 打印费 100% 数据部；茶歇费走默认 100% 游戏部
        self.assertAlmostEqual(got["数据部"]["管理费用"], 10000.0, places=2)
        self.assertAlmostEqual(got["游戏部"]["管理费用"], 10000.0, places=2)

    def test_rent_no_double_count_new_path_equals_old_total(self):
        """房水电不双计：老口径月总额（手填）== 新口径摊入总额（覆盖+100%精配）。

        新路径：金额覆盖提供月度平滑值，精配 100% 给一 BU → 摊入额 == 覆盖额。
        不与旧 manual_alloc 叠加（本测只跑新路径）。
        """
        old_total_yuan = 56.4
        import money

        fen = money.yuan_to_fen(old_total_yuan)
        details = {
            "房租物业": {"amount": float(fen), "cat": "固定运营费用"},
        }
        rules = {"房租物业": {"数据部": {"mode": "比例", "value": 100}}}
        got = allocate_public_details_for_month(details, rules, {}, ["数据部"])
        new_total = sum(got["数据部"].values())
        self.assertEqual(int(round(new_total)), int(fen))
        # 明细行
        lines = allocate_public_details_lines_for_month(
            details, rules, {}, "数据部"
        )
        self.assertIn("固定运营费用", lines)
        self.assertEqual(lines["固定运营费用"][0][0], "房租物业")
        self.assertEqual(int(round(lines["固定运营费用"][0][1])), int(fen))

    def test_amount_mode_allocates_fen(self):
        details = {"装修费": {"amount": 100000.0, "cat": "固定运营费用"}}  # 1000 元
        rules = {
            "装修费": {
                "数据部": {"mode": "金额", "value": 500.0},
                "游戏部": {"mode": "金额", "value": 300.0},
            }
        }
        got = allocate_public_details_for_month(
            details, rules, {}, ["数据部", "游戏部"]
        )
        self.assertAlmostEqual(got["数据部"]["固定运营费用"], 50000.0, places=2)
        self.assertAlmostEqual(got["游戏部"]["固定运营费用"], 30000.0, places=2)
        # 残留 200 元留公司
        residual = 100000.0 - 50000.0 - 30000.0
        self.assertAlmostEqual(residual, 20000.0, places=2)


class TestAllocAmountsByPeriodDetail(unittest.TestCase):
    def test_detail_path_totals(self):
        import datetime

        today = datetime.date(2026, 7, 15)
        public_month_details = {
            (2026, 7): {
                "打印费": {"amount": 10000.0, "cat": "管理费用"},
            }
        }
        public_month_led = {(2026, 7): {c: 0.0 for c in _LEDGER_TO_EXPENSE}}
        public_month_led[(2026, 7)]["管理费用"] = 10000.0
        ratios = {"2026-07": {"数据部": 40.0}}
        fine = {}
        per = alloc_amounts_by_period(
            public_month_led,
            ratios,
            ["数据部"],
            today,
            public_month_details=public_month_details,
            fine_rules_by_month=fine,
        )
        # 年周期应含 7 月摊入 4000
        yk = "2026年"
        self.assertIn(yk, per)
        self.assertAlmostEqual(per[yk]["数据部"], 4000.0, places=2)


if __name__ == "__main__":
    unittest.main()
