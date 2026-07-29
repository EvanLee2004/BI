#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.0.0：原 HTML render 驾驶舱测已退役（模块物理删除）。

本文件保留为「render 不可 import」守卫，避免旧测再挂 SERIAL。
"""
from __future__ import annotations

import importlib
import unittest


class TestRenderRetired(unittest.TestCase):
    def test_render_module_gone(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("render")


if __name__ == "__main__":
    unittest.main()
