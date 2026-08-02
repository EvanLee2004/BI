#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.6 B：字号 token / 关键选择器守卫（静态；不启浏览器）。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "frontend/src/styles/tokens.css"
BUNAV = ROOT / "frontend/src/styles/components/BuNav.css"
BRIDGE = ROOT / "frontend/src/vendor/scifi-kit/scifi-bridge.css"
ADMIN = ROOT / "frontend/src/admin/styles/admin.css"
THEME = ROOT / "static/css/theme.css"
EXPORT = ROOT / "src/export_pl_xlsx.py"


class Test376ReadabilityTokens(unittest.TestCase):
    def test_tokens_fs_ladder_bumped(self):
        t = TOKENS.read_text(encoding="utf-8")
        self.assertRegex(t, r"--fs-meta:\s*12px")
        self.assertRegex(t, r"--fs-caption:\s*13px")
        self.assertRegex(t, r"--fs-body:\s*15px")
        self.assertRegex(t, r"--fs-card-h:\s*15px")
        # KPI 大数默认不动 ~38
        self.assertRegex(t, r"--fs-kpi:\s*38px")

    def test_rank_amt_not_eleven_px(self):
        t = TOKENS.read_text(encoding="utf-8")
        # dual / dual-row 不得再钉死 11px
        dual = re.findall(r"rank-bar__.*__amt[^{]*\{[^}]+\}", t, flags=re.S)
        blob = "\n".join(dual) if dual else t
        self.assertNotIn("font-size: 11px", blob)
        self.assertIn("var(--fs-caption", t)

    def test_bu_nav_taller(self):
        css = BUNAV.read_text(encoding="utf-8")
        self.assertIn("min-height: 40px", css)
        self.assertIn("font-size: 16.5px", css)

    def test_kpi_title_centered_and_hint_ge12(self):
        b = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("kpi-title-row", b)
        # 居中硬需求
        self.assertIn("justify-content: center", b)
        self.assertRegex(b, r"\.kpi-hint\s*\{[^}]*font-size:\s*12px", re.S)
        # sec 略放大
        self.assertRegex(b, r"\.sec-n\s*\{[^}]*font-size:\s*13\.5px", re.S)
        self.assertRegex(b, r"\.sec-t\s*\{[^}]*font-size:\s*18\.5px", re.S)

    def test_admin_el_small_thirteen(self):
        a = ADMIN.read_text(encoding="utf-8")
        self.assertRegex(a, r"--el-font-size-small:\s*13px")

    def test_theme_toggle_min_height(self):
        th = THEME.read_text(encoding="utf-8")
        self.assertIn("min-height:34px", th.replace(" ", ""))
        self.assertIn("min-height:32px", th.replace(" ", ""))

    def test_export_expands_children_present(self):
        src = EXPORT.read_text(encoding="utf-8")
        self.assertIn('ln.get("children")', src)
        self.assertIn("expandable", src)
        self.assertIn("child_indent", src)


if __name__ == "__main__":
    unittest.main()
