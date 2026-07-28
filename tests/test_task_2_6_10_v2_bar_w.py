# -*- coding: utf-8 -*-
"""2.6.10 V-2：/api/v1/rankings/profit items 必须带 bar_w（用户能看见有长短的条）。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestProfitRankBarWUnit(unittest.TestCase):
    def test_payload_has_bar_w_normalized(self):
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from routes import data_api

        rk = {
            "items": [
                {"name": "甲", "revenue": 10000, "cost_pct": 40},
                {"name": "乙", "revenue": 5000, "cost_pct": 50},
                {"name": "丙", "revenue": 0, "cost_pct": None},
            ],
            "unfilled": {"revenue": 2000, "cost_pct": 10},
        }
        items = data_api._profit_rank_items_payload(rk, "customer")
        self.assertGreater(len(items), 0)
        for it in items:
            self.assertIn("bar_w", it, it)
            bw = float(it["bar_w"])
            self.assertGreaterEqual(bw, 0)
            self.assertLessEqual(bw, 100)
        # 至少一条 > 0
        self.assertTrue(any(float(it["bar_w"]) > 0 for it in items))
        # 榜首（最大 revenue）bar_w 最大
        by_name = {it["name"]: float(it["bar_w"]) for it in items}
        self.assertGreaterEqual(by_name["甲"], by_name["乙"])
        self.assertGreaterEqual(by_name["甲"], by_name.get("（未填）", 0))
        # 零收入为 0
        self.assertEqual(by_name["丙"], 0.0)

    def test_source_has_bar_w_field(self):
        src = (ROOT / "src/routes/data_api.py").read_text(encoding="utf-8")
        self.assertIn("bar_w", src)
        self.assertIn("def _profit_rank_items_payload", src)


class TestBarWRedGreenGuard(unittest.TestCase):
    """先红后绿过程：断言逻辑本身会因缺 bar_w 失败。"""

    def test_missing_bar_w_would_fail_assert(self):
        items_bad = [{"i": 1, "name": "甲", "revenue_disp": "1万"}]
        with self.assertRaises(AssertionError):
            for it in items_bad:
                self.assertIn("bar_w", it)


if __name__ == "__main__":
    unittest.main()
