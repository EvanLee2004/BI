#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.3.1：分摊展示路径金额 int 分（源码守卫 + 守恒行为）。

驱动 shipped：alloc_amounts_by_period / apply_alloc_to_pc_view / _share_by_pct。
禁止 re-implement golden。
"""
from __future__ import annotations

import ast
import datetime
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from profit.bu_alloc import (  # noqa: E402
    _share_by_pct,
    alloc_amounts_by_period,
    apply_alloc_to_pc_view,
)
from profit.constants import ALLOC_IN_LABEL, ALLOC_OUT_LABEL, _LEDGER_TO_EXPENSE  # noqa: E402

TODAY = datetime.date(2026, 7, 15)
BU_ALLOC_SRC = (ROOT / "src" / "profit" / "bu_alloc.py").read_text(encoding="utf-8")


def _extract_func_source(src: str, name: str) -> str:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found")


def _strip_docstrings_and_comments(func_src: str) -> str:
    """去掉函数 docstring 与 # 注释，只扫可执行代码。"""
    try:
        tree = ast.parse(func_src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body = node.body[1:]
        # unparse 可能丢注释；再滤行内 #
        code = ast.unparse(tree)
    except Exception:
        code = func_src
    lines = []
    for ln in code.splitlines():
        if "#" in ln:
            ln = ln.split("#", 1)[0]
        lines.append(ln)
    return "\n".join(lines)


class TestAllocIntFenSourceGuards(unittest.TestCase):
    def test_no_float_money_truth_in_display_alloc_path(self):
        """金额向 float(led / * float(pct)/100 / round(...,2) 真相路径禁止。"""
        for fname in ("alloc_amounts_by_period", "apply_alloc_to_pc_view"):
            body = _extract_func_source(BU_ALLOC_SRC, fname)
            self.assertTrue(body, fname)
            code = _strip_docstrings_and_comments(body)
            # 禁止对台账/金额做 float(led… 或 * float(pct)/100
            self.assertIsNone(
                re.search(r"float\s*\(\s*led", code),
                f"{fname}: float(led…) money path",
            )
            self.assertIsNone(
                re.search(r"\*\s*float\s*\(\s*pct\s*\)\s*/\s*100", code),
                f"{fname}: * float(pct)/100 money path",
            )
            self.assertIsNone(
                re.search(r"round\s*\([^)]*,\s*2\s*\)", code),
                f"{fname}: round(...,2) money truth",
            )
            self.assertIn("_fen_amount", body)
        # 默认路径份额须走 _share_by_pct / mul_rates_fen
        body = _extract_func_source(BU_ALLOC_SRC, "alloc_amounts_by_period")
        self.assertIn("_share_by_pct", body)
        self.assertIn("dict[str, int]", body)

    def test_apply_pc_view_returns_int_annotation(self):
        body = _extract_func_source(BU_ALLOC_SRC, "apply_alloc_to_pc_view")
        self.assertIn("dict[str, int]", body)
        self.assertIn("int 分", body)


class TestAllocIntFenBehavior(unittest.TestCase):
    def _month_led_fen(self, month_tot: int) -> dict:
        n = len(_LEDGER_TO_EXPENSE)
        base, rem = divmod(month_tot, n)
        out = {}
        for i, c in enumerate(_LEDGER_TO_EXPENSE):
            out[c] = base + (rem if i == 0 else 0)
        return {(2026, 7): out}

    def test_partial_alloc_conserves_fen(self):
        """ΣBU 分摊 + 公共残留 == 公共池（分）。"""
        pool = 100_00  # 100 元 = 10000 分
        led = self._month_led_fen(pool)
        ratios = {"2026-07": {"游戏": 30, "数据": 20}}
        per = alloc_amounts_by_period(led, ratios, ["游戏", "数据"], TODAY)
        m7 = next(v for k, v in per.items() if "7月" in k)
        self.assertIsInstance(m7["游戏"], int)
        self.assertIsInstance(m7["数据"], int)
        self.assertEqual(m7["游戏"], _share_by_pct(pool, 30))
        self.assertEqual(m7["数据"], _share_by_pct(pool, 20))
        total_alloc = m7["游戏"] + m7["数据"]
        residual = pool - total_alloc
        self.assertEqual(total_alloc + residual, pool)
        self.assertEqual(residual, _share_by_pct(pool, 50))

    def test_apply_pc_view_conservation_int(self):
        groups = [
            ("公共", 100_00, [("房租", 80_00), ("水电", 20_00)]),
            ("游戏", 30_00, [("差旅", 30_00)]),
        ]
        out = apply_alloc_to_pc_view(groups, {"游戏": 30_00, "数据": 20_00})
        gm = {g: (t, dict(f)) for g, t, f in out}
        self.assertEqual(gm["公共"][0], 50_00)
        self.assertEqual(gm["游戏"][0], 60_00)
        self.assertEqual(gm["数据"][0], 20_00)
        self.assertEqual(gm["游戏"][1][ALLOC_IN_LABEL], 30_00)
        self.assertEqual(gm["公共"][1][ALLOC_OUT_LABEL], -50_00)
        self.assertEqual(sum(t for _, t, _ in out), sum(t for _, t, _ in groups))
        for g, t, f in out:
            self.assertIsInstance(t, int)
            self.assertEqual(sum(v for _, v in f), t, msg=g)

    def test_disabled_or_empty_untouched(self):
        """无比例/空 alloc：不动（分摊关或未配置）。"""
        led = self._month_led_fen(10_00)
        per = alloc_amounts_by_period(led, {}, ["游戏"], TODAY)
        self.assertEqual(per, {})
        groups = [("公共", 10_00, [("a", 10_00)]), ("游戏", 1_00, [("b", 1_00)])]
        self.assertEqual(apply_alloc_to_pc_view(groups, {}), groups)
        self.assertIsNone(apply_alloc_to_pc_view(None, {"游戏": 1}))


if __name__ == "__main__":
    unittest.main()
