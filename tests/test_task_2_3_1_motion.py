#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.1 count-up + 2.6.9 U-5 IntroSplash 已下线守卫。"""
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
        self.assertIn("onDone(disp)", src)
        self.assertIn("isAnimatableDisp", src)

    def test_countup_no_disp_parse(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        for pat in (r"parseFloat\s*\([^)]*disp", r"Number\s*\([^)]*disp"):
            self.assertIsNone(re.search(pat, src, re.I), pat)

    def test_intro_splash_removed_2_6_9(self):
        """U-5：短入场动画下线，切 BU 仍用 BuTransitionOverlay。"""
        self.assertFalse((FE / "components" / "IntroSplash.vue").is_file())
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertNotIn("IntroSplash", app)
        self.assertNotIn("showIntro", app)
        self.assertIn("BuTransitionOverlay", app)


if __name__ == "__main__":
    unittest.main()
