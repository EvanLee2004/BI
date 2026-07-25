# -*- coding: utf-8 -*-
"""2.6.1 R2/R6：rankings/full 鉴权；多语营销映射；预算展示。"""
from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import server

ROOT = Path(__file__).resolve().parents[1]


class TestRankingsFullApi(unittest.TestCase):
    def test_rankings_full_route_exists_and_auth(self):
        """未登录 → 401；路由已注册。"""
        app = server.create_app(
            {
                "data_dir": str(ROOT / "数据"),
                "db_path": str(ROOT / "数据" / "看板.db"),
                "serve_static": True,
                "zhiyun_auto_fetch": False,
            },
            root=ROOT,
        )
        c = TestClient(app)
        r = c.get("/api/v1/rankings/full", params={"period": "2026年", "dim": "sales"})
        self.assertEqual(r.status_code, 401)

    def test_pc_to_bu_maps_duoyu_yingxiao(self):
        from profit.constants import _PC_TO_BU
        from profit.summary import normalize_profit_center

        self.assertEqual(normalize_profit_center("多语营销"), "营销")
        self.assertEqual(_PC_TO_BU.get("多语营销"), "营销")


class TestBudgetPctNo999(unittest.TestCase):
    def test_domain_kpi_bar(self):
        from domain.pl.structure import kpi_target_bar

        bar = kpi_target_bar(
            "order",
            "2026年",
            {"orders": 1e10},
            {"order": {"target": 1.0, "done": 1e10, "pct": 99999.0}},
        )
        self.assertEqual(bar["pct_disp"], "目标待校准")
        self.assertNotIn("999%", bar["pct_disp"])


if __name__ == "__main__":
    unittest.main()
