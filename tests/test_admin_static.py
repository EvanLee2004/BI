#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.5 管理端 static/admin 抽取守卫。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ADMIN_DIR = ROOT / "static" / "admin"
GOLDEN = ROOT / "golden" / "admin_baseline.html"


class TestAdminStaticFiles(unittest.TestCase):
    def test_files_exist(self):
        for name in ("admin.html", "admin.css", "admin.js", "bootstrap.html"):
            p = ADMIN_DIR / name
            self.assertTrue(p.is_file(), f"missing {p}")

    def test_js_core_markers(self):
        js = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")
        for token in (
            "showGroup", "showManual", "pickTable", "checkUpdate", "doRefresh",
            "loadHealth", "loadSettings", "loadAccts", "loadVersion",
            "showReview", "dxTbl", "MANUAL_ITEMS", "/api/update/apply",
            "/api/update/check", "/api/alloc_ratios", "/api/detax_rates",
            "setSaveAll", "openVerDrawer",
        ):
            self.assertIn(token, js, token)

    def test_no_duplicate_ids_in_admin_html(self):
        html = (ADMIN_DIR / "admin.html").read_text(encoding="utf-8")
        ids = re.findall(r'\bid=["\']([^"\']+)["\']', html)
        from collections import Counter
        dups = {k: v for k, v in Counter(ids).items() if v > 1}
        self.assertEqual(dups, {}, f"duplicate ids: {dups}")

    def test_no_client_money_math(self):
        js = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")
        # 管理端允许 parseAmount 等表单辅助；禁止 toFixed/parseFloat 做金额展示运算
        for bad in ("toFixed(", "parseFloat("):
            self.assertNotIn(bad, js, bad)

    def test_static_admin_complete(self):
        """static/admin 四件齐全且 app 入口引用正确（已无 server 内嵌副本）。"""
        for name in ("admin.html", "admin.css", "admin.js", "bootstrap.html"):
            self.assertTrue((ADMIN_DIR / name).is_file(), name)
        html = (ADMIN_DIR / "admin.html").read_text(encoding="utf-8")
        self.assertIn("/static/admin/admin.css", html)
        self.assertIn("/admin/app.js", html)
        js = (ADMIN_DIR / "admin.js").read_text(encoding="utf-8")
        self.assertIn("__MANUAL_ITEMS__", js)

    def test_external_html_links(self):
        html = (ADMIN_DIR / "admin.html").read_text(encoding="utf-8")
        self.assertIn('href="/static/admin/admin.css"', html)
        self.assertIn('src="/admin/app.js"', html)
        self.assertNotIn("<style>", html)
        # app logic not inlined
        self.assertNotIn("function showGroup", html)


class TestAdminStaticHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        import accounts, server, loaders
        cls.tmp = Path(tempfile.mkdtemp())
        cls.cfg = loaders.load_config(ROOT)
        accounts.save_accounts(cls.cfg, cls.tmp, [
            {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW},
        ])
        # 标记「已取数成功」即可进完整台（页面读 static）
        server._state["admin_html"] = server._admin_page("", {}, cls.cfg)
        server._state["user_html"] = "<html>u</html>"
        server._state["summary"] = {"meta": {}, "periods": {}}
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def test_unauthenticated_admin_is_login(self):
        r = self._client().get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("管理员端登录", r.text)
        self.assertIn('action="/admin/login"', r.text)

    def test_static_admin_html_is_shell_without_session_data(self):
        """未登录直接读 /static/admin/admin.html 只是壳，无会话态数据。"""
        r = self._client().get("/static/admin/admin.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("管理员控制台", r.text)
        self.assertIn("/admin/app.js", r.text)
        # 壳里不应出现已注入的手填 JSON 数组（仍是占位在 app.js）
        self.assertNotIn("营销人力成本", r.text)

    def test_app_js_injects_manual_items(self):
        r = self._client().get("/admin/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("function showGroup", r.text)
        self.assertNotIn("__MANUAL_ITEMS__", r.text)
        self.assertIn("营销人力成本", r.text)

    def test_logged_in_serves_static_admin(self):
        """登录后 /admin 只走 static 骨架（外链 css/js，不再内嵌整页）。"""
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.server.DEFAULT_PW})
        r = c.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("管理员控制台", r.text)
        self.assertIn("/static/admin/admin.css", r.text)
        self.assertIn("/admin/app.js", r.text)
        self.assertNotIn("<style>", r.text)
        self.assertNotIn("function showGroup", r.text)


class TestAdminGoldenSkeleton(unittest.TestCase):
    def test_external_skeleton_matches_golden_normalized(self):
        if not GOLDEN.exists():
            self.skipTest("no golden")
        golden = GOLDEN.read_text(encoding="utf-8")
        ext = (ADMIN_DIR / "admin.html").read_text(encoding="utf-8")

        def body_core(h: str) -> str:
            # strip head assets / scripts; keep body markup for structure
            h = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
            h = re.sub(r"<link[^>]*>", "", h)
            h = re.sub(r"<script[^>]*>.*?</script>", "", h, flags=re.S)
            h = re.sub(r"<script[^>]*src=[^>]*>\s*</script>", "", h)
            h = re.sub(r"\s+", " ", h).strip()
            return h

        g, e = body_core(golden), body_core(ext)
        self.assertEqual(g, e, "admin body skeleton differs from golden after asset strip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
