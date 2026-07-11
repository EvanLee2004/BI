#!/bin/sh
# 一键验证：语法 → 端到端跑 → 回归红线(库vs文件) → 回归测试 + 数据层/调整/服务测试
# 优先用项目 venv 的 python（含 fastapi/openpyxl）；没有则退回 python3。
set -e
cd "$(dirname "$0")/.."
# 测试/回归一律离线：不碰智云网络、不改进料口（在线抓的正确性由 test_fetch_zhiyun 桩测覆盖）
export KANBAN_OFFLINE=1
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
echo "用解释器：$PY"
echo "[1/4] 语法检查"
$PY -m py_compile src/*.py src/ingest/*.py run.py tests/*.py
echo "[2/4] 端到端生成"
$PY run.py >/dev/null
echo "[3/4] 回归红线：从库算 == 从文件算（一分不差）"
$PY tests/regress_db_vs_files.py
echo "[4/4] 回归测试"
$PY tests/test_cockpit.py
$PY tests/test_datalayer.py
$PY tests/test_adjust.py
$PY tests/test_server.py
$PY tests/test_admin_edit.py
$PY tests/test_fetch_zhiyun.py
$PY tests/test_budget.py
$PY tests/test_expense_views.py
$PY tests/test_bugfix_0711.py
$PY tests/test_exceptions.py
$PY tests/test_daily.py
$PY tests/test_bu.py
$PY tests/test_auth.py
echo "✓ 全部通过"
