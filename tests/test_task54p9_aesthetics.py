# -*- coding: utf-8 -*-
"""54.9 美学终修：主题 token / 字号地板 / EP 主色 结构断言（驱动真实 CSS 源文件）。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "static" / "css" / "theme.css"
BRIDGE = ROOT / "frontend" / "src" / "vendor" / "scifi-kit" / "scifi-bridge.css"
ADMIN = ROOT / "frontend" / "src" / "admin" / "styles" / "admin.css"
ECHARTS = ROOT / "frontend" / "src" / "echarts-theme.ts"

# R1 允许的间距刻度
GRID = {0, 4, 8, 12, 16, 24, 32, 48, 64}


def _css_var(src: str, name: str) -> str | None:
    m = re.search(rf"{re.escape(name)}\s*:\s*([^;]+);", src)
    return m.group(1).strip() if m else None


def _px(val: str) -> float | None:
    m = re.match(r"([\d.]+)px", val.strip())
    return float(m.group(1)) if m else None


class Test54p9DesignTokens(unittest.TestCase):
    def test_theme_spacing_on_8pt_grid(self):
        t = THEME.read_text(encoding="utf-8")
        for name in ("--gap-sec", "--gap-card", "--row-pad-y"):
            raw = _css_var(t, name)
            self.assertIsNotNone(raw, name)
            # may be multi-value for pad; take first px
            nums = [float(x) for x in re.findall(r"([\d.]+)px", raw or "")]
            self.assertTrue(nums, name)
            for n in nums:
                self.assertIn(n, GRID, f"{name}={n} not on 8pt grid")

    def test_theme_pad_card_kpi_grid(self):
        t = THEME.read_text(encoding="utf-8")
        for name in ("--pad-card", "--pad-kpi"):
            raw = _css_var(t, name)
            self.assertIsNotNone(raw, name)
            for n in [float(x) for x in re.findall(r"([\d.]+)px", raw or "")]:
                self.assertIn(n, GRID, f"{name} has {n}")

    def test_body_font_floor_12(self):
        """R4：主题 token 与关键小字类不得声明 <12px 正文字号。"""
        t = THEME.read_text(encoding="utf-8")
        # KPI 注记/周期等曾 <12
        for cls in (".kpi-note", ".kpi-period", ".kpi-cum-l", ".kpi-src", ".tb-ver", ".tb-sub", ".tb-time"):
            # find rule block roughly
            m = re.search(re.escape(cls) + r"\{[^}]*font-size:([\d.]+)px", t)
            if m:
                self.assertGreaterEqual(float(m.group(1)), 12.0, cls)

    def test_fs_ladder_tokens(self):
        t = THEME.read_text(encoding="utf-8")
        self.assertEqual(_css_var(t, "--fs-mut"), "12px")
        self.assertEqual(_css_var(t, "--fs-body"), "14px")
        self.assertEqual(_css_var(t, "--fs-sec"), "16px")
        kpi = _px(_css_var(t, "--fs-kpi") or "")
        self.assertIsNotNone(kpi)
        self.assertIn(kpi, GRID | {28, 32, 36})

    def test_bridge_54p9_section_exists(self):
        b = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("54.9", b)
        self.assertIn("--scifi-space-4", b)
        self.assertIn("min-height: 44px", b)

    def test_admin_ep_primary_is_scifi_cyan(self):
        a = ADMIN.read_text(encoding="utf-8")
        self.assertIn("--el-color-primary: #22d3ee", a)
        self.assertIn("max-width: 960px", a)
        self.assertIn("min-height: 44px", a)

    def test_echarts_axis_label_ge_12(self):
        s = ECHARTS.read_text(encoding="utf-8")
        # 不得再写 fontSize: 11
        self.assertNotRegex(s, r"fontSize:\s*11\b")
        self.assertRegex(s, r"fontSize:\s*12\b")


if __name__ == "__main__":
    unittest.main()
