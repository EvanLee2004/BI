# -*- coding: utf-8 -*-
"""3.7.5 G4：390 顶栏/管理导航/设置控件/表格完整路径 守卫。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestResponsive375(unittest.TestCase):
    def test_topbar_390_wrap_hierarchy(self):
        app = (FE / "styles/components/App.css").read_text(encoding="utf-8")
        theme = (ROOT / "static/css/theme.css").read_text(encoding="utf-8")
        self.assertIn("tb-today", app)
        # 390 两行分层在 theme（S7）；不得隐藏更新时间
        compact = theme.replace(" ", "").replace("\n", "")
        self.assertIn("flex-wrap:wrap!important", compact)
        self.assertIn("max-height:none", compact)
        self.assertNotIn(".tb-today { display: none", app.replace("\n", " "))

    def test_admin_nav_horizontal_scroll(self):
        css = (FE / "admin/layout/admin-layout.css").read_text(encoding="utf-8")
        self.assertIn("overflow-x: auto", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn("writing-mode: horizontal-tb", css)
        self.assertIn("admin-page-skeleton", css)

    def test_settings_token_controls(self):
        css = (FE / "admin/views/settings-view.css").read_text(encoding="utf-8")
        self.assertIn("el-input-number", css)
        self.assertIn("--admin-panel", css)
        self.assertIn("max-width: 1200px", css)

    def test_detail_truncation_title_path(self):
        vue = (FE / "admin/views/DetailView.vue").read_text(encoding="utf-8")
        self.assertIn("show-overflow-tooltip", vue)
        self.assertIn(":title=", vue)
        self.assertIn("cell-clip", vue)

    def test_user_stats_scannable(self):
        vue = (FE / "admin/views/UserStatsView.vue").read_text(encoding="utf-8")
        self.assertIn('data-testid="user-stats-note"', vue)
        # 说明压缩：不再堆砌长段
        desc = ""
        for line in vue.splitlines():
            if "user-stats-note" in line or "主指标" in line:
                desc += line
        self.assertIn("主指标", desc)


if __name__ == "__main__":
    unittest.main()
