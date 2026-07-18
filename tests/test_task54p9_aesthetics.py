# -*- coding: utf-8 -*-
"""54.9 美学终修：扫描真实 CSS 源 —— 字号地板 + 8pt 间距 + EP/登录主色。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "static" / "css" / "theme.css"
BRIDGE = ROOT / "frontend" / "src" / "vendor" / "scifi-kit" / "scifi-bridge.css"
ADMIN = ROOT / "frontend" / "src" / "admin" / "styles" / "admin.css"
LOGIN = ROOT / "frontend" / "src" / "components" / "LoginView.vue"
ECHARTS = ROOT / "frontend" / "src" / "echarts-theme.ts"

GRID = {0, 4, 8, 12, 16, 24, 32, 48, 64}
# 仅允许的「非正文」例外：无（R4 零容忍 <12 正文字号）
FONT_WHITELIST_RE = re.compile(
    r"(?:width|height|border(?:-radius)?|outline|box-shadow|letter-spacing|stroke-width)\s*:\s*[\d.]+px",
    re.I,
)


def _font_sizes(css: str) -> list[tuple[int, float, str]]:
    out = []
    for i, line in enumerate(css.splitlines(), 1):
        for m in re.finditer(r"font-size\s*:\s*([\d.]+)px", line, re.I):
            out.append((i, float(m.group(1)), line.strip()[:100]))
    return out


def _spacing_px(css: str) -> list[tuple[int, str, float, str]]:
    out = []
    prop_re = re.compile(
        r"(padding|padding-top|padding-right|padding-bottom|padding-left|"
        r"margin|margin-top|margin-right|margin-bottom|margin-left|"
        r"gap|row-gap|column-gap)\s*:\s*([^;{}]+)",
        re.I,
    )
    for i, line in enumerate(css.splitlines(), 1):
        for m in prop_re.finditer(line):
            prop, rest = m.group(1).lower(), m.group(2)
            for n in re.findall(r"([\d.]+)px", rest):
                out.append((i, prop, float(n), line.strip()[:100]))
    return out


class Test54p9DesignTokens(unittest.TestCase):
    def test_no_font_size_below_12_in_theme_and_bridge(self):
        for path in (THEME, BRIDGE):
            css = path.read_text(encoding="utf-8")
            bad = [(ln, v, s) for ln, v, s in _font_sizes(css) if v < 12]
            self.assertEqual(bad, [], f"{path.name} font-size<12: {bad[:8]}")

    def test_spacing_on_8pt_grid_theme_bridge_admin(self):
        for path in (THEME, BRIDGE, ADMIN):
            css = path.read_text(encoding="utf-8")
            bad = []
            for ln, prop, v, s in _spacing_px(css):
                if v not in GRID:
                    bad.append((ln, prop, v, s))
            self.assertEqual(bad, [], f"{path.name} nongrid spacing: {bad[:12]}")

    def test_fs_ladder_tokens(self):
        t = THEME.read_text(encoding="utf-8")
        self.assertIn("--fs-mut:12px", t)
        self.assertIn("--fs-body:14px", t)
        self.assertIn("--fs-sec:16px", t)
        self.assertIn("--fs-kpi:32px", t)
        self.assertIn("--gap-card:16px", t)
        self.assertIn("--gap-sec:32px", t)

    def test_admin_settings_max_width_960(self):
        a = ADMIN.read_text(encoding="utf-8")
        self.assertRegex(a, r"\.admin-root\s+\.settings\s*\{[^}]*max-width:\s*960px", re.S)
        self.assertIn("--el-color-primary: #22d3ee", a)

    def test_login_btn_scifi_cyan(self):
        v = LOGIN.read_text(encoding="utf-8")
        self.assertIn("#22d3ee", v)
        self.assertIn("login-btn", v)
        # 禁止纯紫主按钮
        self.assertNotRegex(v, r"login-btn[^{]*\{[^}]*#8b5cf6", re.S | re.I)

    def test_echarts_axis_label_ge_12(self):
        s = ECHARTS.read_text(encoding="utf-8")
        self.assertNotRegex(s, r"fontSize:\s*11\b")
        self.assertRegex(s, r"fontSize:\s*12\b")

    def test_bridge_mobile_44(self):
        b = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("min-height: 44px", b)
        t = THEME.read_text(encoding="utf-8")
        self.assertIn("min-height:44px", t.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
