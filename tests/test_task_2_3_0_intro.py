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
        # 2.3.1：仍可兼容清理 pending；核心改为每次刷新 + min/max
        self.assertIn("prefers-reduced-motion", src)
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
