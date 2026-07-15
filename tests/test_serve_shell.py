#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产路径：SERVE_SHELL=True 且 shell.html 存在时，已登录 / 返回 fetch 壳而非直出整页。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, server  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestServeShellProductionPath(unittest.TestCase):
    def setUp(self):
        self._prev = server.SERVE_SHELL
        server.SERVE_SHELL = True
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
            {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
        ])
        # 标记：若误直出整页会带上 USER-MAIN；壳只含加载文案与 fetch view
        server._state["user_html"] = (
            '<html lang="zh-CN"><body><div class="wrap">USER-MAIN</div></body></html>'
        )
        server._state["bu_pages"] = {}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.assertTrue((server.STATIC_DIR / "shell.html").is_file())

    def tearDown(self):
        server.SERVE_SHELL = self._prev

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def test_logged_in_overall_gets_shell_not_inline_page(self):
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.text
        # shell 特征
        self.assertIn("加载驾驶舱", body)
        self.assertIn("/api/v1/cockpit/view", body)
        # 不得直出整页缓存
        self.assertNotIn("USER-MAIN", body)
        self.assertNotIn('class="wrap"', body)

    def test_serve_shell_false_still_inline(self):
        """对照：关开关后仍直出 HTML（与测试默认一致）。"""
        server.SERVE_SHELL = False
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("USER-MAIN", r.text)
        self.assertNotIn("加载驾驶舱", r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
