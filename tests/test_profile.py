#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简视图已下线守卫：响应中不得出现 executive / data-profile。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, server  # noqa: E402

_SHELL = '<html lang="zh-CN"><body><div class="wrap">{}</div></body></html>'


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestNoProfileResidue(unittest.TestCase):
    """守卫：页面与管理端静态中无精简视图 / data-profile 残留。"""

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
                {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = _SHELL.format("USER-MAIN")
        server._state["bu_pages"] = {"BU甲": {"name": "BU甲", "html": _SHELL.format("PAGE-A")}}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _assert_no_profile(self, text: str):
        self.assertNotIn("executive", text)
        self.assertNotIn("data-profile", text)

    def test_overall_and_bu_pages_have_no_profile(self):
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self._assert_no_profile(r.text)

        c2 = self._client()
        c2.post("/login", data={"account": "user_a", "password": server.DEFAULT_VIEW_PW})
        r2 = c2.get("/bu/" + quote("BU甲"))
        self.assertEqual(r2.status_code, 200)
        self._assert_no_profile(r2.text)

    def test_admin_static_no_profile_toggle(self):
        page = server.admin_ui_source()
        self.assertNotIn('id="profBtn"', page)
        self.assertNotIn("精简视图", page)
        self._assert_no_profile(page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
