# -*- coding: utf-8 -*-
"""2.6.9 S8：已删死端点守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestS8DeadEndpointsGone(unittest.TestCase):
    def test_budget_depts_route_removed(self):
        src = (ROOT / "src" / "routes" / "manual.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/budget_depts")', src)
        self.assertNotIn("def api_budget_depts", src)


if __name__ == "__main__":
    unittest.main()
