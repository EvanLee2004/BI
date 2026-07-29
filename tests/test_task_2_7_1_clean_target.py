# -*- coding: utf-8 -*-
"""2.7.1 干净目标态：旧 cookie 401、旧业务 GET 404、v1 200、无 legacy 模式。"""
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

# 抽样：旧路径须 404；对应 v1 须存在（鉴权后可能 401/200）
OLD_TO_V1 = [
    ("/api/profit_ranking", "/api/v1/rankings/profit"),
    ("/api/detail", "/api/v1/admin/detail"),
    ("/api/detail/values", "/api/v1/admin/detail/values"),
    ("/api/detail_export", "/api/v1/admin/detail/export"),
    ("/api/daily", "/api/v1/daily"),
    ("/api/bu_daily", "/api/v1/bu_daily"),
    ("/api/exceptions", "/api/v1/admin/exceptions"),
    ("/api/order_depts", "/api/v1/admin/order_depts"),
    ("/api/history", "/api/v1/history"),
    ("/api/version", "/api/v1/version"),
    ("/api/bu_config", "/api/v1/admin/bu_config"),
    ("/api/sales_pool", "/api/v1/admin/sales_pool"),
    ("/api/config_changes", "/api/v1/admin/config_changes"),
    ("/api/settings", "/api/v1/admin/settings"),
    ("/api/adjustments", "/api/v1/admin/adjustments"),
    ("/api/manual_items", "/api/v1/admin/manual_items"),
    ("/api/manual", "/api/v1/admin/manual"),
    ("/api/budget", "/api/v1/admin/budget"),
    ("/api/alloc_ratios", "/api/v1/admin/alloc_rates"),
    ("/api/detax_rates", "/api/v1/admin/detax_rates"),
    ("/api/adjust_fields", "/api/v1/admin/adjust_fields"),
    ("/api/accounts", "/api/v1/admin/accounts"),
    ("/api/export.html", "/api/v1/export.html"),
    ("/api/export/pl.xlsx", "/api/v1/export/pl.xlsx"),
    # 2.7.2 写路径收官后旧路径亦 404
    ("/api/health", "/api/v1/health"),
    ("/api/refresh_status", "/api/v1/admin/refresh_status"),
]


class TestFrontendNoLegacyMode(unittest.TestCase):
    def test_frontend_mode_always_vue(self):
        import viewmodels

        self.assertEqual(viewmodels.frontend_mode({"frontend": "legacy"}), "vue")
        self.assertEqual(viewmodels.frontend_mode(None), "vue")

    def test_no_mode_legacy_branch_in_vm(self):
        src = (ROOT / "src/viewmodels/__init__.py").read_text(encoding="utf-8")
        self.assertNotIn('mode == "legacy"', src)
        self.assertNotIn("build_cockpit_views", src)


class TestOldGet404V1Present(unittest.TestCase):
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
            ],
        )
        server._state["fragments"] = fake_main_frags("M")
        server._state["views"] = fake_views("M")
        server._state["bu_pages"] = {"BU甲": fake_bu_page("BU甲", "A")}
        server._state["admin_html"] = "x"
        server._state["has_data"] = True
        server._state["summary"] = {
            "meta": {"year_key": "2026年"},
            "periods": {"2026年": {}},
        }
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls.server = server

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_old_paths_404_v1_not_404(self):
        c = self._client()
        c.post("/api/v1/login", json={"account": "lushasha", "password": self.server.DEFAULT_PW})
        for old, new in OLD_TO_V1:
            r_old = c.get(old)
            self.assertEqual(
                r_old.status_code,
                404,
                f"old {old} should 404 got {r_old.status_code}: {r_old.text[:120]}",
            )
            r_new = c.get(new)
            self.assertNotEqual(
                r_new.status_code,
                404,
                f"v1 {new} should exist got {r_new.status_code}: {r_new.text[:160]}",
            )

    def test_health_exceptions_remain(self):
        c = self._client()
        self.assertEqual(c.get("/api/v1/health").status_code, 200)
        # refresh_status may 200 even without login
        self.assertIn(c.get("/api/v1/admin/refresh_status").status_code, (200, 401, 403))


class TestFrontendSrcNoOldReads(unittest.TestCase):
    """frontend/src 不得再硬编码已删业务 GET。"""

    FORBIDDEN = [
        "/api/profit_ranking",
        '"/api/detail"',
        "`/api/detail",
        "/api/detail?",
        "/api/detail/",
        "/api/detail_export",
        '"/api/daily"',
        "/api/daily?",
        "/api/bu_daily",
        '"/api/history"',
        "/api/history/",
        '"/api/exceptions"',
        '"/api/order_depts"',
        '"/api/version"',
        '"/api/bu_config"',
        '"/api/sales_pool"',
        '"/api/config_changes"',
        '"/api/settings"',
        '"/api/adjustments"',
        '"/api/manual"',
        '"/api/manual_items"',
        '"/api/budget"',
        "/api/alloc_ratios",
        '"/api/detax_rates"',
        '"/api/adjust_fields"',
        '"/api/accounts"',
        "/api/export.html",
        "/api/export/pl.xlsx",
        "'/api/health'",
        "'/api/refresh'",
        "'/api/my_passwd'",
        "'/api/adjust'",
    ]

    def test_src_clean(self):
        hits = []
        for p in (ROOT / "frontend/src").rglob("*"):
            if p.suffix not in {".ts", ".vue", ".js"}:
                continue
            text = p.read_text(encoding="utf-8")
            for needle in self.FORBIDDEN:
                if needle in text:
                    hits.append(f"{p.relative_to(ROOT)}: {needle}")
        self.assertEqual(hits, [], "frontend still calls deleted paths:\n" + "\n".join(hits))


class TestVersion271(unittest.TestCase):
    def test_version_file(self):
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        # 2.7.1 起；后续 2.8.x 等小版本递增仍通过（G5+）
        parts = ver.split(".")
        major = int(parts[0]) if parts and parts[0].isdigit() else 0
        minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        self.assertTrue(major > 2 or (major == 2 and minor >= 7), ver)


if __name__ == "__main__":
    unittest.main(verbosity=2)
