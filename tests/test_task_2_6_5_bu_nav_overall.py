# -*- coding: utf-8 -*-
"""2.6.5·C/D：BU 过场 1s 文案 + 「整体」按钮权限。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestBuTransition265(unittest.TestCase):
    def test_transition_1s_and_copy(self):
        store = (FE / "stores" / "cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("await wait(1000)", store)
        self.assertIn("transitionToMain", store)
        ov = (FE / "components" / "BuTransitionOverlay.vue").read_text(encoding="utf-8")
        self.assertIn("正在计算", ov)
        self.assertIn("BU 数据", ov)
        self.assertIn("skipViewTransition", ov)
        css = (FE / "styles" / "components" / "BuTransitionOverlay.css").read_text(encoding="utf-8")
        self.assertIn("bu-xfade-scan", css)
        self.assertIn("prefers-reduced-motion", css)
        # 时长锁 1s（token 或 1000）
        self.assertTrue(
            "wait(1000)" in store or "--dur-bu-transition: 1s" in (FE / "styles" / "tokens.css").read_text()
        )

    def test_countup_suppressed_during_transition(self):
        src = (FE / "components" / "CountUpNumber.vue").read_text(encoding="utf-8")
        self.assertIn("viewTransitioning", src)
        self.assertIn("过场期间", src)

    def test_overall_button_permission(self):
        nav = (FE / "components" / "BuNav.vue").read_text(encoding="utf-8")
        self.assertIn("bu-nav-overall", nav)
        self.assertIn("整体", nav)
        self.assertIn("can_main", nav)
        self.assertIn("showOverall", nav)
        self.assertIn("transitionToMain", nav)
        # BU 无 can_main 时不渲染
        self.assertIn("v-if=\"showOverall\"", nav)


class TestOverallBtnHttpIsolation(unittest.TestCase):
    """BU 会话 session 无 can_main → 前端不展示；整体有 can_main。"""

    def test_source_lock(self):
        nav = (FE / "components" / "BuNav.vue").read_text(encoding="utf-8")
        self.assertRegex(nav, r"canMain\.value\s*=\s*!!")
        self.assertIn("is_admin", nav)


if __name__ == "__main__":
    unittest.main()
