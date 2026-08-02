# -*- coding: utf-8 -*-
"""3.7.5：管理端切组 loading/skeleton/失败重试契约（静态 + 源码守卫）。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "frontend" / "src" / "admin" / "layout" / "AdminLayout.vue"
CSS = ROOT / "frontend" / "src" / "admin" / "layout" / "admin-layout.css"


class TestAdminPageLoading375(unittest.TestCase):
    def test_layout_has_loading_error_retry(self):
        text = LAYOUT.read_text(encoding="utf-8")
        self.assertIn('data-testid="admin-page-loading"', text)
        self.assertIn('data-testid="admin-page-error"', text)
        self.assertIn('data-testid="admin-page-retry"', text)
        self.assertIn("pageLoading", text)
        self.assertIn("retryPageLoad", text)
        self.assertIn("beginPageLoad", text)
        # 切换时隐藏旧页，避免误操作
        self.assertIn("v-show=\"!pageLoading && !pageError\"", text)
        self.assertIn("router.beforeEach", text)
        self.assertIn("router.onError", text)

    def test_skeleton_styles_present(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".admin-page-skeleton", css)
        self.assertIn(".admin-page-error", css)
        self.assertIn("admin-sk-shimmer", css)


if __name__ == "__main__":
    unittest.main()
