#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·5：domain 分包可 import + re-export 指向真实函数。"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PACKS = ["kpi", "trend", "pl", "expense", "rankings", "receipts", "ledger", "export"]


class TestDomainReexport(unittest.TestCase):
    def test_ast_parse_all(self):
        for name in PACKS:
            p = ROOT / "src" / "domain" / name / "__init__.py"
            src = p.read_text(encoding="utf-8")
            ast.parse(src)
            self.assertNotIn("\\\\n", src)

    def test_import_and_callable(self):
        import domain.kpi as kpi
        import domain.trend as trend
        import domain.pl as pl
        import domain.expense as expense
        import domain.rankings as rankings
        import domain.receipts as receipts
        import domain.ledger as ledger
        import domain.export as export  # noqa: F401

        self.assertTrue(callable(kpi.build_period))
        self.assertTrue(callable(trend.render_trend))
        self.assertTrue(callable(pl.render_pl_table))
        self.assertTrue(callable(expense.compute_ledger_expenses))
        self.assertTrue(callable(rankings.render_profit_rankings))
        self.assertTrue(callable(receipts.render_receipts))
        self.assertTrue(callable(ledger.compute_ledger_expenses))

    def test_same_object_as_profit_render(self):
        import profit
        import render
        import domain.expense as expense
        import domain.trend as trend

        self.assertIs(expense.compute_ledger_expenses, profit.compute_ledger_expenses)
        self.assertIs(trend.render_trend, render.render_trend)


if __name__ == "__main__":
    unittest.main()
