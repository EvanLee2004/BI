#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P5：旧整页 SSR 路径 /api/v1/cockpit/view 已真删；shell 仅 fragments。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, server  # noqa: E402


class TestP5NoViewPath(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        p = bu.config_path(self.cfg, self.tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"bus": [{"name": "BU甲", "销售": ["销售A"]}]}, ensure_ascii=False),
                     encoding="utf-8")
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW},
            {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
        ])
        server._state["user_html"] = "<html><body>MAIN</body></html>"
        server._state["summary"] = {"meta": {"year": 2026}, "periods": {}}
        server._state["fragments"] = {
            "title": "t", "particles": "", "logo": "", "version": "", "generated_at": "",
            "pw_modal": "", "period_bar": "", "kpi_views": "K", "trend_html": "",
            "donut_views": "", "pl_views": "", "profit_rank_views": "",
            "receipts_budget": "", "daily_html": "", "rank_views": "", "drawer": "",
        }
        server._state["bu_pages"] = {}
        self.app = server.create_app(self.cfg, root=self.tmp)

    def tearDown(self):
        pass

    def test_view_route_gone(self):
        from fastapi.testclient import TestClient
        c = TestClient(self.app, follow_redirects=False)
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/api/v1/cockpit/view")
        self.assertEqual(r.status_code, 404, r.text[:200])

    def test_fragments_ok(self):
        from fastapi.testclient import TestClient
        c = TestClient(self.app, follow_redirects=False)
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/api/v1/cockpit/fragments")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("mode"), "fragments")
        self.assertIn("fragments", body)
        self.assertIn("chrome_prefix", body)
        self.assertIn("views", body)
        self.assertEqual(body["fragments"].get("rank_views"), "")  # P0 shipped：JS 组装

    def test_shell_has_no_view_string(self):
        shell = (ROOT / "static" / "shell.html").read_text(encoding="utf-8")
        self.assertNotIn("/api/v1/cockpit/view", shell)
        self.assertIn("/api/v1/cockpit/fragments", shell)
        # 源码无 view 路由注册
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn('@app.get("/api/v1/cockpit/view"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
