#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-P4 增补：登录页为 static，错误由 API 前端渲染（服务端不再 format 拼 err）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestP4LoginStatic(unittest.TestCase):
    def test_static_login_files(self):
        for name in ("view_login.html", "admin_login.html"):
            p = ROOT / "static" / name
            self.assertTrue(p.is_file(), name)
            t = p.read_text(encoding="utf-8")
            self.assertIn("/api/v1/login", t)
            self.assertNotIn("{err}", t)
            self.assertNotIn("{account}", t)

    def test_server_no_login_format_helpers(self):
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("def _login_page", src)
        self.assertNotIn("def _view_login_page", src)
        self.assertIn("view_login.html", src)
        self.assertIn("admin_login.html", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
