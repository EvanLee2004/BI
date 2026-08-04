#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.9/3.7.10：能力矩阵收敛硬规则（TDD）。

产品 SSOT：权限看范围；用户能力仅看端导出；管理类绑管理员；
非管理员脏 admin_access 等强制 false；can_main 仅角色。
3.7.10：设置页展示三项内容向标签（全部视图/管理利润表/收单台账明细）。
"""
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

# 管理类 + 管端导出/归档（非管理员恒 false）
_ADMIN_BOUND = (
    authz.CAP_ADMIN_ACCESS,
    authz.CAP_DATA_REFRESH,
    authz.CAP_DATA_WRITE,
    authz.CAP_MANAGE_ACCOUNTS,
    authz.CAP_EXPORT_ADMIN_DETAIL,
    authz.CAP_EXPORT_ARCHIVE,
    authz.CAP_VIEW_MAIN,
)

_USER_EXPORTS = (
    authz.CAP_EXPORT_PAGE_HTML,
    authz.CAP_EXPORT_PAGE_PNG,
    authz.CAP_EXPORT_PL_XLSX,
    authz.CAP_EXPORT_LEDGER_XLSX,
)


class TestMaterializeHardRules379(unittest.TestCase):
    """G1 红测：materialize / can_main / is_admin 硬规则。"""

    def test_dirty_admin_access_non_admin_forced_false(self):
        """T8：BU/整体 JSON 脏 admin_access=true → 生效 false。"""
        for role, extra in (
            (accounts.PERM_MAIN, {}),
            (accounts.PERM_BU, {"可见BU": ["甲"]}),
        ):
            acc = {
                "账号": "dirty",
                "权限": role,
                "能力": {
                    authz.CAP_ADMIN_ACCESS: True,
                    authz.CAP_DATA_REFRESH: True,
                    authz.CAP_DATA_WRITE: True,
                    authz.CAP_MANAGE_ACCOUNTS: True,
                    authz.CAP_EXPORT_ADMIN_DETAIL: True,
                    authz.CAP_EXPORT_ARCHIVE: True,
                    authz.CAP_VIEW_MAIN: True,
                    authz.CAP_EXPORT_PL_XLSX: True,
                },
                **extra,
            }
            m = authz.materialize_caps(acc)
            for k in _ADMIN_BOUND:
                self.assertFalse(m[k], f"{role}/{k} must be false")
            self.assertTrue(m[authz.CAP_EXPORT_PL_XLSX])
            self.assertFalse(authz.is_admin(acc), f"{role} is_admin must be false")

    def test_admin_all_caps_true(self):
        acc = {"账号": "a", "权限": accounts.PERM_ADMIN}
        m = authz.materialize_caps(acc)
        self.assertTrue(all(m[k] for k in authz.FINE_CAP_KEYS))
        self.assertTrue(authz.is_admin(acc))

    def test_admin_cannot_downgrade_via_json(self):
        """管理员 JSON 试图关管理类 → 仍全 true。"""
        acc = {
            "账号": "a",
            "权限": accounts.PERM_ADMIN,
            "能力": {k: False for k in authz.FINE_CAP_KEYS},
        }
        m = authz.materialize_caps(acc)
        self.assertTrue(all(m[k] for k in authz.FINE_CAP_KEYS))

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

    def test_can_main_role_only(self):
        """can_main := is_admin OR is_main；脏 view_main / 旧 可看整体页 不放行 BU。"""
        admin = {"账号": "a", "权限": accounts.PERM_ADMIN}
        main = {"账号": "m", "权限": accounts.PERM_MAIN}
        bu = {"账号": "b", "权限": accounts.PERM_BU, "可见BU": ["甲"]}
        bu_dirty = {
            "账号": "b2",
            "权限": accounts.PERM_BU,
            "可见BU": ["甲"],
            "能力": {authz.CAP_VIEW_MAIN: True},
            "可看整体页": True,
        }
        self.assertTrue(authz.can_main(admin))
        self.assertTrue(authz.can_main(main))
        self.assertFalse(authz.can_main(bu))
        self.assertFalse(authz.can_main(bu_dirty))
        # materialize view_main for non-admin always false
        self.assertFalse(authz.materialize_caps(bu_dirty)[authz.CAP_VIEW_MAIN])
        self.assertFalse(authz.materialize_caps(main)[authz.CAP_VIEW_MAIN])

    def test_four_exports_independent_for_non_admin(self):
        acc = {
            "账号": "m",
            "权限": accounts.PERM_MAIN,
            "能力": {
                authz.CAP_EXPORT_PAGE_HTML: True,
                authz.CAP_EXPORT_PAGE_PNG: False,
                authz.CAP_EXPORT_PL_XLSX: True,
                authz.CAP_EXPORT_LEDGER_XLSX: False,
            },
        }
        m = authz.materialize_caps(acc)
        self.assertTrue(m[authz.CAP_EXPORT_PAGE_HTML])
        self.assertFalse(m[authz.CAP_EXPORT_PAGE_PNG])
        self.assertTrue(m[authz.CAP_EXPORT_PL_XLSX])
        self.assertFalse(m[authz.CAP_EXPORT_LEDGER_XLSX])

    def test_export_archive_admin_detail_non_admin_false(self):
        acc = {
            "账号": "m",
            "权限": accounts.PERM_MAIN,
            "能力": {
                authz.CAP_EXPORT_ARCHIVE: True,
                authz.CAP_EXPORT_ADMIN_DETAIL: True,
                authz.CAP_EXPORT_PL_XLSX: True,
            },
        }
        m = authz.materialize_caps(acc)
        self.assertFalse(m[authz.CAP_EXPORT_ARCHIVE])
        self.assertFalse(m[authz.CAP_EXPORT_ADMIN_DETAIL])

    def test_stock_main_four_exports_on_no_admin(self):
        """存量整体无 能力：四导出开；管理类关。"""
        acc = {"账号": "m", "权限": accounts.PERM_MAIN}
        m = authz.materialize_caps(acc)
        for k in _USER_EXPORTS:
            self.assertTrue(m[k], k)
        for k in _ADMIN_BOUND:
            self.assertFalse(m[k], k)

    def test_template_main_four_on_bu_four_off(self):
        t_main = authz.caps_template("整体")
        t_bu = authz.caps_template("BU")
        for k in _USER_EXPORTS:
            self.assertTrue(t_main[k], k)
            self.assertFalse(t_bu[k], k)
        for k in _ADMIN_BOUND:
            self.assertFalse(t_main[k], k)
            self.assertFalse(t_bu[k], k)
        t_admin = authz.caps_template("管理员")
        self.assertTrue(all(t_admin[k] for k in authz.FINE_CAP_KEYS))

    def test_is_admin_role_only_not_dirty_cap(self):
        """禁止「非管理员角色 + 脏 admin_access」半管理。"""
        acc = {
            "账号": "x",
            "权限": accounts.PERM_MAIN,
            "能力": {authz.CAP_ADMIN_ACCESS: True},
        }
        self.assertFalse(authz.is_admin(acc))
        self.assertFalse(authz.has_fine_cap(acc, authz.CAP_ADMIN_ACCESS))


class TestCapsHttp379(unittest.TestCase):
    """API：无 cap 403；非管理员管理路径 403；管理员可达。"""

    @classmethod
    def setUpClass(cls):
        import server
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp(prefix="t379_caps_"))
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
                    authz.CAP_EXPORT_LEDGER_XLSX: False,
                    authz.CAP_EXPORT_PAGE_HTML: False,
                    authz.CAP_EXPORT_PAGE_PNG: False,
                },
            }
        )
        rows.append(
            {
                "账号": "bu_user",
                "显示名": "BU号",
                "权限": accounts.PERM_BU,
                "可见BU": ["甲"],
                "密码": accounts.DEFAULT_VIEW_PW,
                "能力": {
                    # 脏管理类 — 服务端必须忽略
                    authz.CAP_ADMIN_ACCESS: True,
                    authz.CAP_DATA_REFRESH: True,
                    authz.CAP_DATA_WRITE: True,
                    authz.CAP_MANAGE_ACCOUNTS: True,
                    authz.CAP_EXPORT_ARCHIVE: True,
                    authz.CAP_EXPORT_ADMIN_DETAIL: True,
                    authz.CAP_EXPORT_PL_XLSX: True,
                },
            }
        )
        accounts.save_accounts(cls.cfg, cls.tmp, rows)

    def setUp(self):
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

    def test_session_caps_non_admin_admin_bound_false(self):
        hdr = self._login_view("bu_user")
        r = self.client.get("/api/v1/session", headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        caps = r.json().get("caps") or {}
        for k in _ADMIN_BOUND:
            self.assertFalse(caps.get(k), k)
        self.assertFalse(r.json().get("is_admin"))
        self.assertFalse(r.json().get("can_main"))

    def test_no_pl_export_cap_403(self):
        hdr = self._login_view("no_export")
        r = self.client.get("/api/v1/export/pl.xlsx", headers=hdr)
        self.assertEqual(r.status_code, 403, r.text)

    def test_bu_refresh_403(self):
        """非管理员不得 refresh：401（非管理会话）或 403（无 cap）均可。"""
        hdr = self._login_view("bu_user")
        r = self.client.post("/api/v1/admin/refresh", headers=hdr)
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_bu_data_write_403(self):
        hdr = self._login_view("bu_user")
        r = self.client.post(
            "/api/v1/admin/detax_rates",
            headers=hdr,
            json={"rates": {"房租": 6}},
        )
        # 非管理员：401/403 均可（未进管理会话或无 cap）
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_bu_archive_export_403(self):
        hdr = self._login_view("bu_user")
        r = self.client.get("/api/v1/admin/archive_export?year=2026", headers=hdr)
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_admin_refresh_not_403_for_cap(self):
        """管理员 refresh 路径：不得因 cap 403（503/200/其它业务码可）。"""
        hdr = self._login_admin("lushasha")
        r = self.client.post("/api/v1/admin/refresh", headers=hdr)
        self.assertNotEqual(r.status_code, 403, r.text)

    def test_admin_accounts_plaintext_password(self):
        """3.7.8 密码回显不回退。"""
        hdr = self._login_admin("lushasha")
        r = self.client.get("/api/v1/admin/accounts", headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        rows = r.json().get("accounts") or []
        master = next(a for a in rows if a["账号"] == "lushasha")
        self.assertEqual(master["密码"], accounts.DEFAULT_ADMIN_PW)

    def test_save_cleans_dirty_admin_caps(self):
        """保存后物化干净：脏 admin_access 不生效且落盘/回显为 false。"""
        hdr = self._login_admin("lushasha")
        rows = accounts.load_accounts(self.cfg, self.tmp)
        payload = []
        for a in rows:
            row = {
                "账号": a["账号"],
                "显示名": a.get("显示名") or a["账号"],
                "权限": a["权限"],
                "密码": a.get("密码") or accounts.DEFAULT_VIEW_PW,
                "能力": dict(a.get("能力") or {}),
            }
            if a.get("可见BU"):
                row["可见BU"] = a["可见BU"]
            if a["账号"] == "bu_user":
                row["能力"] = {
                    authz.CAP_ADMIN_ACCESS: True,
                    authz.CAP_DATA_WRITE: True,
                    authz.CAP_EXPORT_PL_XLSX: True,
                }
            payload.append(row)
        r = self.client.post(
            "/api/v1/admin/accounts",
            headers=hdr,
            json={"accounts": payload},
        )
        self.assertEqual(r.status_code, 200, r.text)
        saved = next(a for a in r.json()["accounts"] if a["账号"] == "bu_user")
        caps = saved.get("能力") or saved.get("caps") or {}
        self.assertFalse(caps.get(authz.CAP_ADMIN_ACCESS))
        self.assertFalse(caps.get(authz.CAP_DATA_WRITE))
        self.assertTrue(caps.get(authz.CAP_EXPORT_PL_XLSX))
        # disk
        disk = accounts.load_accounts(self.cfg, self.tmp)
        bu = next(a for a in disk if a["账号"] == "bu_user")
        m = authz.materialize_caps(bu)
        self.assertFalse(m[authz.CAP_ADMIN_ACCESS])


class TestSettingsUiSource379(unittest.TestCase):
    """G3 静态：设置页源码符合 §2.6（无浏览器）。3.7.10 三内容能力。"""

    def test_cap_keys_only_three_content_exports(self):
        form = (ROOT / "frontend/src/admin/composables/useSettingsForm.ts").read_text(
            encoding="utf-8"
        )
        # CAP_KEYS 数组仅三项内容导出（无 export_page_png）
        self.assertIn("export_page_html", form)
        self.assertIn("export_pl_xlsx", form)
        self.assertIn("export_ledger_xlsx", form)
        import re

        m = re.search(r"export const CAP_KEYS = \[([^\]]+)\]", form)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn("export_page_png", body)
        for banned in (
            "view_main",
            "admin_access",
            "data_refresh",
            "data_write",
            "manage_accounts",
            "export_admin_detail",
            "export_archive",
            "export_page_png",
        ):
            self.assertNotIn(f"'{banned}'", body, banned)
        # 能力标签为内容向三词，禁止旧格式标签
        self.assertIn("全部视图", form)
        self.assertIn("管理利润表", form)
        self.assertIn("收单台账明细", form)
        for old_label in ("导出HTML", "导出PNG", "导出利润表", "导出明细"):
            self.assertNotIn(old_label, form, old_label)

    def test_settings_view_admin_fixed_and_subtitle(self):
        vue = (ROOT / "frontend/src/admin/views/SettingsView.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("管理员 · 全部权限", vue)
        self.assertIn("管理员固定全权", vue)
        # 3.7.10：三能力内容导向副标题
        self.assertIn("全部视图", vue)
        self.assertIn("管理利润表", vue)
        self.assertIn("收单台账明细", vue)
        self.assertNotIn("四导出", vue)
        # 无「看整体」能力勾文案；无旧四词能力标签
        self.assertNotIn("看整体", vue)
        self.assertNotIn("进管理端", vue)
        for old_label in ("导出HTML", "导出PNG", "导出利润表", "导出明细"):
            self.assertNotIn(old_label, vue, old_label)


if __name__ == "__main__":
    unittest.main()
