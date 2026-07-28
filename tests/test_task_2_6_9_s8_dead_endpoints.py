# -*- coding: utf-8 -*-
"""2.6.9 S8：已删死端点守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestS8DeadEndpointsGone(unittest.TestCase):
    def test_budget_depts_route_removed(self):
        src = (ROOT / "src" / "routes" / "manual.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/admin/budget_depts")', src)
        self.assertNotIn("def api_budget_depts", src)

    def test_detail_meta_route_removed(self):
        src = (ROOT / "src" / "routes" / "data_api.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/admin/detail/meta")', src)
        self.assertNotIn("def api_detail_meta", src)

    def test_client_error_stats_route_removed(self):
        src = (ROOT / "src" / "routes" / "data_api.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/client-error/stats")', src)
        self.assertNotIn("def api_client_error_stats", src)

    def test_legacy_cockpit_json_routes_removed(self):
        """S8-C：旧 /api/v1/cockpit JSON 已删；VM 路径保留。2.7.7：fragments 死 API 仍注册但恒 404。"""
        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/cockpit")\n', src)
        self.assertNotIn("def api_v1_cockpit(", src)
        self.assertNotIn('@app.get("/api/v1/cockpit/bu/{name}")', src)
        self.assertNotIn("def api_v1_cockpit_bu(", src)
        self.assertIn('@app.get("/api/v1/vm/cockpit")', src)
        # fragments 路由可仍在（404 桩），但实现必须 raise 404
        self.assertIn("status_code=404", src)
        self.assertIn("fragments 已废止", src)


if __name__ == "__main__":
    unittest.main()
