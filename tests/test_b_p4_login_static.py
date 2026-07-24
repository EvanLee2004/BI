#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P4 / 2.5.0：唯一登录 static 为 view_login；admin_login 仅跳转壳（无独立门面表单）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestP4LoginStatic(unittest.TestCase):
    def test_view_login_posts_api_and_forwards_next(self):
        p = ROOT / "static" / "view_login.html"
        self.assertTrue(p.is_file())
        t = p.read_text(encoding="utf-8")
        self.assertIn("/api/v1/login", t)
        self.assertNotIn("{err}", t)
        self.assertNotIn("{account}", t)
        # 2.5.0：深链 next 必须进 JSON body（与 Vue LoginView 一致）
        self.assertIn('q.get("next")', t)
        self.assertIn("body.next", t)

    def test_admin_login_is_redirect_stub_not_product_form(self):
        p = ROOT / "static" / "admin_login.html"
        self.assertTrue(p.is_file(), "书签兼容文件可保留为跳转壳")
        t = p.read_text(encoding="utf-8")
        self.assertIn("/login", t)
        self.assertIn("next", t)
        # 禁止独立管理登录产品表单
        self.assertNotIn("管理员端登录", t)
        self.assertNotIn("<form", t)
        self.assertNotIn("/api/v1/login", t)
        self.assertNotIn('id="loginForm"', t)
        self.assertNotIn('name="password"', t)

    def test_server_no_login_format_helpers(self):
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("def _login_page", src)
        self.assertNotIn("def _view_login_page", src)
        self.assertIn("view_login.html", src)
        # 2.5.0：_admin_login_file 不再读 admin 独立皮当登录 UI
        self.assertIn("def _admin_login_file", src)
        self.assertIn("login_redirect", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
