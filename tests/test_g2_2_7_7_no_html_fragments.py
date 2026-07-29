#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2 · 真门禁：刷新不预装 HTML 碎片；fragments HTTP 404；看数走 VM。"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestG2NoHtmlFragments(unittest.TestCase):
    def test_generate_no_html_fragments(self):
        if not (ROOT / "_golden_data").exists():
            self.skipTest("缺 _golden_data")
        import core
        import loaders

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        summary, html, _ing, bu_pages = core.generate(
            cfg, datetime.date(2026, 6, 30), trigger="g2"
        )
        self.assertEqual(html, "")
        self.assertFalse(summary.get("_fragments"))
        self.assertTrue(summary.get("_views"))
        for name, page in (bu_pages or {}).items():
            self.assertNotIn("fragments", page)
            self.assertTrue(page.get("views"), name)

    def test_fragments_routes_unregistered_http_404(self):
        import accounts
        import bu
        import loaders
        import server

        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/cockpit/fragments")', src)
        self.assertNotIn('@app.get("/api/v1/cockpit/bu/{name}/fragments")', src)

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        p = bu.config_path(cfg, tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"bus":[{"name":"BU甲","销售":["销售A"]}]}', encoding="utf-8")
        accounts.save_accounts(
            cfg,
            tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                },
            ],
        )
        server._state["summary"] = {"meta": {"year": 2026}, "periods": {}}
        server._state["views"] = {}
        server._state["has_data"] = True
        app = server.create_app(cfg, root=tmp)
        from fastapi.testclient import TestClient

        c = TestClient(app, follow_redirects=False)
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(c.get("/api/v1/cockpit/fragments").status_code, 404)
        self.assertEqual(
            c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
