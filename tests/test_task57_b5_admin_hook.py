#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-5：管理端 bootstrap 必须挂前端错误钩子（与看端一致）。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestAdminB5Hook(unittest.TestCase):
    def test_boot_admin_installs_reporter(self):
        src = (ROOT / "frontend/src/admin/bootstrap.ts").read_text(encoding="utf-8")
        self.assertIn("installFrontendErrorReporter", src)
        self.assertIn("bootAdmin", src)
        # 必须实际调用，不能只 import
        self.assertRegex(src, r"installFrontendErrorReporter\s*\(")

    def test_boot_cockpit_installs_reporter(self):
        src = (ROOT / "frontend/src/boot-cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("installFrontendErrorReporter", src)
        self.assertRegex(src, r"installFrontendErrorReporter\s*\(")


if __name__ == "__main__":
    unittest.main()
