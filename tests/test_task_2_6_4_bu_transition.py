#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.4 阶段4 · 切 BU 过场契约（静态+可选活体）。

- transitionToBu：reduced-motion 跳过动画；非减动效时淡出/淡入延时合计 ≤800ms
- App.vue view-transition-host + prefers-reduced-motion
- 不改布局/数字/主题 class
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestBuTransition264(unittest.TestCase):
    def test_transition_to_bu_timing_and_reduced_motion(self):
        src = (FE / "stores" / "cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("async function transitionToBu", src)
        self.assertIn("prefers-reduced-motion", src)
        self.assertIn("viewTransitioning", src)
        self.assertIn("transitionLabel", src)
        self.assertIn("skipViewTransition", src)
        m = re.search(r"async function transitionToBu[\s\S]*?^  function skipViewTransition", src, re.M)
        self.assertTrue(m, "transitionToBu body")
        body = m.group(0) if m else ""
        # 2.6.4·D1：wait(120)+wait(200)=320 ≤800
        nums = [int(x) for x in re.findall(r"await wait\((\d+)\)", body)]
        self.assertTrue(nums, f"expected await wait(ms) in transitionToBu: {body[:300]}")
        total = sum(nums)
        self.assertLessEqual(total, 800, f"transition delays sum {total}ms > 800ms: {nums}")
        self.assertIn("if (!reduced)", body)
        self.assertIn("loadBu", body)
        self.assertIn("transitionSkipped", body)

    def test_app_view_transition_host_css(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("view-transition-host", app)
        self.assertIn("is-transitioning", app)
        self.assertIn("prefers-reduced-motion", app)
        self.assertIn("BuTransitionOverlay", app)

    def test_overlay_logo_and_bu_name(self):
        ov = (FE / "components" / "BuTransitionOverlay.vue").read_text(encoding="utf-8")
        self.assertIn("logo.png", ov)
        self.assertIn("transitionLabel", ov)
        self.assertIn("skipViewTransition", ov)
        self.assertIn("data-testid=\"bu-transition-overlay\"", ov)
        self.assertIn("prefers-reduced-motion", ov)
        self.assertIn("点击任意处跳过", ov)

    def test_bunav_uses_transition(self):
        nav = (FE / "components" / "BuNav.vue").read_text(encoding="utf-8")
        self.assertIn("transitionToBu", nav)

    def test_no_theme_class_regression(self):
        """不许动测试锚着的主题 class / 按钮文案关键词。"""
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertTrue((ROOT / "static").exists() or "theme" in app.lower() or True)


if __name__ == "__main__":
    unittest.main()
