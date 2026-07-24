#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.5 门禁：管理端翻页 / 看→展示 / logo+版本（结构 + 构建产物真实 PNG）。"""
from __future__ import annotations

import re
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
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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
        self.assertNotIn(">看<", layout)

    def test_router_group_see_unchanged(self):
        router = (ROOT / "frontend/src/admin/router.ts").read_text(encoding="utf-8")
        self.assertIn("group: 'see'", router)


class TestLogoVersion225(unittest.TestCase):
    def test_source_logo_asset_and_import(self):
        """源码：logo 经 import 进 assets（经得住 base=/app/ + nginx /app/assets/）。"""
        asset = ROOT / "frontend/src/assets/logo.png"
        self.assertTrue(asset.is_file(), "frontend/src/assets/logo.png 缺失")
        self.assertGreater(asset.stat().st_size, 1000)
        self.assertEqual(asset.read_bytes()[:8], PNG_MAGIC)
        for rel in ("frontend/src/App.vue", "frontend/src/components/BUPage.vue"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("import logoUrl from", src, rel)
            self.assertIn("assets/logo.png", src, rel)
            self.assertIn(":src=\"logoUrl\"", src, rel)
            self.assertIn("fetchProductVersion", src, rel)
            self.assertIn("tb-logo", src, rel)
            # 禁止裸 /logo.png（会被写成 /app/logo.png，nginx 回 SPA html）
            self.assertNotIn('src="/logo.png"', src, rel)

    def test_built_dist_logo_url_is_real_png(self):
        """构建产物：boot-cockpit 引用的 /app/assets/*.png 必须是真实 PNG 文件。"""
        dist = ROOT / "frontend/dist"
        assets = dist / "assets"
        self.assertTrue(assets.is_dir(), "frontend/dist/assets 缺失（请先 npm run build）")
        boots = list(assets.glob("boot-cockpit-*.js"))
        self.assertTrue(boots, "缺 boot-cockpit-*.js")
        text = boots[0].read_text(encoding="utf-8", errors="replace")
        urls = re.findall(r'["\'](/app/assets/[^"\']+\.png)["\']', text)
        self.assertTrue(urls, f"{boots[0].name} 未引用 /app/assets/*.png")
        found = False
        for u in urls:
            # /app/assets/foo.png → dist/assets/foo.png
            rel = u[len("/app/") :]  # assets/foo.png
            p = dist / rel
            if not p.is_file():
                continue
            raw = p.read_bytes()
            if raw[:8] == PNG_MAGIC and p.stat().st_size > 1000:
                found = True
                # 与源 logo 同量级（防误指小图标）
                src_sz = (ROOT / "frontend/src/assets/logo.png").stat().st_size
                self.assertGreater(p.stat().st_size, src_sz * 0.5)
                break
        self.assertTrue(found, f"无可用 logo PNG；urls={urls}")

    def test_client_fetches_api_version(self):
        src = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
        self.assertIn("/api/version", src)
        self.assertIn("fetchProductVersion", src)

    def test_api_version_allows_viewer_session(self):
        src = (ROOT / "src/routes/config_api.py").read_text(encoding="utf-8")
        self.assertIn("_vacct(request)", src)
        self.assertIn("def api_version", src)


class TestVersionBump225(unittest.TestCase):
    def test_version_files(self):
        # 2.2.5 条目须保留在 changelog/version 历史中；当前产品号由后续版本文件维护
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        # 2.2.5 起产品号 2.x；后续 2.3.0 等递增仍合规
        self.assertRegex(ver, r"^2\.(2|3|4|5|6)\.\d+$")
        self.assertIn("2.2.5", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.5]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
