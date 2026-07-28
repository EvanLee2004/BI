#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·5：domain 分包可 import；2.7.9 G4 起 HTML 函数不再经 domain 再导出。"""
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
        import domain.trend as trend  # noqa: F401 — 包可 import
        import domain.pl as pl
        import domain.expense as expense
        import domain.rankings as rankings
        import domain.receipts as receipts
        import domain.ledger as ledger
        import domain.export as export  # noqa: F401

        self.assertTrue(callable(kpi.build_period))
        self.assertTrue(callable(pl.pl_structure))
        self.assertTrue(callable(expense.compute_ledger_expenses))
        self.assertTrue(callable(rankings.compute_ranking))
        self.assertTrue(callable(receipts.compute_receipts))
        self.assertTrue(callable(ledger.compute_ledger_expenses))

    def test_domain_packages_no_html_reexport(self):
        """G4：domain 业务包不得再 from/import HTML 装运层。"""
        import re

        pat = re.compile(r"import render|from render")
        for name in ("pl", "expense", "rankings", "receipts", "trend"):
            p = ROOT / "src" / "domain" / name / "__init__.py"
            src = p.read_text(encoding="utf-8")
            self.assertIsNone(pat.search(src), f"domain.{name} 仍依赖 HTML 装运层")

    def test_same_object_as_profit(self):
        import profit
        import domain.expense as expense

        self.assertIs(expense.compute_ledger_expenses, profit.compute_ledger_expenses)


if __name__ == "__main__":
    unittest.main()
