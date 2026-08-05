# -*- coding: utf-8 -*-
"""3.7.14 审计修复：004 client_ip / 005 导出 401·403 / 006 detail 脱敏 / 003 Cookie Secure。

先红后绿：驱动 shipped 入口（csrf_guard / export 路由 / session_ctx / login）。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import authz  # noqa: E402
import loaders  # noqa: E402
import login_guard  # noqa: E402


class Test004ClientIpTrustBoundary(unittest.TestCase):
    """AUDIT-004：仅 loopback 信任 XFF 最左 hop。"""

    def test_loopback_uses_leftmost_xff(self):
        from csrf_guard import client_ip_for_auth

        ip = client_ip_for_auth(
            client_host="127.0.0.1",
            x_forwarded_for="203.0.113.50, 10.0.0.1",
        )
        self.assertEqual(ip, "203.0.113.50")

    def test_loopback_ipv6_uses_xff(self):
        from csrf_guard import client_ip_for_auth

        ip = client_ip_for_auth(
            client_host="::1",
            x_forwarded_for="198.51.100.9",
        )
        self.assertEqual(ip, "198.51.100.9")

    def test_testclient_host_is_loopback_trust_xff(self):
        from csrf_guard import client_ip_for_auth

        ip = client_ip_for_auth(
            client_host="testclient",
            x_forwarded_for="203.0.113.77",
        )
        self.assertEqual(ip, "203.0.113.77")

    def test_external_client_ignores_xff(self):
        from csrf_guard import client_ip_for_auth

        ip = client_ip_for_auth(
            client_host="203.0.113.10",
            x_forwarded_for="1.2.3.4, 5.6.7.8",
        )
        self.assertEqual(ip, "203.0.113.10")

    def test_no_xff_returns_client_host(self):
        from csrf_guard import client_ip_for_auth

        self.assertEqual(client_ip_for_auth(client_host="10.1.2.3", x_forwarded_for=None), "10.1.2.3")
        self.assertEqual(client_ip_for_auth(client_host="10.1.2.3", x_forwarded_for=""), "10.1.2.3")

    def test_login_lock_uses_xff_via_api(self):
        """登录失败锁键须走 client_ip_for_auth（loopback + XFF → 锁远端 IP）。"""
        from fastapi.testclient import TestClient
        import server

        login_guard.reset_all_for_tests()
        tmp = Path(tempfile.mkdtemp(prefix="t3714_ip_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy2(ROOT / "config.json", tmp / "config.json")
        (tmp / "数据").mkdir()
        cfg = loaders.load_config(tmp)
        cfg = dict(cfg)
        cfg["login_max_failures"] = 3
        cfg["login_lock_minutes"] = 30
        accounts.seed_defaults(cfg, tmp)
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        headers = {"X-Forwarded-For": "203.0.113.88"}
        for _ in range(3):
            r = client.post(
                "/api/v1/login",
                json={"account": "lushasha", "password": "wrong-pass-xx"},
                headers=headers,
            )
            self.assertIn(r.status_code, (401, 429), r.text)
        # 同 XFF 应锁定
        r_lock = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": "wrong-pass-xx"},
            headers=headers,
        )
        self.assertEqual(r_lock.status_code, 429, r_lock.text)
        # 另一 IP（另一 XFF）不应被同一把锁误伤
        r_other = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": "wrong-pass-xx"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        self.assertEqual(r_other.status_code, 401, r_other.text)
        login_guard.reset_all_for_tests()


class Test005ExportAuthMatrix(unittest.TestCase):
    """AUDIT-005：未登录 401；已登录无权限/无 cap 403。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import server

        cls.tmp = Path(tempfile.mkdtemp(prefix="t3714_exp_"))
        shutil.copy2(ROOT / "config.json", cls.tmp / "config.json")
        (cls.tmp / "数据").mkdir()
        cls.cfg = loaders.load_config(cls.tmp)
        cls.server = server
        cls._orig_recompute = server.recompute
        server.recompute = lambda *a, **k: None
        server._state["summary"] = {
            "meta": {"year_key": "2026年"},
            "periods": {"2026年": {}},
        }
        server._state["has_data"] = True
        server._state["bu_pages"] = {
            "甲": {
                "name": "甲",
                "summary": {"meta": {"year_key": "2026年"}, "periods": {"2026年": {}}},
                "views": {},
            }
        }
        accounts.seed_defaults(cls.cfg, cls.tmp)
        rows = accounts.load_accounts(cls.cfg, cls.tmp)
        rows.append(
            {
                "账号": "no_export",
                "显示名": "无导出",
                "权限": accounts.PERM_MAIN,
                "密码": accounts.DEFAULT_VIEW_PW,
                "能力": {
                    authz.CAP_EXPORT_PL_XLSX: False,
                    authz.CAP_EXPORT_PAGE_HTML: False,
                    authz.CAP_EXPORT_PAGE_PNG: False,
                    authz.CAP_EXPORT_LEDGER_XLSX: False,
                },
            }
        )
        rows.append(
            {
                "账号": "bu_only",
                "显示名": "仅甲",
                "权限": accounts.PERM_BU,
                "可见BU": ["甲"],
                "密码": accounts.DEFAULT_VIEW_PW,
                "能力": {
                    authz.CAP_EXPORT_PAGE_HTML: True,
                    authz.CAP_EXPORT_PAGE_PNG: True,
                    authz.CAP_EXPORT_PL_XLSX: True,
                },
            }
        )
        accounts.save_accounts(cls.cfg, cls.tmp, rows)
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.client = TestClient(cls.app, follow_redirects=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.recompute = cls._orig_recompute
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _login(self, account: str, password: str | None = None) -> dict:
        pw = password or (
            accounts.DEFAULT_ADMIN_PW if account == "lushasha" else accounts.DEFAULT_VIEW_PW
        )
        r = self.client.post("/api/v1/login", json={"account": account, "password": pw})
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.cookies.get(self.server.SID_COOKIE) or r.cookies.get(self.server.COOKIE)
        self.assertTrue(sid)
        return {"Cookie": f"{self.server.SID_COOKIE}={sid}"}

    def test_unauthenticated_export_paths_401(self):
        # 类级 TestClient 可能残留登录 cookie → 先清空
        self.client.cookies.clear()
        paths = [
            "/api/v1/export.html",
            "/api/v1/export.png",
            "/api/v1/export/pl.xlsx",
            "/api/v1/export/bu/甲/html",
            "/api/v1/export/bu/甲/png",
            "/api/v1/export/bu/甲/pl.xlsx",
        ]
        for p in paths:
            with self.subTest(path=p):
                r = self.client.get(p)
                self.assertEqual(r.status_code, 401, f"{p} → {r.status_code} {r.text[:200]}")

    def test_logged_in_no_cap_export_403(self):
        hdr = self._login("no_export")
        for p in (
            "/api/v1/export.html",
            "/api/v1/export.png",
            "/api/v1/export/pl.xlsx",
        ):
            with self.subTest(path=p):
                r = self.client.get(p, headers=hdr)
                self.assertEqual(r.status_code, 403, f"{p} → {r.status_code} {r.text[:200]}")

    def test_bu_user_cannot_export_main_403(self):
        hdr = self._login("bu_only")
        for p in ("/api/v1/export.html", "/api/v1/export/pl.xlsx"):
            with self.subTest(path=p):
                r = self.client.get(p, headers=hdr)
                self.assertEqual(r.status_code, 403, f"{p} → {r.status_code} {r.text[:200]}")

    def test_bu_user_forbidden_other_bu_403_not_401(self):
        hdr = self._login("bu_only")
        r = self.client.get("/api/v1/export/bu/不存在线/html", headers=hdr)
        self.assertEqual(r.status_code, 403, r.text)
        r2 = self.client.get("/api/v1/export/bu/不存在线/pl.xlsx", headers=hdr)
        self.assertEqual(r2.status_code, 403, r2.text)


class Test006ExportDetailSanitized(unittest.TestCase):
    """AUDIT-006：导出失败对外 detail 无异常类名/堆栈路径。"""

    def test_snapshot_build_failure_detail_no_exception_type(self):
        from fastapi.testclient import TestClient
        import server
        from routes import export as export_mod

        tmp = Path(tempfile.mkdtemp(prefix="t3714_san_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy2(ROOT / "config.json", tmp / "config.json")
        (tmp / "数据").mkdir()
        cfg = loaders.load_config(tmp)
        accounts.seed_defaults(cfg, tmp)
        server._state["summary"] = {
            "meta": {"year_key": "2026年"},
            "periods": {"2026年": {}},
        }
        server._state["has_data"] = True
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        r = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE)
        hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}

        # 打桩：组装导出 HTML 时抛带路径的异常
        def _boom(*a, **k):
            raise RuntimeError("/opt/kanban/secret/path.py line 99: boom")

        with mock.patch("export_html.assemble_export_pack", side_effect=_boom):
            resp = client.get("/api/v1/export.html", headers=hdr)
        self.assertIn(resp.status_code, (500, 503), resp.text)
        detail = ""
        try:
            detail = str(resp.json().get("detail") or "")
        except Exception:
            detail = resp.text
        low = detail.lower()
        self.assertNotIn("runtimeerror", low)
        self.assertNotIn("exception", low)
        self.assertNotIn("/opt/kanban", detail)
        self.assertNotIn("secret/path", detail)
        self.assertNotIn("traceback", low)
        # 固定短句应可理解
        self.assertTrue(len(detail) < 80 or "导出" in detail or "失败" in detail, detail)

    def test_pl_xlsx_failure_detail_no_exception_type(self):
        from fastapi.testclient import TestClient
        import server

        tmp = Path(tempfile.mkdtemp(prefix="t3714_plsan_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy2(ROOT / "config.json", tmp / "config.json")
        (tmp / "数据").mkdir()
        cfg = loaders.load_config(tmp)
        accounts.seed_defaults(cfg, tmp)
        server._state["summary"] = {
            "meta": {"year_key": "2026年"},
            "periods": {"2026年": {}},
        }
        server._state["has_data"] = True
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        r = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
        )
        sid = r.cookies.get(server.SID_COOKIE) or r.cookies.get(server.COOKIE)
        hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}

        def _boom(*a, **k):
            raise ValueError("hidden.TypeName at /var/lib/x.py")

        with mock.patch("export_pl_xlsx.build_pl_xlsx_bytes", side_effect=_boom):
            resp = client.get("/api/v1/export/pl.xlsx", headers=hdr)
        self.assertIn(resp.status_code, (500, 503), resp.text)
        detail = str(resp.json().get("detail") or "")
        low = detail.lower()
        self.assertNotIn("valuerror", low)
        self.assertNotIn("valueerror", low)
        self.assertNotIn("/var/lib", detail)
        self.assertNotIn("typename", low)


class Test003CookieSecureConditional(unittest.TestCase):
    """AUDIT-003：Secure 仅 HTTPS / 可信转发 https；纯 HTTP 可登录。"""

    def test_helper_http_false(self):
        from csrf_guard import cookie_secure_for_request

        self.assertFalse(
            cookie_secure_for_request(
                client_host="127.0.0.1",
                scheme="http",
                forwarded_proto=None,
            )
        )

    def test_helper_https_true(self):
        from csrf_guard import cookie_secure_for_request

        self.assertTrue(
            cookie_secure_for_request(
                client_host="10.0.0.5",
                scheme="https",
                forwarded_proto=None,
            )
        )

    def test_helper_loopback_forwarded_https(self):
        from csrf_guard import cookie_secure_for_request

        self.assertTrue(
            cookie_secure_for_request(
                client_host="127.0.0.1",
                scheme="http",
                forwarded_proto="https",
            )
        )

    def test_helper_external_forged_forwarded_https_ignored(self):
        from csrf_guard import cookie_secure_for_request

        self.assertFalse(
            cookie_secure_for_request(
                client_host="203.0.113.1",
                scheme="http",
                forwarded_proto="https",
            )
        )

    def test_login_http_sets_cookie_without_secure(self):
        from fastapi.testclient import TestClient
        import server

        tmp = Path(tempfile.mkdtemp(prefix="t3714_ck_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy2(ROOT / "config.json", tmp / "config.json")
        (tmp / "数据").mkdir()
        cfg = loaders.load_config(tmp)
        accounts.seed_defaults(cfg, tmp)
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        r = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        # httpx/starlette: set-cookie header
        sc = r.headers.get("set-cookie") or ""
        self.assertIn(server.SID_COOKIE, sc)
        self.assertNotIn("Secure", sc)
        # 会话可用
        sid = r.cookies.get(server.SID_COOKIE)
        self.assertTrue(sid)
        sess = client.get("/api/v1/session", headers={"Cookie": f"{server.SID_COOKIE}={sid}"})
        self.assertEqual(sess.status_code, 200, sess.text)

    def test_login_with_forwarded_https_sets_secure(self):
        from fastapi.testclient import TestClient
        import server

        tmp = Path(tempfile.mkdtemp(prefix="t3714_cks_"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy2(ROOT / "config.json", tmp / "config.json")
        (tmp / "数据").mkdir()
        cfg = loaders.load_config(tmp)
        accounts.seed_defaults(cfg, tmp)
        app = server.create_app(cfg, root=tmp)
        client = TestClient(app, follow_redirects=False)
        r = client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": accounts.DEFAULT_ADMIN_PW},
            headers={"X-Forwarded-Proto": "https"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sc = r.headers.get("set-cookie") or ""
        self.assertIn("Secure", sc)


class TestH20CaliberCopy(unittest.TestCase):
    """H20：费用区文案区分饼/分摊 vs 明细业务BU 原始行（后端 caliber_note）。"""

    def test_period_expense_note_mentions_raw_bu_or_chart_distinction(self):
        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        # 实现后应含明细「业务BU」原始行或等价口径区分（非仅「与上方图表口径一致」）
        self.assertTrue(
            ("业务BU" in src and "原始" in src)
            or ("分摊" in src and "明细" in src and "业务BU" in src),
            "cockpit caliber_note 须区分图表/分摊与明细原始行",
        )


if __name__ == "__main__":
    unittest.main()
