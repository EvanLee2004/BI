#!/bin/sh
# 一键验证：语法 → 端到端跑 → 回归测试
set -e
cd "$(dirname "$0")/.."
echo "[1/3] 语法检查"
python3 -m py_compile src/*.py run.py tests/*.py
echo "[2/3] 端到端生成"
python3 run.py >/dev/null
echo "[3/3] 回归测试"
python3 tests/test_cockpit.py
echo "✓ 全部通过"
