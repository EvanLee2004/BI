#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.12 费用视图收敛：去部门 · BU 藏利润中心 · 整体 by_pc=各 BU 分摊后 total · 展示守恒。

驱动 shipped：viewmodels.packers.pack_expense_views_by_period / ExpenseSection 源码。
禁止 re-implement 打包逻辑。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from viewmodels import packers  # noqa: E402

FE_EXP = ROOT / "frontend" / "src" / "components" / "ExpenseSection.vue"
FE_TYPES = ROOT / "frontend" / "src" / "types" / "vm.ts"


def _strip_comments(src: str) -> str:
    src = re.sub(r"<!--[\s\S]*?-->", "", src)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//.*?$", "", src, flags=re.M)
    return src


class TestExpenseViewsSourceGuards(unittest.TestCase):
    def setUp(self):
        self.src = FE_EXP.read_text(encoding="utf-8")
        self.code = _strip_comments(self.src)
        self.types = FE_TYPES.read_text(encoding="utf-8")

    def test_no_dept_tab_or_mode(self):
        self.assertNotIn("exp-tab-dept", self.src)
        self.assertNotIn("按部门", self.code)
        self.assertNotIn("by_dept", self.code)
        self.assertNotRegex(self.code, r"mode\s*===\s*['\"]dept['\"]")
        self.assertNotIn("by_dept", self.types)

    def test_pc_tab_only_when_not_bu(self):
        self.assertIn("exp-tab-pc", self.src)
        self.assertIn("按利润中心", self.src)
        self.assertIn("showPcTab", self.code)
        self.assertIn("store.scope !== 'bu'", self.code)
        self.assertIn("v-if=\"showPcTab\"", self.src)

    def test_bu_switch_resets_pc_mode(self):
        self.assertIn("store.scope", self.code)
        self.assertIn("store.buName", self.code)
        self.assertIn("mode.value = 'donut'", self.code)
        # 切 scope/bu 时若 mode 是 pc/dept 要 reset
        self.assertRegex(self.code, r"mode\.value\s*===\s*['\"]pc['\"]")

    def test_still_binds_category_and_pc(self):
        self.assertIn("by_category", self.code)
        self.assertIn("by_pc", self.code)
        self.assertIn("exp-tab-donut", self.src)
        self.assertIn("exp-tab-fine", self.src)


class TestPackExpenseViewsConserve(unittest.TestCase):
    """驱动 pack_expense_views_by_period：守恒 + by_pc=BU total。"""

    def test_no_by_dept_key(self):
        summary = {
            "periods": {
                "2026年": {"expense": {"total": 1_000_00, "营销费用": 1_000_00}},
            },
            "expense_fine_type": {
                "2026年": {"营销费用": [("差旅", 400_00)]},
            },
        }
        out = packers.pack_expense_views_by_period(summary, is_bu=False, bu_pages={})
        self.assertIn("2026年", out)
        self.assertNotIn("by_dept", out["2026年"])

    def test_by_category_conserves_with_residual(self):
        total = 1_000_00
        summary = {
            "periods": {"2026年": {"expense": {"total": total}}},
            "expense_fine_type": {
                "2026年": {"营销费用": [("差旅", 300_00), ("招待", 200_00)]},
            },
        }
        packed = packers.pack_expense_views_by_period(summary, is_bu=False, bu_pages={})
        block = packed["2026年"]
        self.assertEqual(block["total"], total)
        rows = block["by_category"]
        s = sum(int(r.get("value") or 0) for r in rows)
        self.assertEqual(s, total)
        names = [r["name"] for r in rows]
        self.assertIn(packers.EXPENSE_RESIDUAL_CATEGORY, names)
        residual = next(r for r in rows if r["name"] == packers.EXPENSE_RESIDUAL_CATEGORY)
        self.assertEqual(int(residual["value"]), 500_00)

    def test_overall_by_pc_matches_bu_expense_totals(self):
        pk = "2026年6月"
        overall_total = 900_00
        bu_a, bu_b = 500_00, 300_00
        summary = {
            "periods": {pk: {"expense": {"total": overall_total}}},
            "expense_fine_type": {},
        }
        bu_pages = {
            "语言": {
                "name": "语言",
                "summary": {"periods": {pk: {"expense": {"total": bu_a}}}},
            },
            "数据": {
                "name": "数据",
                "summary": {"periods": {pk: {"expense": {"total": bu_b}}}},
            },
        }
        packed = packers.pack_expense_views_by_period(
            summary, is_bu=False, bu_pages=bu_pages
        )
        block = packed[pk]
        by_pc = block["by_pc"]
        by_name = {r["name"]: int(r.get("value") or 0) for r in by_pc}
        self.assertEqual(by_name.get("语言"), bu_a)
        self.assertEqual(by_name.get("数据"), bu_b)
        # 守恒：BU 行 + 公共剩余 = 整体 total
        self.assertEqual(sum(by_name.values()), overall_total)
        self.assertEqual(
            by_name.get(packers.EXPENSE_RESIDUAL_PC),
            overall_total - bu_a - bu_b,
        )

    def test_bu_pack_has_empty_by_pc(self):
        summary = {
            "periods": {"2026年": {"expense": {"total": 200_00}}},
            "expense_fine_type": {
                "2026年": {"管理费用": [("办公", 200_00)]},
            },
        }
        # 即使误传 bu_pages，is_bu=True 也不得下发 by_pc
        fake_pages = {
            "X": {"name": "X", "summary": {"periods": {"2026年": {"expense": {"total": 99}}}}}
        }
        packed = packers.pack_expense_views_by_period(
            summary, is_bu=True, bu_pages=fake_pages
        )
        self.assertEqual(packed["2026年"]["by_pc"], [])
        s = sum(int(r.get("value") or 0) for r in packed["2026年"]["by_category"])
        self.assertEqual(s, 200_00)

    def test_category_exact_match_no_spurious_residual(self):
        total = 700_00
        summary = {
            "periods": {"2026年": {"expense": {"total": total}}},
            "expense_fine_type": {
                "2026年": {"营销费用": [("差旅", 400_00), ("招待", 300_00)]},
            },
        }
        packed = packers.pack_expense_views_by_period(summary, is_bu=False, bu_pages={})
        names = [r["name"] for r in packed["2026年"]["by_category"]]
        self.assertNotIn(packers.EXPENSE_RESIDUAL_CATEGORY, names)
        self.assertEqual(
            sum(int(r["value"]) for r in packed["2026年"]["by_category"]),
            total,
        )


class TestPackerDoesNotUseLedgerByPc(unittest.TestCase):
    """禁止整体 by_pc 再走台账直记 expense_by_profit_center 半截。"""

    def test_ledger_by_pc_ignored_when_bu_pages_given(self):
        pk = "2026年"
        summary = {
            "periods": {pk: {"expense": {"total": 100_00}}},
            "expense_fine_type": {},
            # 若误读此字段会出「台账半截」行
            "expense_by_profit_center": {
                pk: [("幽灵中心", 1_00, [("x", 1_00)])],
            },
        }
        bu_pages = {
            "真BU": {
                "name": "真BU",
                "summary": {"periods": {pk: {"expense": {"total": 100_00}}}},
            },
        }
        packed = packers.pack_expense_views_by_period(
            summary, is_bu=False, bu_pages=bu_pages
        )
        names = [r["name"] for r in packed[pk]["by_pc"]]
        self.assertIn("真BU", names)
        self.assertNotIn("幽灵中心", names)


if __name__ == "__main__":
    unittest.main()
