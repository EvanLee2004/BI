#!/bin/sh
# 一键验证：语法 → 端到端 → 回归红线 → 回归测试
# C 提速：轻量无共享态用例并行（KANBAN_VERIFY_JOBS，默认 4）。
# 写库 / generate / 碰 server._LOCK·_state 的用例强制串行，避免竞态。
# KANBAN_VERIFY_JOBS=1 → 全部串行。
# 3.6.0 G0：离线必物化脱敏 fixture；KANBAN_PROFILE=dev；报告本轮真实 skip；关键 skip≠0 非 0。
set -e
cd "$(dirname "$0")/.."
export KANBAN_OFFLINE=1
# TEST-ENV-001：独占 数据/ 与 DB，防并行 materialize 污染假红
VERIFY_LOCK="${KANBAN_VERIFY_LOCK:-$PWD/数据/.verify.lock}"
mkdir -p "$(dirname "$VERIFY_LOCK")" 2>/dev/null || true
if command -v flock >/dev/null 2>&1; then
  exec 9>"$VERIFY_LOCK"
  if ! flock -n 9; then
    echo "VERIFY locked by another run ($VERIFY_LOCK). Wait or set KANBAN_VERIFY_LOCK=..."
    exit 75
  fi
  echo "[env] acquired verify flock $VERIFY_LOCK"
else
  # macOS 无 flock 时用 mkdir 锁
  LOCKDIR="${VERIFY_LOCK}.d"
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    # stale > 2h → steal
    if [ -d "$LOCKDIR" ]; then
      age=$(( $(date +%s) - $(stat -f %m "$LOCKDIR" 2>/dev/null || stat -c %Y "$LOCKDIR" 2>/dev/null || echo 0) ))
      if [ "$age" -gt 7200 ]; then
        rmdir "$LOCKDIR" 2>/dev/null || rm -rf "$LOCKDIR"
        mkdir "$LOCKDIR" || { echo "VERIFY lock busy $LOCKDIR"; exit 75; }
      else
        echo "VERIFY locked ($LOCKDIR age=${age}s). Wait or remove stale lock."
        exit 75
      fi
    fi
  fi
  trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM
  echo "[env] acquired verify mkdir-lock $LOCKDIR"
fi

# 注意：不要全局 export KANBAN_PROFILE=dev —— 会覆盖临时 root 的 data_dir=数据，弄坏 schedule/admin 单测。
# 端到端步骤单独用 PROFILE=dev；单测依赖 materialize 写入的 数据/ 脱敏进料。
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
JOBS="${KANBAN_VERIFY_JOBS:-4}"
echo "用解释器：$PY  并行 jobs=$JOBS  KANBAN_OFFLINE=$KANBAN_OFFLINE"
# 0/5：物化脱敏 offline fixture → _golden_data + 数据/（确定性；无真实生产数据）
echo "[0/5] materialize offline fixtures → _golden_data and 数据/"
$PY scripts/materialize_offline_fixtures.py || exit 1
# 活体 manifest 契约（空 entries 允许；缺字段 entry 红）
if [ -f docs/验收证据/3_6_0/live/manifest.json ]; then
  echo "[0b/5] live manifest schema"
  $PY scripts/live_manifest.py docs/验收证据/3_6_0/live/manifest.json || exit 1
