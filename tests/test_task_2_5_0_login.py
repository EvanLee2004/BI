#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.5.0：统一登录分流 + next 白名单 + /admin/login 兼容（驱动真实 login_redirect + 路由）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import authz  # noqa: E402
import login_redirect  # noqa: E402


def _acc(role: str, name: str = "u", bus: list | None = None) -> dict:
    a = {"账号": name, "显示名": name, "权限": role, "密码": "x", "密码版本": 1}
    if bus is not None:
        a["可见BU"] = bus
    return a


class TestLoginRedirectUnit(unittest.TestCase):
    def test_default_admin_overall_bu(self):
        self.assertEqual(
            login_redirect.default_redirect_for_account(_acc("管理员", "lushasha")),
            "/admin",
        )
        self.assertEqual(
            login_redirect.default_redirect_for_account(_acc("整体", "overall")),
            "/",
        )
        pages = {"多语营销": {}, "游戏": {}}
        r = login_redirect.default_redirect_for_account(
            _acc("BU", "j", ["多语营销", "游戏"]), bu_pages=pages
        )
        self.assertTrue(r.startswith("/bu/"), r)
        self.assertIn("多语营销", unquote(r))

    def test_next_whitelist(self):
        admin = _acc("管理员", "a")
        bu = _acc("BU", "b", ["多语营销"])
        overall = _acc("整体", "o")
        self.assertEqual(login_redirect.sanitize_next_path("/admin", admin), "/admin")
        self.assertIsNone(login_redirect.sanitize_next_path("/admin", bu))
        self.assertIsNone(login_redirect.sanitize_next_path("/admin/settings", bu))
        self.assertIsNone(login_redirect.sanitize_next_path("https://evil.com", admin))
        self.assertIsNone(login_redirect.sanitize_next_path("//evil.com", admin))
        self.assertEqual(login_redirect.sanitize_next_path("/", overall), "/")
        self.assertIsNone(login_redirect.sanitize_next_path("/", bu))  # 纯 BU 不可 next 整体
        ok = login_redirect.sanitize_next_path("/bu/多语营销", bu)
        self.assertIsNotNone(ok)
        self.assertIsNone(login_redirect.sanitize_next_path("/bu/游戏", bu))

    def test_resolve_prefers_safe_next(self):
        admin = _acc("管理员", "a")
        r = login_redirect.resolve_login_redirect(admin, "/admin/settings")
        self.assertEqual(r, "/admin/settings")
        bu = _acc("BU", "b", ["多语营销"])
        r2 = login_redirect.resolve_login_redirect(bu, "/admin", bu_pages={"多语营销": {}})
        self.assertTrue(r2.startswith("/bu/"), r2)


class TestUnifiedLoginHttp(unittest.TestCase):
    """TestClient 真路径：/api/v1/login redirect + /admin/login 303。"""

    @classmethod
    def setUpClass(cls):
        import loaders
        import server
        from support import fake_bu_page, fake_main_frags, fake_views

        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        # 经 accounts.save_accounts 规范化（与 test_auth 一致）
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": server.DEFAULT_VIEW_PW,
                },
                {
                    "账号": "user_a",
                    "显示名": "BU甲",
                    "权限": "BU甲",
                    "密码": server.DEFAULT_VIEW_PW,
                },
            ],
        )
        server._state["user_html"] = "<html></html>"
        server._state["fragments"] = fake_main_frags("M")
        server._state["views"] = fake_views("M")
        server._state["bu_pages"] = {"BU甲": fake_bu_page("BU甲", "A"), "BU乙": fake_bu_page("BU乙", "B")}
        server._state["admin_html"] = "x"
        server._state["has_data"] = True
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_api_login_redirects(self):
        c = self._client()
        r = c.post("/api/v1/login", json={"account": "lushasha", "password": self.server.DEFAULT_PW})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("redirect"), "/admin")

        r = c.post(
            "/api/v1/login", json={"account": "overall", "password": self.server.DEFAULT_VIEW_PW}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("redirect"), "/")

        r = c.post(
            "/api/v1/login", json={"account": "user_a", "password": self.server.DEFAULT_VIEW_PW}
        )
        self.assertEqual(r.status_code, 200)
        redir = r.json().get("redirect") or ""
        self.assertTrue(redir.startswith("/bu/"), redir)
        self.assertIn("BU甲", unquote(redir))

    def test_bu_next_admin_ignored(self):
        c = self._client()
        r = c.post(
            "/api/v1/login",
            json={
                "account": "user_a",
                "password": self.server.DEFAULT_VIEW_PW,
                "next": "/admin",
            },
        )
        self.assertEqual(r.status_code, 200)
        redir = r.json().get("redirect") or ""
        self.assertNotIn("/admin", redir)
        self.assertTrue(redir.startswith("/bu/"), redir)

    def test_admin_login_get_redirects_unified(self):
        c = self._client()
        r = c.get("/admin/login")
        self.assertEqual(r.status_code, 303, r.text)
        loc = r.headers.get("location") or ""
        self.assertTrue(loc.startswith("/login"), loc)
        self.assertIn("next", loc)

    def test_admin_root_unauth_redirects_login(self):
        c = self._client()
        r = c.get("/admin")
        self.assertEqual(r.status_code, 303)
        self.assertTrue((r.headers.get("location") or "").startswith("/login"))

    def test_open_redirect_blocked(self):
        c = self._client()
        r = c.post(
            "/api/v1/login",
            json={
                "account": "lushasha",
                "password": self.server.DEFAULT_PW,
                "next": "https://evil.example/",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("redirect"), "/admin")


class TestNoStandaloneAdminLoginUi(unittest.TestCase):
    def test_source_no_admin_login_product_title_as_entry(self):
        # 删除 LoginView 后此测仍应通过：router 不挂独立登录组件
        router = (ROOT / "frontend" / "src" / "admin" / "router.ts").read_text(encoding="utf-8")
        self.assertIn("/login", router)
        self.assertNotIn("views/LoginView.vue", router)
        api = (ROOT / "frontend" / "src" / "admin" / "api.ts").read_text(encoding="utf-8")
        self.assertNotIn("/admin/login", api)
        lv = ROOT / "frontend" / "src" / "admin" / "views" / "LoginView.vue"
        # 允许文件暂存一版；删后不存在即可
        if lv.is_file():
            # 若仍存在，不得被 router 引用（上面已断言）
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
