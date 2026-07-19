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
echo "[1/5] 语法检查"
$PY -m py_compile src/*.py src/ingest/*.py src/routes/*.py run.py tests/*.py
# 任务书54.12·R-08：ruff 卫生红线（EXIT 非 0 即 FAIL）
if [ -x .venv/bin/ruff ]; then
  echo "[1a/5] ruff check src/"
  .venv/bin/ruff check src/ || exit 1
elif command -v ruff >/dev/null 2>&1; then
  echo "[1a/5] ruff check src/"
  ruff check src/ || exit 1
else
  echo "[1a/5] ruff 未安装，跳过（建议 .venv 装 ruff）"
fi
# 任务书51·B8：前端契约类型检查（vue-tsc --noEmit）
if [ -d frontend/node_modules ] && [ -f frontend/package.json ]; then
  echo "[1b/5] 前端 vue-tsc --noEmit"
  (cd frontend && npm run typecheck) || exit 1
fi
echo "[2/5] 端到端生成"
$PY run.py >/dev/null
echo "[3/5] 回归红线：从库算 == 从文件算（一分不差）"
$PY tests/regress_db_vs_files.py
echo "[4/5] 回归测试"
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
tests/test_b_bu_shipped_assemble.py
tests/test_login_cache_p0.py
tests/test_ranking_monthly_a8.py
tests/test_publish_once.py
tests/test_b_p0_shipped_path.py
tests/test_b_shipped_cards.py
tests/test_b_http_shipped.py
tests/test_db_atomic_rebuild.py
tests/test_money_fen.py
tests/test_db_a4a7.py
tests/test_hygiene_b.py
tests/test_budget_rates_adj_migrate.py
tests/test_task37_filters.py
tests/test_task37_expense_perm.py
tests/test_task37_fetch_banner.py
tests/test_task39.py
tests/test_gzip_fragments.py
tests/test_task41.py
tests/test_task42_final.py
tests/test_task43_nginx_mode.py
tests/test_task43_arch.py
tests/test_task46_stage0.py
tests/test_task50_stage_b.py
tests/test_authz.py
tests/test_vm_contract.py
tests/test_config_engine.py
tests/test_backup_restore.py
tests/test_domain_reexport.py
tests/test_echarts_vm_labels.py
tests/frontend/parity/test_parity_structure.py
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
tests/test_admin_vue_54d.py
tests/test_no_html_in_py.py
tests/test_b_p0_rankings_assemble.py
tests/test_b_p1_contract.py
tests/test_task37_ui.py
tests/test_year2027.py
tests/test_split_static.py
tests/test_linux_deploy.py
tests/test_task51_pl_structure.py
tests/test_task51_assemble_vm.py
tests/test_task51_authz_access.py
tests/test_task51_batch5.py
tests/test_task51_frontend_types.py
tests/test_task52_fixes.py
tests/test_task54_scifi.py
tests/test_task54p1_visual.py
tests/test_task54p4_receipts_b4.py
tests/test_task54p14_r20_no_double_wan.py
tests/test_task54p14_r21_r26.py
tests/test_task54p12_export_consistency.py
tests/test_task54p15_chart_whitelist.py
tests/test_task55_friendly_error.py
tests/test_task56_r45_ledger_caliber.py
tests/test_task57_b5_frontend_errors.py
tests/test_task57_b6_domain_coverage.py
tests/test_task57_c_export_cap.py
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
