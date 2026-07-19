#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 page_size 不得被 500 静默截断。"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db.detail as detail  # noqa: E402


class TestExportCap(unittest.TestCase):
    def test_query_detail_accepts_max_page_size(self):
        sig = inspect.signature(detail.query_detail)
        self.assertIn("max_page_size", sig.parameters)
        self.assertEqual(sig.parameters["max_page_size"].default, 500)


if __name__ == "__main__":
    unittest.main()
