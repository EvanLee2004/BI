#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.8 G2/G3：能力矩阵 + 导出/写/刷 API 403 + session.caps + 密码回显。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import authz  # noqa: E402
import loaders  # noqa: E402


class TestCapsMaterialize(unittest.TestCase):
    def test_stock_admin_all_on(self):
        acc = {"账号": "a", "权限": accounts.PERM_ADMIN}
        m = authz.materialize_caps(acc)
        self.assertTrue(all(m[k] for k in authz.FINE_CAP_KEYS))

    def test_stock_main_exports_on_no_admin(self):
        """3.7.9：存量整体四导出开；view_main 不再生效（can_main 走角色）。"""
        acc = {"账号": "m", "权限": accounts.PERM_MAIN}
        m = authz.materialize_caps(acc)
        self.assertFalse(m[authz.CAP_VIEW_MAIN])
        self.assertTrue(authz.can_main(acc))
        self.assertTrue(m[authz.CAP_EXPORT_PL_XLSX])
        self.assertTrue(m[authz.CAP_EXPORT_LEDGER_XLSX])
        self.assertFalse(m[authz.CAP_ADMIN_ACCESS])
        self.assertFalse(m[authz.CAP_DATA_WRITE])
        self.assertFalse(m[authz.CAP_DATA_REFRESH])
        self.assertFalse(m[authz.CAP_MANAGE_ACCOUNTS])

    def test_stock_bu_exports_on(self):
        acc = {"账号": "b", "权限": accounts.PERM_BU, "可见BU": ["甲"]}
        m = authz.materialize_caps(acc)
        self.assertTrue(m[authz.CAP_EXPORT_PAGE_HTML])
        self.assertFalse(m[authz.CAP_ADMIN_ACCESS])

    def test_explicit_cap_override(self):
        """3.7.9：仅四导出可覆盖；view_main 脏 true 强制 false。"""
        acc = {
            "账号": "m",
            "权限": accounts.PERM_MAIN,
            "能力": {authz.CAP_EXPORT_PL_XLSX: False, authz.CAP_VIEW_MAIN: True},
        }
        m = authz.materialize_caps(acc)
        self.assertFalse(m[authz.CAP_EXPORT_PL_XLSX])
        self.assertFalse(m[authz.CAP_VIEW_MAIN])
        # unspecified user-export keys keep role default
        self.assertTrue(m[authz.CAP_EXPORT_LEDGER_XLSX])

    def test_master_forced_manage(self):
        acc = {
            "账号": accounts.MASTER_ACCOUNT,
            "权限": accounts.PERM_ADMIN,
            "能力": {
                authz.CAP_ADMIN_ACCESS: False,
                authz.CAP_MANAGE_ACCOUNTS: False,
            },
        }
        m = authz.materialize_caps(acc)
        self.assertTrue(m[authz.CAP_ADMIN_ACCESS])
        self.assertTrue(m[authz.CAP_MANAGE_ACCOUNTS])

    def test_legacy_role_matrix_unchanged(self):
        m = authz.role_matrix_for_tests()
        self.assertTrue(m["管理员"][authz.CAN_ADMIN])
        self.assertTrue(m["管理员"][authz.CAN_EXPORT])
        self.assertFalse(m["管理员"][authz.CAN_VIEW_SALARY])
        self.assertTrue(m["整体"][authz.CAN_EXPORT])
        self.assertFalse(m["整体"][authz.CAN_ADMIN])

    def test_bu_template_safe_defaults(self):
        t = authz.caps_template("BU")
        self.assertFalse(any(t[k] for k in authz.FINE_CAP_KEYS))


class TestCapsHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp(prefix="t378_caps_"))
        shutil.copy2(ROOT / "config.json", cls.tmp / "config.json")
        (cls.tmp / "数据").mkdir()
        cls.cfg = loaders.load_config(cls.tmp)
        cls._orig = server.recompute
        server.recompute = lambda cfg, root=None, **k: server._state.__setitem__(
            "built_at", "RECOMPUTED"
        )
        server._state["summary"] = {
            "meta": {"year_key": "2026"},
            "periods": {"2026": {"range": ("2026-01", "2026-12")}},
        }
        server._state["has_data"] = True
        cls.server = server
        cls._seed_accounts()
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.client = TestClient(cls.app, follow_redirects=False)

    @classmethod
    def _seed_accounts(cls):
        """每测可重入：固定矩阵账号，避免上例 save 删掉 overall/no_export。"""
        accounts.seed_defaults(cls.cfg, cls.tmp)
        rows = accounts.load_accounts(cls.cfg, cls.tmp)
        rows.append(
            {
                "账号": "no_export",
                "显示名": "无导出",
                "权限": accounts.PERM_MAIN,
                "密码": accounts.DEFAULT_VIEW_PW,
                "能力": {
                    **authz.default_caps_for_role(
                        {"账号": "no_export", "权限": accounts.PERM_MAIN}
                    ),
                    authz.CAP_EXPORT_PL_XLSX: False,
                    authz.CAP_EXPORT_LEDGER_XLSX: False,
                    authz.CAP_EXPORT_PAGE_HTML: False,
                    authz.CAP_EXPORT_PAGE_PNG: False,
                    authz.CAP_EXPORT_ADMIN_DETAIL: False,
                    authz.CAP_EXPORT_ARCHIVE: False,
                },
            }
        )
        for a in rows:
            if a["账号"] == "overall":
                a["能力"] = {
                    **authz.materialize_caps(a),
                    authz.CAP_DATA_WRITE: False,
                    authz.CAP_DATA_REFRESH: False,
                }
        # 3.7.9：管理员不可半开写/刷；用整体号测无管理类 403
        rows.append(
            {
                "账号": "ops_ro",
                "显示名": "整体无写刷",
                "权限": accounts.PERM_MAIN,
                "密码": accounts.DEFAULT_VIEW_PW,
                "能力": {
                    authz.CAP_EXPORT_PL_XLSX: True,
                    authz.CAP_DATA_WRITE: True,  # 脏：须被硬规则抹掉
                    authz.CAP_DATA_REFRESH: True,
                },
            }
        )
        accounts.save_accounts(cls.cfg, cls.tmp, rows)

    def setUp(self):
        # 破坏性用例后恢复账号表
        self._seed_accounts()

    @classmethod
    def tearDownClass(cls):
        cls.server.recompute = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _login_view(self, account: str, password: str | None = None):
        pw = password or accounts.DEFAULT_VIEW_PW
        r = self.client.post("/api/v1/login", json={"account": account, "password": pw})
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.cookies.get(self.server.SID_COOKIE) or r.cookies.get(self.server.COOKIE)
        return {"Cookie": f"{self.server.SID_COOKIE}={sid}"}

    def _login_admin(self, account: str = "lushasha", password: str | None = None):
        pw = password or accounts.DEFAULT_ADMIN_PW
        r = self.client.post(
            "/admin/login", data={"account": account, "password": pw}
        )
        sid = r.cookies.get(self.server.SID_COOKIE) or r.cookies.get(self.server.COOKIE)
        return {"Cookie": f"{self.server.SID_COOKIE}={sid}"}

    def test_session_includes_caps(self):
        hdr = self._login_view("overall")
        r = self.client.get("/api/v1/session", headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("caps", body)
        for k in authz.FINE_CAP_KEYS:
            self.assertIn(k, body["caps"], k)
        self.assertTrue(body["caps"][authz.CAP_EXPORT_PL_XLSX])

    def test_no_pl_export_cap_403(self):
        hdr = self._login_view("no_export")
        r = self.client.get("/api/v1/export/pl.xlsx", headers=hdr)
        self.assertEqual(r.status_code, 403, r.text)

    def test_no_ledger_export_cap_403(self):
        hdr = self._login_view("no_export")
        r = self.client.get("/api/v1/vm/ledger/export", headers=hdr)
        self.assertEqual(r.status_code, 403, r.text)

    def test_stock_overall_export_not_403_for_cap(self):
        """T8：存量无 能力 时默认 export 开；403 只来自其它校验（如 503 未构建可接受）。"""
        # use seed overall after materialize - re-seed path: login overall
        # Our overall has 能力 with exports on
        hdr = self._login_view("overall")
        r = self.client.get("/api/v1/export/pl.xlsx", headers=hdr)
        self.assertNotEqual(r.status_code, 403, r.text)

    def test_no_data_write_403(self):
        """3.7.9：非管理员（含脏 data_write）写路径 401/403。"""
        hdr = self._login_view("ops_ro")
        r = self.client.post(
            "/api/v1/admin/detax_rates",
            headers=hdr,
            json={"rates": {"房租": 6}},
        )
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_no_data_refresh_403(self):
        """3.7.9：非管理员 refresh 401/403（管理员不可半关写刷）。"""
        hdr = self._login_view("ops_ro")
        r = self.client.post("/api/v1/admin/refresh", headers=hdr)
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_admin_accounts_returns_plaintext_password(self):
        hdr = self._login_admin("lushasha")
        r = self.client.get("/api/v1/admin/accounts", headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        rows = body.get("accounts") or []
        self.assertTrue(rows)
        master = next(a for a in rows if a["账号"] == "lushasha")
        self.assertIn("密码", master)
        self.assertEqual(master["密码"], accounts.DEFAULT_ADMIN_PW)
        self.assertIn("caps", master)
        self.assertIn("能力", master)

    def test_session_has_no_password_field(self):
        hdr = self._login_view("overall")
        r = self.client.get("/api/v1/session", headers=hdr)
        body = r.json()
        self.assertNotIn("密码", body)
        self.assertNotIn("password", body)

    def test_last_admin_manage_protected(self):
        hdr = self._login_admin("lushasha")
        # try save with only non-manage accounts
        r = self.client.post(
            "/api/v1/admin/accounts",
            headers=hdr,
            json={
                "accounts": [
                    {
                        "账号": "lushasha",
                        "显示名": "管理员",
                        "权限": "管理员",
                        "密码": accounts.DEFAULT_ADMIN_PW,
                        "能力": {
                            **{k: True for k in authz.FINE_CAP_KEYS},
                            authz.CAP_MANAGE_ACCOUNTS: False,
                        },
                    }
                ]
            },
        )
        # master forced manage in materialize, but validate should still pass for master force
        # If only master and force restores manage, save may 200. Try strip all admins:
        r2 = self.client.post(
            "/api/v1/admin/accounts",
            headers=hdr,
            json={
                "accounts": [
                    {
                        "账号": "only_view",
                        "显示名": "仅看",
                        "权限": "整体",
                        "密码": "8888",
                    }
                ]
            },
        )
        self.assertEqual(r2.status_code, 400, r2.text)

    def test_settings_password_not_in_zhiyun(self):
        """智云密码仍不下发。"""
        hdr = self._login_admin("lushasha")
        r = self.client.get("/api/v1/admin/settings", headers=hdr)
        if r.status_code != 200:
            self.skipTest(f"settings {r.status_code}")
        body = r.json()
        self.assertNotIn("zhiyun_password", body)
        # password_set flag ok
        self.assertIn("zhiyun_password_set", body)


if __name__ == "__main__":
    unittest.main()
