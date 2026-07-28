#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54.4 批次 D：管理端 Vue SPA 结构 + 写路径 API 冒烟。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FE_ADMIN = ROOT / "frontend" / "src" / "admin"
FE_VIEWS = FE_ADMIN / "views"


class TestAdminVueStructure(unittest.TestCase):
    """Vue 管理端文件与能力覆盖（对表 static/admin 能力）。"""

    def test_core_files_exist(self):
        for rel in (
            "bootstrap.ts",
            "AdminApp.vue",
            "router.ts",
            "api.ts",
            "utils.ts",
            "layout/AdminLayout.vue",
            # 2.5.0：无独立管理员登录页（统一 /login）
            "views/ConsoleView.vue",
            "views/DetailView.vue",
            "views/ManualView.vue",
            "views/BudgetView.vue",
            "views/ExceptionOverview.vue",
            "views/LedgerView.vue",
            "views/OrderDeptView.vue",
            "views/UnclassifiedView.vue",
            "views/HistoryView.vue",
            "views/AuditView.vue",
            "views/SettingsView.vue",
        ):
            p = FE_ADMIN / rel
            self.assertTrue(p.is_file(), f"missing {p}")

    def test_capability_markers_in_views(self):
        """能力对表：每项能力至少在某个 view/api 中出现端点或语义锚点。"""
        blob = ""
        for p in FE_ADMIN.rglob("*"):
            if p.suffix in (".vue", ".ts"):
                blob += p.read_text(encoding="utf-8") + "\n"
        markers = {
            "控制台 iframe": ('src="/"', "ConsoleView"),
            "更新数据": ("/api/refresh", "doRefresh"),
            "手填": ("/api/v1/admin/manual", "manual_batch"),
            "分摊": ("/api/v1/admin/alloc_rates", "/api/alloc_rates"),  # 61·G：前端已对齐 ratios
            "去税": ("/api/v1/admin/detax_rates",),
            "预算": ("/api/v1/admin/budget", "budget_batch"),
            "明细调整": ("/api/v1/admin/detail", "/api/adjust"),
            "账号": ("/api/v1/admin/accounts",),
            "BU": ("/api/v1/admin/bu_config", "sales_pool"),
            "设置": ("/api/v1/admin/settings",),
            "审计": ("/api/v1/admin/config_changes",),
            "历史": ("/api/v1/history",),
            "异常": ("/api/v1/admin/exceptions",),
            "版本": ("/api/v1/version", "/api/v1/update/check"),
            "登录": ("/api/v1/login", "adminLogin"),
            "无 v-html 不可信": (),  # 下面单独断言
        }
        for name, toks in markers.items():
            if name.startswith("无"):
                continue
            ok = any(t in blob for t in toks)
            self.assertTrue(ok, f"capability {name} missing any of {toks}")
        # 禁止 v-html（管理端）
        for p in FE_ADMIN.rglob("*.vue"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("v-html", text, f"v-html forbidden in {p}")

    def test_main_ts_admin_branch(self):
        main = (ROOT / "frontend" / "src" / "main.ts").read_text(encoding="utf-8")
        self.assertIn("/admin", main)
        self.assertIn("admin/bootstrap", main)
        self.assertIn("boot-cockpit", main)

    def test_element_plus_in_package(self):
        pkg = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        self.assertIn("element-plus", pkg)
        self.assertIn("vue-router", pkg)


class TestAdminVueHttp(unittest.TestCase):
    """vue 模式下 /admin 吐 dist；写路径 API 仍可用。"""

    @classmethod
    def setUpClass(cls):
        import accounts
        import loaders
        import server

        cls.tmp = Path(tempfile.mkdtemp())
        cls.cfg = loaders.load_config(ROOT)
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW},
            ],
        )
        server._state["admin_html"] = server._admin_page("", {}, cls.cfg)
        server._state["user_html"] = "<html>u</html>"
        server._state["summary"] = {"meta": {}, "periods": {}}
        # 强制 vue（有 dist 时）
        os.environ["KANBAN_FRONTEND"] = "vue"
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server
        cls.DEFAULT_PW = server.DEFAULT_PW

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("KANBAN_FRONTEND", None)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_unauth_admin_serves_spa_or_login(self):
        # 2.5.0：未登录 /admin → 303 统一 /login
        r = self._client().get("/admin")
        self.assertEqual(r.status_code, 303)
        loc = r.headers.get("location") or ""
        self.assertTrue(loc.startswith("/login"), loc)

    def test_login_form_post_still_works(self):
        c = self._client()
        r = c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        self.assertIn(r.status_code, (303, 302))
        self.assertEqual(r.headers.get("location"), "/admin")
        # cookie 已下发
        self.assertTrue(c.cookies.get("kanban_session") or any("kanban" in k for k in c.cookies.keys()) or r.headers.get("set-cookie"))

    def test_logged_in_admin_spa(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        r = c.get("/admin")
        self.assertEqual(r.status_code, 200)
        # vue → dist index（含 /app/assets）；若 dist 缺失会 503 文本
        if r.status_code == 200:
            self.assertTrue(
                "/app/assets/" in r.text or "Vue frontend not built" in r.text or "管理员控制台" in r.text,
                r.text[:200],
            )

    def test_admin_deep_path_spa(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        r = c.get("/admin/settings")
        self.assertEqual(r.status_code, 200)

    def test_manual_items_api(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        r = c.get("/api/v1/admin/manual_items")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        # 与 config 手填项一致（至少有一项）
        self.assertTrue(len(data["items"]) >= 1)

    def test_write_path_settings_get(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        for path in (
            "/api/v1/admin/settings",
            "/api/v1/admin/accounts",
            "/api/v1/admin/bu_config",
            "/api/v1/version",
            "/api/health",
            "/api/v1/admin/exceptions",
            "/api/v1/admin/adjust_fields",
            "/api/v1/admin/config_changes",
        ):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)

    def test_logout_still_registered(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        r = c.get("/admin/logout")
        self.assertIn(r.status_code, (303, 302))
        # 2.5.0：退出到统一登录
        self.assertEqual(r.headers.get("location"), "/login")

    def test_admin_always_vue_spa(self):
        """2.7.1：管理端仅 Vue SPA（legacy 模式已删）。"""
        import accounts
        import loaders
        import server

        tmp = Path(tempfile.mkdtemp())
        cfg = loaders.load_config(ROOT)
        accounts.save_accounts(
            cfg,
            tmp,
            [{"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW}],
        )
        server._state["admin_html"] = "ready"
        app = server.create_app(cfg, root=tmp)
        from fastapi.testclient import TestClient

        c = TestClient(app, follow_redirects=False)
        c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        r = c.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            'id="app"' in r.text or "管理员" in r.text or "/app/" in r.text,
            "admin should serve vue spa shell",
        )


if __name__ == "__main__":
    unittest.main()
