#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书65·L1：管理端 Vue 单轨守卫（legacy static admin 已下线）。

原 test_admin_static 锁定 admin.js/admin.html.legacy 的用例已删除；
Vue 等价覆盖见 test_admin_vue_54d.py / frontend 管理端组件。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ADMIN_DIR = ROOT / "static" / "admin"


class TestAdminVueOnly(unittest.TestCase):
    def test_legacy_files_gone(self):
        for name in ("admin.js", "admin.html.legacy", "admin.css"):
            self.assertFalse((ADMIN_DIR / name).is_file(), f"legacy 应已删: {name}")

    def test_bootstrap_kept(self):
        """首次部署引导 F-02 仍保留。"""
        p = ADMIN_DIR / "bootstrap.html"
        self.assertTrue(p.is_file())
        self.assertIn("首次取数", p.read_text(encoding="utf-8"))

    def test_admin_app_js_gone(self):
        """GET /admin/app.js → 410，绝不下发旧业务 JS。"""
        import loaders
        import server
        from fastapi.testclient import TestClient

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        orig = server.recompute
        server.recompute = lambda *a, **k: None
        server._state["user_html"] = "<html>u</html>"
        server._state["admin_html"] = "ready"
        server._state["has_data"] = True
        try:
            app = server.create_app(cfg, root=tmp)
            c = TestClient(app, follow_redirects=False)
            r = c.get("/admin/app.js")
            self.assertEqual(r.status_code, 410)
            self.assertNotIn("showGroup", r.text)
            self.assertNotIn("doRefresh", r.text)
        finally:
            server.recompute = orig

    def test_admin_serves_vue_not_legacy_shell(self):
        """已登录且有数据 → Vue dist（含 #app / module），不含 legacy admin 骨架。"""
        import loaders
        import server
        from fastapi.testclient import TestClient

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config()
        orig = server.recompute
        server.recompute = lambda *a, **k: None
        server._state["has_data"] = True
        server._state["admin_html"] = "ready"
        try:
            app = server.create_app(cfg, root=tmp)
            c = TestClient(app, follow_redirects=False)
            # 管理员登录
            r = c.post(
                "/admin/login",
                data={"account": "lushasha", "password": server.DEFAULT_PW},
            )
            self.assertIn(r.status_code, (200, 303), r.text[:200])
            r2 = c.get("/admin")
            self.assertEqual(r2.status_code, 200)
            body = r2.text
            self.assertNotIn("onclick=\"showGroup", body)
            self.assertNotIn("/admin/app.js", body)
            # Vue index 特征
            self.assertTrue(
                'id="app"' in body or "type=\"module\"" in body or "/assets/" in body,
                body[:300],
            )
        finally:
            server.recompute = orig


if __name__ == "__main__":
    unittest.main()