fi
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
# 任务书66·C：VM 字段 GEN 块与 pydantic 对齐
echo "[1c/5] scripts/gen_vm_ts.py --check"
$PY scripts/gen_vm_ts.py --check || exit 1
echo "[2/5] 端到端生成（offline fixture @ 数据/ + PROFILE=dev 双保险）"
# PROFILE=dev 仅限本步，避免污染后续单测临时 root
KANBAN_PROFILE=dev $PY run.py >/dev/null
echo "[3/5] 回归红线：从库算 == 从文件算（一分不差）"
KANBAN_PROFILE=dev $PY tests/regress_db_vs_files.py
echo "[4/5] 回归测试"
echo "[4a/5] 测试清单完整性"
$PY scripts/verify_test_inventory.py || exit 1
# 写库 / generate / 全局锁 / HTTP 服务态
SERIAL="
tests/test_datalayer.py
tests/test_adjust.py
tests/test_server.py
tests/test_admin_edit.py
tests/test_expense_drawer.py
tests/test_expense_views_3_7_12.py
tests/test_auth.py
tests/test_auth_sec_p4.py
tests/test_multibu.py
tests/test_update.py
tests/test_alloc_monthly.py
tests/test_detax.py
tests/test_api_v1_numbers.py
tests/test_a2_inhouse_name.py
tests/test_a5_bu_ledger_isolation.py
tests/test_serve_shell.py
tests/test_b_p5_no_view.py
tests/test_b_p4_login_static.py
tests/test_login_cache_p0.py
tests/test_ranking_monthly_a8.py
tests/test_publish_once.py
tests/test_db_atomic_rebuild.py
tests/test_money_fen.py
tests/test_db_a4a7.py
tests/test_hygiene_b.py
tests/test_budget_rates_adj_migrate.py
tests/test_task37_filters.py
tests/test_task37_expense_perm.py
tests/test_task37_fetch_banner.py
tests/test_gzip_fragments.py
tests/test_task42_final.py
tests/test_verify_test_inventory.py
tests/test_task43_nginx_mode.py
tests/test_task_2_4_3_entry.py
tests/test_task_2_5_0_login.py
tests/test_task_2_6_0_session.py
tests/test_task_2_6_1_budget_pct_display.py
tests/test_task_2_6_1_rankings_full_and_scroll.py
tests/test_task_2_6_5_profit_rank_modal.py
tests/test_frontend_arch_guards.py
tests/test_css_no_dup_classes.py
tests/test_task_2_6_9_u2_budget_yuan.py
tests/test_task_2_6_9_s5_zero_row_no_unlink.py
tests/test_task_2_6_9_s8_dead_endpoints.py
tests/test_task_2_6_10_v2_bar_w.py
tests/test_task_2_6_10_v4_no_native_alert.py
tests/test_task_2_6_10_v5_friendly_error.py
tests/test_task_2_6_10_v5_error_state_source.py
tests/test_task_2_6_5_bu_nav_overall.py
tests/test_task_2_6_5_echarts_solid_colors.py
tests/test_task_2_6_6_health_gaps.py
tests/test_task_2_6_8_t1_fallback_alert.py
tests/test_task_2_6_8_t2_expense_locator.py
tests/test_task_2_6_8_t3_adjust_idempotent.py
tests/test_task_2_6_8_t4_share_retry.py
tests/test_task_2_6_8_t5_dual_api_contract.py
tests/test_task_2_6_8_t6_history_noop.py
tests/test_task_2_6_2_mobile_layout.py
tests/test_task_2_6_3_batch_a.py
tests/test_task_2_6_3_batch_c.py
tests/test_task43_arch.py
tests/test_authz.py
tests/test_vm_contract.py
tests/test_g1_2_7_6_vm_numbers_contract.py
tests/test_g2_2_7_7_no_html_fragments.py
tests/test_g3_2_7_8_export_same_pack.py
tests/test_g4_2_7_9_no_import_render.py
tests/test_g5_2_8_0_pl_structure_contract.py
tests/test_g6_3_0_0_no_render.py
tests/test_g7_3_1_0_hygiene.py
tests/test_g8_3_2_0_structure.py
tests/test_user_stats_3_3_0.py
tests/test_config_engine.py
tests/test_backup_restore.py
tests/test_domain_reexport.py
tests/test_echarts_vm_labels.py
tests/frontend/parity/test_parity_structure.py
tests/test_task66_stage66_batch_b.py
tests/test_task_2_3_6_pl_xlsx.py
tests/test_376_readability_tokens.py
tests/test_377_desktop_logo_tokens.py
tests/test_maintenance_mode.py
tests/test_task54p11_r01_bu_nav.py
tests/test_task54p11_r02_period.py
tests/test_task54p11_r03_overlay.py
tests/test_task_2_4_0_calc.py
tests/test_g0_offline_gate.py
tests/test_g1_lifecycle_3_6_0.py
tests/test_g2_schedule_health_3_6_0.py
tests/test_g3_security_3_6_0.py
tests/test_375_credentials_no_leak.py
tests/test_375_schedule_slot_states.py
tests/test_375_admin_page_loading.py
tests/test_375_ui_components.py
tests/test_375_responsive_admin.py
tests/test_task_3_7_8_write_lock.py
tests/test_task_3_7_8_caps.py
tests/test_task_3_7_8_exceptions_false_green.py
tests/test_task_3_7_9_caps.py
tests/test_bu_daily_iso_3_7_11.py
tests/test_project_manager_3_7_13.py
tests/test_adjust_ux_3_7_13.py
tests/test_audit_3_7_14_backend.py
tests/test_ledger_cifs_3_7_15.py
tests/test_g4_key_customers_axis_3_6_0.py
tests/test_g4_key_customers_ui_3_6_0.py
tests/test_g5_boss_ui_3_6_0.py
tests/test_s13_csrf_proxy_host_port.py
tests/test_section_kc_ux_3_6_1.py
tests/test_publish_preflight_3_7_0.py
tests/test_mobile_390_p2_03.py
tests/test_lu_ui_three_20260731.py
tests/test_key_customers_3_6_2_dual_pie.py
tests/test_publish_bluegreen_3_7_3.py
tests/test_task_3_3_3_no_target_calibration_label.py
"
# 无共享进程态（或只读静态文件）
PARALLEL="
tests/test_fetch_zhiyun.py
tests/test_fin_p5_money_alloc.py
tests/test_fe001_daily_clear_scope.py
tests/test_version.py
tests/test_schedule.py
tests/test_profile.py
tests/test_admin_static.py
tests/test_admin_vue_54d.py
tests/test_no_html_in_py.py
tests/test_b_p1_contract.py
tests/test_be_write_atomicity_p2.py
tests/test_year2027.py
tests/test_split_static.py
tests/test_linux_deploy.py
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
tests/test_task57_b5_admin_hook.py
tests/test_task57_b6_domain_coverage.py
tests/test_task57_c_export_cap.py
tests/test_task58_ledger_date_range.py
tests/test_ledger_excel_filter.py
tests/test_task61_stage61.py
tests/test_task63_stage63_batch_a.py
tests/test_task63_stage63_batch_b.py
tests/test_task64_stage64.py
tests/test_task66_stage66_batch_a.py
tests/test_task66_stage66_batch_c.py
tests/test_task66_stage66_batch_d.py
tests/test_ux_stability_3_7_4.py
tests/test_ui_sales_customer_order_and_ro_filter.py
tests/test_expense_zhuangxiu_alloc.py
tests/test_task_2_2_5.py
tests/test_task_2_2_6.py
tests/test_task_2_2_7.py
tests/test_task_2_2_8.py
tests/test_task_2_2_9.py
tests/test_task_2_3_0_theme_enum.py
tests/test_task_2_3_0_neon_tokens.py
tests/test_task_2_3_0_fx_guard.py
tests/test_task_2_3_0_intro.py
tests/test_task_2_3_0_countup.py
tests/test_task_2_3_0_export_theme.py
tests/test_task_2_3_0_echarts_registry.py
tests/test_task_2_3_0_health_metrics.py
tests/test_task_2_3_1_motion.py
tests/test_task_2_3_1_neon_hud.py
tests/test_task_2_6_3_batch_b.py
tests/test_task_2_6_3_batch_d.py
tests/test_task_2_6_12_rank_modal_monthly.py
tests/test_task_2_6_13_money_ssot.py
tests/test_task_2_7_0_arch_ssot.py
tests/test_task_2_7_1_clean_target.py
tests/test_task_2_7_2_write_paths.py
tests/test_alert_store_2_6_4.py
tests/test_alert_health_ack_2_6_4.py
tests/test_failure_mode_guards.py
tests/test_task_2_6_4_bu_transition.py
tests/test_task_2_2_4.py
tests/test_stage_inventory_3_3_1_baseline.py
tests/test_task_3_3_1_alloc_int_fen.py
tests/test_task_3_3_2_refresh_honesty.py
tests/test_key_customers_3_4_0.py
tests/test_key_customers_3_4_3.py
tests/test_key_customers_3_5_0.py
tests/test_domain_coverage_54p13.py
tests/test_g0_2_7_5_tax_labels.py
tests/test_task_2_3_3_manual_rename.py
tests/test_task_2_4_0_display.py
tests/test_task_2_4_0_schema.py
tests/test_audit_3_7_14_frontend.py
tests/test_admin_ux_3_7_18.py
"
# 本轮真实结果：每文件独立 stats，避免并行写竞态（禁止只看静态 skip 位点）
RUNTIME_STATS_DIR=$(mktemp -d -t kanban_rt.XXXXXX)
run_one() {
  f="$1"
  log=$(mktemp -t kanban_t.XXXXXX)
  set +e
  $PY tests/run_test.py "$f" >"$log" 2>&1
  st=$?
  set -e
  # 解析 unittest 摘要：Ran N tests … OK/FAILED (skipped=X failures=Y errors=Z)
  summary=$($PY - "$log" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
ran = 0
m = re.search(r"Ran (\d+) tests?", text)
if m:
    ran = int(m.group(1))
skipped = failures = errors = 0
for kind, pat in (
    ("skipped", r"skipped\s*=\s*(\d+)"),
    ("failures", r"failures\s*=\s*(\d+)"),
    ("errors", r"errors\s*=\s*(\d+)"),
):
    mm = re.search(pat, text)
    if mm:
        if kind == "skipped":
            skipped = int(mm.group(1))
        elif kind == "failures":
            failures = int(mm.group(1))
        else:
            errors = int(mm.group(1))
passed = max(0, ran - skipped - failures - errors)
print(f"{ran} {passed} {failures} {errors} {skipped}")
PY
)
  safe=$(echo "$f" | tr '/.' '__')
  echo "$f $summary" >"$RUNTIME_STATS_DIR/$safe.stat"
  if [ "$st" -eq 0 ]; then
    echo "OK  $f  ($summary)"
    rm -f "$log"
    return 0
  fi
  echo "FAIL $f  ($summary)"
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
# 本轮真实 passed/failed/skipped（非静态源码位点）
AGG=$($PY - "$RUNTIME_STATS_DIR" <<'PY'
import sys
from pathlib import Path
ran = passed = failures = errors = skipped = 0
d = Path(sys.argv[1])
for p in sorted(d.glob("*.stat")):
    line = p.read_text(encoding="utf-8", errors="replace").strip()
    parts = line.split()
    if len(parts) < 6:
        continue
    try:
        ran += int(parts[-5])
        passed += int(parts[-4])
        failures += int(parts[-3])
        errors += int(parts[-2])
        skipped += int(parts[-1])
    except ValueError:
        continue
print(f"{ran} {passed} {failures} {errors} {skipped}")
PY
)
rm -rf "$RUNTIME_STATS_DIR"
set -- $AGG
RUNTIME_RAN=$1
RUNTIME_PASSED=$2
RUNTIME_FAILED=$3
RUNTIME_ERRORS=$4
RUNTIME_SKIP=$5
CRITICAL_SKIP=$RUNTIME_SKIP
echo "[result] runtime passed=$RUNTIME_PASSED failed=$RUNTIME_FAILED errors=$RUNTIME_ERRORS skipped=$RUNTIME_SKIP ran=$RUNTIME_RAN"
echo "[result] CRITICAL_SKIP=$CRITICAL_SKIP（关键 skip 必须为 0；本轮真实执行结果，非源码位点）"
# 参考：静态 skip 位点（不作为门禁绿标准）
SKIP_SITES=$($PY - <<'PY'
import re
from pathlib import Path
n = 0
for p in Path("tests").rglob("*.py"):
    text = p.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if re.search(r"@unittest\.skip|@pytest\.mark\.skip|skipUnless|skipIf|self\.skipTest\(|pytest\.skip\(", line):
            n += 1
print(n)
PY
)
echo "[skip] 测试源码 skip 位点数=$SKIP_SITES（仅参考；清单见 docs/验收证据/2_6_7/skip_inventory.md）"
if [ "${CRITICAL_SKIP:-0}" != "0" ]; then
  echo "✗ 关键 skip=$CRITICAL_SKIP ≠ 0 —— 门禁失败（禁止用 skip 换绿）"
  exit 1
fi
if [ "${RUNTIME_FAILED:-0}" != "0" ] || [ "${RUNTIME_ERRORS:-0}" != "0" ]; then
  echo "✗ runtime failed/errors 非 0"
  exit 1
fi
echo "✓ 全部通过（runtime skip=0）"
