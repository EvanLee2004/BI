# -*- coding: utf-8 -*-
"""2.6.9 U-5：IntroSplash 已下线——守卫断言组件与 App 入口不存在。"""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestIntroSplashRemoved(unittest.TestCase):
    def test_component_gone(self):
        self.assertFalse((FE / "components" / "IntroSplash.vue").is_file())
        self.assertFalse((FE / "styles" / "components" / "IntroSplash.css").is_file())

    def test_app_no_show_intro(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertNotIn("IntroSplash", app)
        self.assertNotIn("showIntro", app)


if __name__ == "__main__":
    unittest.main()
