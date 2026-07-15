#!/bin/sh
# 一键验证：语法 → 端到端跑 → 回归红线(库vs文件) → 回归测试 + 数据层/调整/服务测试
# 优先用项目 venv 的 python（含 fastapi/openpyxl）；没有则退回 python3。
# HTTP 测试统一经 tests/run_test.py（先装 support：SERVE_SHELL=False）。
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
run_t() { $PY tests/run_test.py "$1"; }
run_t tests/test_cockpit.py
run_t tests/test_datalayer.py
run_t tests/test_adjust.py
run_t tests/test_server.py
run_t tests/test_admin_edit.py
run_t tests/test_fetch_zhiyun.py
run_t tests/test_budget.py
run_t tests/test_expense_views.py
run_t tests/test_bugfix_0711.py
run_t tests/test_exceptions.py
run_t tests/test_daily.py
run_t tests/test_profit_ranking.py
run_t tests/test_bu.py
run_t tests/test_auth.py
run_t tests/test_iter16.py
run_t tests/test_version.py
run_t tests/test_schedule.py
run_t tests/test_multibu.py
run_t tests/test_update.py
run_t tests/test_alloc_monthly.py
run_t tests/test_iter21.py
run_t tests/test_iter22.py
run_t tests/test_profile.py
run_t tests/test_detax.py
run_t tests/test_api_v1_numbers.py
run_t tests/test_admin_static.py
run_t tests/test_serve_shell.py
run_t tests/test_no_html_in_py.py
run_t tests/test_a2_inhouse_name.py
run_t tests/test_a5_bu_ledger_isolation.py
run_t tests/test_b_p0_rankings_assemble.py
run_t tests/test_b_p1_contract.py
run_t tests/test_b_page_assemble.py
echo "✓ 全部通过"
