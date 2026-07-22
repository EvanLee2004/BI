#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1 S1：count-up 解绑主题 + intro 每次刷新/时长守卫。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestMotion231(unittest.TestCase):
    def test_countup_not_theme_gated(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        self.assertIn("prefersReducedMotion", src)
        self.assertNotIn("fxLevel() !== 1", src)
        self.assertNotIn("fxLevel() === 1", src)
        # 终帧仍直赋
        self.assertIn("onDone(disp)", src)
        self.assertIn("isAnimatableDisp", src)

    def test_countup_no_disp_parse(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        for pat in (r"parseFloat\s*\([^)]*disp", r"Number\s*\([^)]*disp"):
            self.assertIsNone(re.search(pat, src, re.I), pat)

    def test_intro_every_refresh_bounds(self):
        intro = (FE / "components" / "IntroSplash.vue").read_text(encoding="utf-8")
        self.assertIn("MIN_SHOW_MS", intro)
        self.assertIn("900", intro)
        self.assertIn("1600", intro)
        self.assertIn("dataReady", intro)
        # 不依赖主题
        self.assertNotIn("fxLevel", intro)
        self.assertNotIn("themeMode", intro)
        # admin / reduced-motion 跳过
        self.assertIn("/admin", intro)
        self.assertIn("prefersReducedMotion", intro)

    def test_app_shows_intro_on_boot(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("showIntro.value = true", app)
        self.assertIn(":data-ready", app)


if __name__ == "__main__":
    unittest.main()
