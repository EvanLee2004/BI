#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.1.0 / G2：generate 只挂 _views；bu_pages 无 HTML 碎片；fragments HTTP 404。"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import server  # noqa: E402
from support import fake_views  # noqa: E402


class TestPublishOnce(unittest.TestCase):
    def test_generate_caches_client_ready(self):
        import core

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "看板.db"
        cfg["zhiyun_auto_fetch"] = False
        summary, html, ing, bu_pages = core.generate(
            cfg, datetime.date(2026, 6, 30), trigger="publish-once"
        )
        self.assertFalse(summary.get("_fragments"), "generate 不得挂 _fragments")
        self.assertEqual(html, "", "运行态 html 应为空串")
        views = summary.get("_views") or {}
        self.assertTrue(
            views.get("period_keys") or views.get("rankings_view"),
            "generate 须挂 client-ready _views",
        )
        if bu_pages:
            for name, page in bu_pages.items():
                self.assertNotIn("fragments", page, f"BU {name} 不应再有 fragments 键")
                self.assertFalse(page.get("html"), f"BU {name} 不得预装 html")
                self.assertTrue(
                    (page.get("views") or {}).get("period_keys")
                    or (page.get("views") or {}).get("rankings_view"),
                    f"BU {name} 应有 views",
                )

    def test_http_fragments_404_and_views_state(self):
        """_state 仅 views；fragments 路由 404。"""
        import accounts
        import bu

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        p = bu.config_path(cfg, tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"bus":[{"name":"BU甲","销售":["销售A"]}]}', encoding="utf-8")
        accounts.save_accounts(
            cfg,
            tmp,
            [
                {"账号": "overall", "显示名": "整", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
                {"账号": "lushasha", "显示名": "管", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "user_a", "显示名": "甲", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        mark = "CACHED-VIEWS-MARK-XYZ"
        views = fake_views(mark)
        server._state.pop("fragments", None)
        server._state["views"] = views
        server._state["summary"] = {
            "meta": {"year_key": "2026年", "year": 2026},
            "periods": {"2026年": {}},
        }
        server._state["bu_pages"] = {
            "BU甲": {
                "name": "BU甲",
                "views": fake_views("PAGE-A"),
                "summary": {
                    "meta": {"year_key": "2026年", "year": 2026},
                    "periods": {"2026年": {}},
                },
            }
        }
        server._state["admin_html"] = "ready"
        server._state["has_data"] = True
        app = server.create_app(cfg, root=tmp)
        from fastapi.testclient import TestClient

        c = TestClient(app, follow_redirects=False)
        r = c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(c.get("/api/v1/cockpit/fragments").status_code, 404)
        views = server._state.get("views") or {}
        rk = (views.get("rankings_view") or {})
        titles = []
        for pv in rk.values():
            if isinstance(pv, dict):
                sales = pv.get("sales") or {}
                if isinstance(sales, dict) and sales.get("title"):
                    titles.append(str(sales["title"]))
        self.assertIn(mark, " ".join(titles))
        c2 = TestClient(app, follow_redirects=False)
        r2 = c2.post("/login", data={"account": "user_a", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r2.status_code, 303)
        self.assertEqual(
            c2.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
