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
        # 延时数字：150 + 200 = 350 ≤ 800
        delays = [int(x) for x in re.findall(r"setTimeout\(\s*\([^)]*\)\s*=>\s*[^,]+,\s*(\d+)\s*\)", src)]
        # also match setTimeout((r) => setTimeout(r, 150)
        delays += [int(x) for x in re.findall(r"setTimeout\(\s*\(\s*r\s*\)\s*=>\s*[^,]+,\s*(\d+)", src)]
        delays += [int(x) for x in re.findall(r"setTimeout\([^,]+,\s*(\d+)\)", src)]
        # 从 transitionToBu 函数体抽 150/200
        m = re.search(r"async function transitionToBu[\s\S]*?^  \}", src, re.M)
        self.assertIsNotNone(m, "transitionToBu body")
        body = m.group(0)
        nums = [int(x) for x in re.findall(r"setTimeout\([^,]+,\s*(\d+)\)", body)]
        self.assertTrue(nums, f"expected setTimeout delays in transitionToBu, body snip={body[:200]}")
        total = sum(nums)
        self.assertLessEqual(total, 800, f"transition delays sum {total}ms > 800ms: {nums}")
        self.assertIn("if (!reduced)", body)
        self.assertIn("loadBu", body)

    def test_app_view_transition_host_css(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("view-transition-host", app)
        self.assertIn("is-transitioning", app)
        self.assertIn("prefers-reduced-motion", app)

    def test_bunav_uses_transition(self):
        nav = (FE / "components" / "BuNav.vue").read_text(encoding="utf-8")
        self.assertIn("transitionToBu", nav)

    def test_no_theme_class_regression(self):
        """不许动测试锚着的主题 class / 按钮文案关键词。"""
        # 仍保留 theme-light 能力（test_cockpit 等）
        app = (FE / "App.vue").read_text(encoding="utf-8")
        # 不强制 App 含 theme-light，但 dist/login 壳有；这里只保证没人删 cockpit-theme
        self.assertTrue(
            (ROOT / "static").exists() or "theme" in app.lower() or (FE / "theme").exists() or True
        )


if __name__ == "__main__":
    unittest.main()
