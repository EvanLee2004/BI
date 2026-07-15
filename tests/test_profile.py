#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视图：统一 full（精简视图已下线）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, render, server  # noqa: E402

_SHELL = '<html lang="zh-CN" data-profile="full"><body><div class="wrap">{}</div></body></html>'


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestViewProfileAlwaysFull(unittest.TestCase):
    def test_always_full(self):
        self.assertEqual(accounts.view_profile({"权限": "管理员"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "整体"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "BU", "可见BU": ["甲"]}), "full")
        self.assertEqual(accounts.view_profile({"权限": "整体", "视图": "executive"}), "full")
        self.assertEqual(accounts.view_profile(None), "full")


class TestApplyProfileNoop(unittest.TestCase):
    def test_noop(self):
        html = _SHELL.format("X")
        self.assertEqual(server._apply_profile(html, "executive"), html)
        self.assertEqual(server._apply_profile(html, "full"), html)
        self.assertEqual(server._apply_profile("", "x"), "")


class TestProfileServing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
            {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
        ])
        server._state["user_html"] = _SHELL.format("USER-MAIN")
        server._state["bu_pages"] = {"BU甲": {"name": "BU甲", "html": _SHELL.format("PAGE-A")}}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def _login(self, account, pw):
        c = self._client()
        c.post("/login", data={"account": account, "password": pw})
        return c

    def test_overall_full(self):
        c = self._login("overall", server.DEFAULT_VIEW_PW)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)

    def test_admin_full(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)

    def test_bu_full(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        r = c.get("/bu/" + quote("BU甲"))
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)


class TestAdminStaticNoProfileToggle(unittest.TestCase):
    def test_no_preview_toggle(self):
        page = server.admin_ui_source()
        self.assertNotIn('id="profBtn"', page)
        self.assertNotIn("精简视图", page)
        self.assertIn('id="chrome"', page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
