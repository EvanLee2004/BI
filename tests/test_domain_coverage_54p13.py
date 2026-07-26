#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""54.13 M8：补 domain 有断言价值的覆盖（config_engine + pl.structure 缺口）。"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain import config_engine  # noqa: E402
from domain.pl import structure as pl_structure  # noqa: E402


class TestConfigEngineBasics(unittest.TestCase):
    def test_default_categories_nonempty(self):
        # 真断言：硬编码默认配置可加载且含核心键
        self.assertTrue(hasattr(config_engine, "default_config_from_hardcoded"))
        self.assertTrue(hasattr(config_engine, "load_all"))
        cfg = config_engine.default_config_from_hardcoded()
        self.assertIsInstance(cfg, dict)
        self.assertIn("报表大类白名单", cfg)
        names = [n for n in dir(config_engine) if not n.startswith("_")]
        self.assertGreater(len(names), 3)

    def test_pl_structure_empty_period_safe(self):
        # minimal empty-ish period should not crash
        p = {
            "revenue": 0, "cost": 0, "gross": 0, "gross_rate": 0,
            "expenses": {}, "expense_total": 0, "op_profit": 0,
            "tax_surcharge": 0, "profit_before_tax": 0,
        }
        self.assertTrue(callable(getattr(pl_structure, "pl_structure", None)))
        out = pl_structure.pl_structure(p, {})
        self.assertIsInstance(out, dict)


if __name__ == '__main__':
    unittest.main()
