#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一跑单个测试脚本：先装 support（SERVE_SHELL=False），再 run_path。

用法：.venv/bin/python tests/run_test.py tests/test_auth.py
run_verify.sh 全部经此入口，避免 26 个文件逐个改 SERVE_SHELL。
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT / "src"))

import support  # noqa: E402,F401  # 安装 SERVE_SHELL=False

if len(sys.argv) < 2:
    print("用法: python tests/run_test.py tests/test_xxx.py", file=sys.stderr)
    sys.exit(2)

script = Path(sys.argv[1]).resolve()
sys.argv = [str(script)] + sys.argv[2:]
runpy.run_path(str(script), run_name="__main__")
