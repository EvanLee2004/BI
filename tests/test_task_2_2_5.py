#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.5 门禁：管理端翻页 / 看→展示 / logo+版本（结构源码守卫，驱动 shipped 路径）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ADMIN_LIST_VIEWS = [
    "LedgerView.vue",
    "OrderDeptView.vue",
    "UnclassifiedView.vue",
    "HistoryView.vue",
    "AuditView.vue",
    "ExceptionOverview.vue",
    "DetailView.vue",
]


class TestAdminPagination225(unittest.TestCase):
    def test_list_views_have_pager(self):
        for name in ADMIN_LIST_VIEWS:
            src = (ROOT / "frontend/src/admin/views" / name).read_text(encoding="utf-8")
            has_prev = "上一页" in src
            has_page = "page" in src or "pageRows" in src
            has_size = "pageSize" in src or "page_size=50" in src or "useClientPager" in src
            self.assertTrue(has_prev, f"{name}: 缺「上一页」")
            self.assertTrue(has_page and has_size, f"{name}: 缺 page/pageSize 翻页结构")

    def test_use_client_pager_page_size_50(self):
        src = (ROOT / "frontend/src/admin/composables/useClientPager.ts").read_text(encoding="utf-8")
        self.assertIn("ADMIN_PAGE_SIZE = 50", src)
        self.assertIn("上一页", (ROOT / "frontend/src/admin/views/LedgerView.vue").read_text(encoding="utf-8"))


class TestSeeToDisplay225(unittest.TestCase):
    def test_admin_tab_display_keeps_see_key(self):
        layout = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn(">展示<", layout)
        self.assertIn("showGroup('see')", layout)
        self.assertIn("group === 'see'", layout)
        # 页签不再显示单独一个「看」字
        self.assertNotIn(">看<", layout)

    def test_router_group_see_unchanged(self):
        router = (ROOT / "frontend/src/admin/router.ts").read_text(encoding="utf-8")
        self.assertIn("group: 'see'", router)


class TestLogoVersion225(unittest.TestCase):
    def test_public_logo_exists(self):
        p = ROOT / "frontend/public/logo.png"
        self.assertTrue(p.is_file(), "frontend/public/logo.png 缺失")
        self.assertGreater(p.stat().st_size, 1000)

    def test_app_and_bu_have_logo_and_version_api(self):
        for rel in ("frontend/src/App.vue", "frontend/src/components/BUPage.vue"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("/logo.png", src, rel)
            self.assertIn("fetchProductVersion", src, rel)
            self.assertIn("tb-logo", src, rel)

    def test_client_fetches_api_version(self):
        src = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
        self.assertIn("/api/version", src)
        self.assertIn("fetchProductVersion", src)

    def test_api_version_allows_viewer_session(self):
        """shipped：config_api /api/version 不再仅限管理员。"""
        src = (ROOT / "src/routes/config_api.py").read_text(encoding="utf-8")
        self.assertIn("_vacct(request)", src)
        self.assertIn("def api_version", src)


class TestVersionBump225(unittest.TestCase):
    def test_version_files(self):
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "2.2.5")
        self.assertIn("2.2.5", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.5]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
