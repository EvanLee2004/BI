#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产路径：已登录 / 固定 shell；无 SERVE_SHELL 直出化石。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts
import bu
import loaders
import server  # noqa: E402
from support import fake_main_frags, fake_views  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestServeShellProductionPath(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = '<html><body><div class="wrap">USER-MAIN</div></body></html>'
        # 模拟 publish 预拼缓存
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["summary"] = {
            "meta": {"year": 2026, "year_key": "2026年", "tab_groups": {"季度": [], "月": []}},
            "periods": {},
        }
        server._state["views"] = fake_views("USER-MAIN")
        server._state["bu_pages"] = {}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_logged_in_overall_gets_shell_not_inline_page(self):
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("加载驾驶舱", body)
        self.assertIn("/api/v1/cockpit/fragments", body)
        self.assertIn("assemble/page.js", body)
        self.assertNotIn("USER-MAIN", body)
        # 碎片 API：卡字段须 strip；内容在 views
        fr = c.get("/api/v1/cockpit/fragments")
        self.assertEqual(fr.status_code, 200)
        body = fr.json()
        self.assertEqual(body["fragments"].get("kpi_views"), "")
        kpi_body = (body.get("views") or {}).get("kpi_body") or {}
        self.assertIn("USER-MAIN", " ".join(str(v) for v in kpi_body.values()))

    def test_no_serve_shell_attr_fossil(self):
        """P5：不存在 SERVE_SHELL 开关（或即使残留也不得再控制 / 直出）。"""
        # 模块上不应再作为生产开关文档化使用；若属性残留，/ 仍须是 shell
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        if hasattr(server, "SERVE_SHELL"):
            server.SERVE_SHELL = False  # 即便有人误设，也不得直出
        r = c.get("/")
        self.assertIn("加载驾驶舱", r.text)
        self.assertNotIn("USER-MAIN", r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
