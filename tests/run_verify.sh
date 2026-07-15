#!/bin/sh
# 一键验证：语法 → 端到端 → 回归红线 → 回归测试
# C 提速：轻量无共享态用例并行（KANBAN_VERIFY_JOBS，默认 4）。
# 写库 / generate / 碰 server._LOCK·_state 的用例强制串行，避免竞态。
# KANBAN_VERIFY_JOBS=1 → 全部串行。
set -e
cd "$(dirname "$0")/.."
export KANBAN_OFFLINE=1
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
JOBS="${KANBAN_VERIFY_JOBS:-4}"
echo "用解释器：$PY  并行 jobs=$JOBS"
echo "[1/4] 语法检查"
$PY -m py_compile src/*.py src/ingest/*.py run.py tests/*.py
echo "[2/4] 端到端生成"
$PY run.py >/dev/null
echo "[3/4] 回归红线：从库算 == 从文件算（一分不差）"
$PY tests/regress_db_vs_files.py
echo "[4/4] 回归测试"
# 写库 / generate / 全局锁 / HTTP 服务态
SERIAL="
tests/test_cockpit.py
tests/test_datalayer.py
tests/test_adjust.py
tests/test_server.py
tests/test_admin_edit.py
tests/test_budget.py
tests/test_expense_views.py
tests/test_daily.py
tests/test_profit_ranking.py
tests/test_bu.py
tests/test_auth.py
tests/test_multibu.py
tests/test_update.py
tests/test_alloc_monthly.py
tests/test_detax.py
tests/test_api_v1_numbers.py
tests/test_a2_inhouse_name.py
tests/test_a5_bu_ledger_isolation.py
tests/test_b_page_assemble.py
tests/test_b_p3_cards.py
tests/test_b_p4_remainder.py
tests/test_serve_shell.py
tests/test_b_p5_no_view.py
tests/test_b_p4_login_static.py
"
# 无共享进程态（或只读静态文件）
PARALLEL="
tests/test_fetch_zhiyun.py
tests/test_bugfix_0711.py
tests/test_exceptions.py
tests/test_iter16.py
tests/test_version.py
tests/test_schedule.py
tests/test_iter21.py
tests/test_iter22.py
tests/test_profile.py
tests/test_admin_static.py
tests/test_no_html_in_py.py
tests/test_b_p0_rankings_assemble.py
tests/test_b_p0_shipped_path.py
tests/test_b_shipped_cards.py
tests/test_b_http_shipped.py
tests/test_b_p1_contract.py
"
run_one() {
  f="$1"
  log=$(mktemp -t kanban_t.XXXXXX)
  if $PY tests/run_test.py "$f" >"$log" 2>&1; then
    echo "OK  $f"
    rm -f "$log"
    return 0
  fi
  echo "FAIL $f"
  cat "$log"
  rm -f "$log"
  return 1
}

echo "  · 串行（写库/服务态）"
for f in $SERIAL; do
  run_one "$f" || exit 1
done

echo "  · 并行（jobs=$JOBS）"
if [ "$JOBS" = "1" ]; then
  for f in $PARALLEL; do
    run_one "$f" || exit 1
  done
else
  fail=0
  running=0
  pids=""
  for f in $PARALLEL; do
    while [ "$running" -ge "$JOBS" ]; do
      set +e
      wait $(echo $pids | awk '{print $1}')
      st=$?
      set -e
      pids=$(echo $pids | awk '{$1=""; sub(/^ /,""); print}')
      running=$((running - 1))
      [ "$st" -eq 0 ] || fail=1
    done
    run_one "$f" &
    pids="$pids $!"
    running=$((running + 1))
  done
  for pid in $pids; do
    set +e
    wait "$pid"
    st=$?
    set -e
    [ "$st" -eq 0 ] || fail=1
  done
  [ "$fail" -eq 0 ] || exit 1
fi
echo "✓ 全部通过"
