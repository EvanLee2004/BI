#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.7.1：kanban_sid 单会话；旧 cookie 不能维持登录（驱动真实 session_ctx + 登录路径）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import auth_session  # noqa: E402
import session_ctx  # noqa: E402
from app_state import COOKIE, SID_COOKIE, VCOOKIE  # noqa: E402


class TestResolveSidOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = {"data_dir": "数据", "db_path": "看板.db"}
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
                    "密码": "kanban2026",
                },
                {
                    "账号": "overall",
                    "显示名": "整体",
                    "权限": "整体",
                    "密码": "view2026",
                },
                {
                    "账号": "user_a",
                    "显示名": "BU甲",
                    "权限": "BU甲",
                    "密码": "view2026",
                },
            ],
        )
        self.sec = auth_session.load_or_init_secret(self.cfg, self.tmp)
        session_ctx.set_today_override(None)

    def tearDown(self):
        session_ctx.set_today_override(None)

    def _tok(self, account: str) -> str:
        acc = accounts.find_account(self.cfg, self.tmp, account)
        return auth_session.make_token(
            self.sec, account, pw_ver=accounts.password_version_of(acc)
        )

    def test_sid_auth_works(self):
        cookies = {SID_COOKIE: self._tok("overall")}
        ctx = session_ctx.resolve_session(cookies, sec=self.sec, cfg=self.cfg, root=self.tmp)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.account, "overall")
        self.assertEqual(ctx.source, "sid")
        self.assertFalse(ctx.needs_upgrade)

    def test_legacy_session_alone_fails(self):
        cookies = {COOKIE: self._tok("lushasha")}
        ctx = session_ctx.resolve_session(cookies, sec=self.sec, cfg=self.cfg, root=self.tmp)
        self.assertIsNone(ctx)

    def test_legacy_view_alone_fails(self):
        cookies = {VCOOKIE: self._tok("user_a")}
        ctx = session_ctx.resolve_session(cookies, sec=self.sec, cfg=self.cfg, root=self.tmp)
        self.assertIsNone(ctx)

    def test_legacy_ignored_when_sid_present(self):
        cookies = {
            SID_COOKIE: self._tok("overall"),
            COOKIE: self._tok("lushasha"),
            VCOOKIE: self._tok("user_a"),
        }
        ctx = session_ctx.resolve_session(cookies, sec=self.sec, cfg=self.cfg, root=self.tmp)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.account, "overall")
        self.assertEqual(ctx.source, "sid")


class TestLoginSetsSidOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import loaders
        import server
        from support import fake_bu_page, fake_main_frags, fake_views

        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
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
        server._state["fragments"] = fake_main_frags("M")
        server._state["views"] = fake_views("M")
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "A"),
            "BU乙": fake_bu_page("BU乙", "B"),
        }
        server._state["admin_html"] = "x"
        server._state["has_data"] = True
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_api_login_sets_sid_not_legacy_as_primary(self):
        c = self._client()
        for acc, pw, redir_prefix in [
            ("lushasha", self.server.DEFAULT_PW, "/admin"),
            ("overall", self.server.DEFAULT_VIEW_PW, "/"),
            ("user_a", self.server.DEFAULT_VIEW_PW, "/bu/"),
        ]:
            r = c.post("/api/v1/login", json={"account": acc, "password": pw})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertTrue(
                str(body.get("redirect") or "").startswith(redir_prefix)
                or body.get("redirect") == redir_prefix,
                body,
            )
            self.assertIn(SID_COOKIE, c.cookies)
            sc = str(r.headers).lower()
            self.assertIn("kanban_sid", sc)

    def test_logout_clears_sid(self):
        c = self._client()
        c.post("/api/v1/login", json={"account": "lushasha", "password": self.server.DEFAULT_PW})
        r = c.post("/api/v1/logout")
        self.assertEqual(r.status_code, 200)
        raw = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []
        if not raw and r.headers.get("set-cookie"):
            raw = [r.headers.get("set-cookie")]
        joined = " ".join(raw).lower()
        for name in (SID_COOKIE, COOKIE, VCOOKIE):
            self.assertTrue(
                any(line.lower().startswith(name.lower() + "=") for line in raw),
                f"logout must Set-Cookie delete {name}; got {raw}",
            )
        self.assertIn("max-age=0", joined)
        c.cookies.clear()
        r2 = c.get("/api/v1/session")
        self.assertEqual(r2.status_code, 401)

    def test_legacy_cookie_cannot_auth(self):
        """2.7.1：仅旧 cookie 不能维持登录。"""
        c = self._client()
        sec = auth_session.load_or_init_secret(self.cfg, self.tmp)
        acc = accounts.find_account(self.cfg, self.tmp, "user_a")
        tok = auth_session.make_token(sec, "user_a", pw_ver=accounts.password_version_of(acc))
        c.cookies.set(VCOOKIE, tok)
        r = c.get("/api/v1/session")
        self.assertEqual(r.status_code, 401, r.text)
        c.cookies.clear()
        c.cookies.set(COOKIE, tok)
        r2 = c.get("/api/v1/session")
        self.assertEqual(r2.status_code, 401, r2.text)

    def test_bu_next_admin_still_blocked(self):
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

    def test_pure_bu_root_redirect(self):
        c = self._client()
        c.post("/api/v1/login", json={"account": "user_a", "password": self.server.DEFAULT_VIEW_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 303)
        self.assertIn("/bu/", r.headers.get("location") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
