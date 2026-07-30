# -*- coding: utf-8 -*-
"""3.6.0 G4：重点客户金额轴仅当前选中系列。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestSelectedSeriesAxis(unittest.TestCase):
    def test_chart_does_not_use_global_amount_axis_max(self):
        src = (FE / "charts/keyCustomersChart.ts").read_text(encoding="utf-8")
        # 禁止 amountAxis?.max 参与轴上限
        self.assertNotRegex(
            src,
            r"Number\(amountAxis\?\.max\)",
            "amount axis max must not use global amountAxis.max",
        )
        self.assertIn("localMax", src)
        self.assertIn("Math.max(localMax", src)

    def test_compare_max_five(self):
        vm = (ROOT / "src/viewmodels/key_customers.py").read_text(encoding="utf-8")
        self.assertIn('"compare_max": 5', vm)
        fe = (FE / "composables/useKeyCustomers.ts").read_text(encoding="utf-8")
        self.assertRegex(fe, r":\s*5\b|Math\.min\(5")


class TestDomainVmNoFrontendMoney(unittest.TestCase):
    def test_key_customers_components_no_amount_math(self):
        # 业务组件层禁止 * 100 / 10000 等金额换算
        banned = re.compile(r"/\s*10000|\*\s*10000|yuan_to_fen|fen_to_yuan")
        for p in (FE / "components").rglob("*.vue"):
            if "key-customers" not in str(p) and "KeyCustomers" not in p.name:
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            self.assertIsNone(banned.search(t), f"amount math in {p}")


if __name__ == "__main__":
    unittest.main()
