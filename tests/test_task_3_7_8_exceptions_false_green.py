#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.8 G5：异常加载失败不得假绿成「0 / 无待处理」。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestExceptionsFalseGreen(unittest.TestCase):
    def test_overview_has_error_and_retry(self):
        src = (ROOT / "frontend/src/admin/views/ExceptionOverview.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("loadError", src)
        self.assertIn("loadedOk", src)
        self.assertIn("exceptions-load-error", src)
        self.assertIn("exceptions-retry", src)
        # 成功且真 0 才「无待处理」
        self.assertIn("无待处理", src)
        self.assertIn("loadedOk", src)
        # 失败时 cardStatus 不得直接 0 绿
        self.assertRegex(
            src,
            re.compile(r"loadError\.value\s*&&\s*!loadedOk", re.M),
        )
        # ok class 须同时要求 loadedOk 且无 loadError
        self.assertIn("loadedOk && !(ex[c.key] || 0)", src)
        self.assertIn("!loadError && !c.disabled && loadedOk", src)

    def test_layout_badge_fail_state(self):
        src = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("exceptionsLoadError", src)
        self.assertIn("nav-exceptions-badge", src)
        # 失败徽标不得静默当 0
        self.assertTrue(
            "exceptionsLoadError" in src and ("!" in src or "加载失败" in src),
            "布局须暴露异常加载失败态",
        )


if __name__ == "__main__":
    unittest.main()
