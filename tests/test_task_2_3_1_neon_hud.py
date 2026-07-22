#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1：霓虹 HUD/背景选择器存在；light/:root 基线未改值的结构守卫。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "theme.css").read_text(encoding="utf-8")
BRIDGE = (ROOT / "frontend/src/vendor/scifi-kit/scifi-bridge.css").read_text(encoding="utf-8")


class TestNeonHud231(unittest.TestCase):
    def test_neon_hud_selectors(self):
        self.assertIn('[data-theme="neon"]', BRIDGE)
        self.assertIn("clip-path", BRIDGE)
        self.assertIn("neon-kpi-in", BRIDGE)
        self.assertIn("no-hud-clip", BRIDGE)

    def test_neon_space_bg(self):
        self.assertIn("neon-grid-drift", CSS)
        self.assertIn("neon-scan", CSS)
        self.assertIn("prefers-reduced-motion", CSS)

    def test_root_dark_bg_unchanged(self):
        # :root 基础块仍含深空 --bg:#04060d
        m = re.search(r":root\{[^}]*--bg:#04060d", CSS)
        self.assertTrue(m, "deep space :root --bg must remain #04060d")

    def test_light_block_still_has_f4f7fb(self):
        self.assertIn("--bg:#f4f7fb", CSS)

    def test_pie_glow_helper(self):
        fx = (ROOT / "frontend/src/chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("pieGlowItemStyle", fx)
        self.assertTrue("fxLevel() === 1" in fx or "fxLevel()===1" in fx)

    def test_bu_transition(self):
        st = (ROOT / "frontend/src/stores/cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("viewTransitioning", st)
        self.assertIn("transitionToBu", st)


if __name__ == "__main__":
    unittest.main()
