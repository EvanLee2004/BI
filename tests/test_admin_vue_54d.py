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
            "views/LoginView.vue",
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
            "手填": ("/api/manual", "manual_batch"),
            "分摊": ("/api/alloc_rates",),
            "去税": ("/api/detax_rates",),
            "预算": ("/api/budget", "budget_batch"),
            "明细调整": ("/api/detail", "/api/adjust"),
            "账号": ("/api/accounts",),
            "BU": ("/api/bu_config", "sales_pool"),
            "设置": ("/api/settings",),
            "审计": ("/api/config_changes",),
            "历史": ("/api/history",),
            "异常": ("/api/exceptions",),
            "版本": ("/api/version", "/api/update/check"),
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
        r = self._client().get("/admin")
        self.assertEqual(r.status_code, 200)
        # Vue dist index 或仍带登录文案
        body = r.text
        self.assertTrue(
            "/app/assets/" in body or "管理员端登录" in body or 'id="app"' in body,
            "expected Vue SPA shell or login",
        )

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
        r = c.get("/api/manual_items")
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
            "/api/settings",
            "/api/accounts",
            "/api/bu_config",
            "/api/version",
            "/api/health",
            "/api/exceptions",
            "/api/adjust_fields",
            "/api/config_changes",
        ):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)

    def test_logout_still_registered(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": self.DEFAULT_PW})
        r = c.get("/admin/logout")
        self.assertIn(r.status_code, (303, 302))
        self.assertEqual(r.headers.get("location"), "/admin")

    def test_legacy_mode_static_admin(self):
        """KANBAN_FRONTEND=legacy 时登录后仍走 static 骨架。"""
        import accounts
        import loaders
        import server

        os.environ["KANBAN_FRONTEND"] = "legacy"
        try:
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
            self.assertIn("管理员控制台", r.text)
            self.assertIn("/admin/app.js", r.text)
        finally:
            os.environ["KANBAN_FRONTEND"] = "vue"


if __name__ == "__main__":
    unittest.main()
