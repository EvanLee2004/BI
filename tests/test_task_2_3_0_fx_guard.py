#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S3：图表闪光仅霓虹；非霓虹 animation:false 守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestFxGuard230(unittest.TestCase):
    def test_echarts_host_non_neon_animation_false(self):
        src = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")
        self.assertIn("animation: false", src)
        self.assertIn("fxLevel", src)
        # 霓虹 canvas / 暗亮 svg
        self.assertIn("canvas", src)
        self.assertIn("svg", src)

    def test_chart_fx_level_dark_light_zero(self):
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("fxLevel", src)
        self.assertIn("prefersReducedMotion", src)
        # dark/light 路径返回 0
        self.assertIn("return 0", src)
        self.assertIn("neon", src)

    def test_reduced_motion_forces_zero(self):
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        # prefersReducedMotion 真 → fxLevel 0
        self.assertIn("if (prefersReducedMotion()) return 0", src)

    def test_glow_styles_branch_on_fx(self):
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("barGlowStyle", src)
        self.assertIn("lineGlowStyle", src)
        self.assertIn("areaGradient", src)
        self.assertIn("shadowBlur: fx ? 10", src)

    def test_breath_tombstone_kept(self):
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("breathScatterSeries", src)


if __name__ == "__main__":
    unittest.main()
