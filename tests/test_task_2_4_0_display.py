#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.4.0 Stage E：BU 分摊明细下钻 + 其他N项可展开。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.pl.structure import _fine_pairs, _pl_bu_expense_block  # noqa: E402


class TestAllocDetailLinesInStructure(unittest.TestCase):
    def test_alloc_added_details_show_per_item(self):
        p = {
            "alloc_added": {"管理费用": 10000.0},
            "alloc_added_details": {
                "管理费用": [
                    {"name": "打印费", "amt": 6400.0},
                    {"name": "办公用品", "amt": 3600.0},
                ]
            },
            "range": ["2026-07-01", "2026-07-31"],
        }
        e = {"管理费用": 10000.0, "total": 10000.0}
        man = {}
        led = {"管理费用": 10000.0}
        fine = {}
        alloc_meta = {"enabled": True, "ratio_disp": "按明细分摊"}
        _tag, _hf, _hm, _rows, details = _pl_bu_expense_block(
            p, e, man, led, fine, alloc_meta
        )
        admin_lines = details["admin"]["lines"]
        names = [ln["name"] for ln in admin_lines]
        self.assertTrue(any(n.startswith("分摊自公共·打印费") for n in names), names)
        self.assertTrue(any(n.startswith("分摊自公共·办公用品") for n in names), names)
        # 不应只剩一条「分摊自公共」合计
        self.assertNotIn("分摊自公共", names)

    def test_fallback_single_alloc_line_without_details(self):
        p = {"alloc_added": {"管理费用": 5000.0}}
        e = {"管理费用": 5000.0, "total": 5000.0}
        _tag, _hf, _hm, _rows, details = _pl_bu_expense_block(
            p, e, {}, {"管理费用": 5000.0}, {}, {"enabled": True, "ratio_disp": "按月比例"}
        )
        names = [ln["name"] for ln in details["admin"]["lines"]]
        self.assertIn("分摊自公共", names)


class TestOtherNExpandable(unittest.TestCase):
    def test_fine_pairs_other_has_children(self):
        pairs = [(f"项{i}", float(100 - i)) for i in range(12)]
        lines = _fine_pairs(pairs, limit=8)
        other = [ln for ln in lines if str(ln.get("name", "")).startswith("其他")]
        self.assertEqual(len(other), 1)
        self.assertTrue(other[0].get("expandable"))
        children = other[0].get("children") or []
        self.assertEqual(len(children), 4)
        self.assertEqual(children[0]["name"], "项8")

    def test_frontend_pltable_expand_anchor(self):
        vue = (ROOT / "frontend/src/components/PLTable.vue").read_text(encoding="utf-8")
        self.assertIn("expandedOther", vue)
        self.assertIn("toggleOther", vue)
        self.assertIn("expandable", vue)
        self.assertIn("children", vue)


if __name__ == "__main__":
    unittest.main()
