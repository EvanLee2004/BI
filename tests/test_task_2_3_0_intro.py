#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S4.A 登录入场特效结构守卫。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestIntro230(unittest.TestCase):
    def test_intro_splash_exists(self):
        p = FE / "components" / "IntroSplash.vue"
        self.assertTrue(p.is_file())
        src = p.read_text(encoding="utf-8")
        css = (FE / "styles" / "components" / "IntroSplash.css").read_text(encoding="utf-8")
        # 2.3.1 / 2.6.5：reduced-motion 在 chart-fx prefersReducedMotion 或 CSS
        self.assertTrue(
            "prefers-reduced-motion" in src
            or "prefersReducedMotion" in src
            or "prefers-reduced-motion" in css,
            "须尊重 reduced-motion",
        )
        self.assertIn("skip", src.lower())
        self.assertIn("logo", src.lower())
        self.assertIn("900", src)
        self.assertIn("1600", src)

    def test_login_sets_pending(self):
        # 登录页仍可写 pending（兼容）；2.3.1 刷新不依赖它
        view = (ROOT / "static" / "view_login.html").read_text(encoding="utf-8")
        self.assertIn("kanban_intro_pending", view)

    def test_app_mounts_intro(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("IntroSplash", app)
        self.assertIn("showIntro", app)


if __name__ == "__main__":
    unittest.main()
