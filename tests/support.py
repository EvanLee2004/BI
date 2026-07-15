#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试公共引导（唯一入口）：关闭 SERVE_SHELL，HTTP 测试直出 HTML 便于断言。

由 tests/run_test.py 在加载任意测试脚本前 import；禁止在各 test_*.py 里散改。
需要测生产 shell 路径时，在用例内临时 server.SERVE_SHELL = True，finally 恢复 False。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import server  # noqa: E402

server.SERVE_SHELL = False
