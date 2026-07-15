#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次2 · publish-once：generate 一次产出 client-ready fragments+views，HTTP 直接取缓存。

守卫：
- generate 后 _fragments 已 strip、_views 有 period_keys/rankings_view
- BU pages 同理
- client_strip_fragments 对已 strip 缓存幂等；assert_clean 能抓回潮
- 不在 HTTP 路径强制 rebuild（缓存 views 原样下发）
"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import api_v1  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
from support import fake_bu_page, fake_main_frags, fake_views  # noqa: E402


class TestPublishOnce(unittest.TestCase):
    def test_generate_caches_client_ready(self):
        import core

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        summary, html, ing, bu_pages = core.generate(cfg, datetime.date(2026, 6, 30), trigger="publish-once")
        self.assertTrue(html)
        fr = summary.get("_fragments") or {}
        views = summary.get("_views") or {}
        self.assertTrue(fr, "generate 须挂 _fragments")
        self.assertTrue(views.get("period_keys") or views.get("rankings_view"), "generate 须挂 client-ready _views")
        self.assertTrue(
            api_v1.fragments_client_fields_empty(fr),
            f"publish-once fragments 应已 strip: {[f for f in api_v1._CLIENT_ASSEMBLE_FIELDS if fr.get(f)]}",
        )
        # 幂等 strip + assert_clean 不炸
        api_v1.client_strip_fragments(fr, assert_clean=True)
        # BU
        if bu_pages:
            for name, page in bu_pages.items():
                self.assertTrue(
                    api_v1.fragments_client_fields_empty(page.get("fragments") or {}), f"BU {name} fragments 应已 strip"
                )
                self.assertTrue(
                    (page.get("views") or {}).get("period_keys") or (page.get("views") or {}).get("rankings_view"),
                    f"BU {name} 应有 views",
                )

    def test_strip_assert_clean_catches_dirty(self):
        dirty = {"kpi_views": "预拼串", "title": "t"}
        with self.assertRaises(AssertionError):
            api_v1.client_strip_fragments(dirty, assert_clean=True)
        clean = api_v1.client_strip_fragments(dirty)
        self.assertEqual(clean.get("kpi_views"), "")
        api_v1.client_strip_fragments(clean, assert_clean=True)

    def test_http_serves_cached_views_without_rebuild(self):
        """_state 已有 strip fragments + views 时，HTTP 原样下发 views 标记。"""
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
        fr = fake_main_frags("FULL-PRE")
        fr = api_v1.client_strip_fragments(fr)
        views = fake_views(mark)
        server._state["user_html"] = "<html></html>"
        server._state["fragments"] = fr
        server._state["views"] = views
        server._state["summary"] = {
            "meta": {"year_key": "2026年", "year": 2026},
            "periods": {"2026年": {}},
        }
        server._state["bu_pages"] = {
            "BU甲": {
                "name": "BU甲",
                "html": "<html></html>",
                "fragments": api_v1.client_strip_fragments(fake_bu_page("BU甲", "PAGE-A")["fragments"]),
                "views": fake_views("PAGE-A"),
                "summary": {"meta": {"year_key": "2026年", "year": 2026}, "periods": {"2026年": {}}},
            }
        }
        server._state["admin_html"] = "ready"
        app = server.create_app(cfg, root=tmp)
        from fastapi.testclient import TestClient

        c = TestClient(app, follow_redirects=False)
        r = c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r.status_code, 303)
        pack = c.get("/api/v1/cockpit/fragments").json()
        self.assertEqual(pack["fragments"].get("kpi_views"), "")
        self.assertIn(mark, " ".join((pack.get("views") or {}).get("kpi_body", {}).values()))
        # BU
        c2 = TestClient(app, follow_redirects=False)
        r2 = c2.post("/login", data={"account": "user_a", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r2.status_code, 303)
        bpack = c2.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").json()
        self.assertEqual(bpack["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-A", " ".join((bpack.get("views") or {}).get("kpi_body", {}).values()))


if __name__ == "__main__":
    unittest.main()
