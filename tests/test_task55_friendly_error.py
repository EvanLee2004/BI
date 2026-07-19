#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终局补漏：友好网络错误文案存在于 shipped 前端源。"""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestFriendlyError(unittest.TestCase):
    def test_util_and_wiring(self):
        util = (FE / "utils" / "friendlyError.ts").read_text(encoding="utf-8")
        self.assertIn("服务暂时不可达", util)
        self.assertIn("failed to fetch", util.lower())
        api = (FE / "admin" / "api.ts").read_text(encoding="utf-8")
        self.assertIn("friendlyError", api)
        self.assertIn("catch", api)


if __name__ == "__main__":
    unittest.main()
