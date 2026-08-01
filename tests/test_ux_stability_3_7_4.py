#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.4 体验与稳定性：异常伪零、抓数分流/48h、帮助层与可读性契约（先红后绿）。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FE = ROOT / "frontend" / "src"
ADMIN = FE / "admin"


class TestExceptionLoadFailNotZero(unittest.TestCase):
    """P1：/api/v1/admin/exceptions 失败不得渲染 0 / 无待处理。"""

    def test_overview_has_error_state_and_retry(self):
        src = (ADMIN / "views" / "ExceptionOverview.vue").read_text(encoding="utf-8")
        self.assertIn("loadError", src)
        self.assertIn("加载失败，可重试", src)
        self.assertIn("exceptions-load-error", src)
        self.assertIn("exceptions-retry", src)
        # 失败路径不得把空对象当成功绿
        self.assertIn("loadedOk", src)
        self.assertNotRegex(
            src,
            r"catch\s*\{\s*ex\.value\s*=\s*\{\s*\}",
            "旧实现 catch 后 ex={} 会伪造成 0",
        )

    def test_admin_layout_badge_not_silent_on_error(self):
        src = (ADMIN / "layout" / "AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn("exceptionsLoadError", src)
        self.assertIn("nav-exceptions-badge", src)
        # 失败时徽标仍可见（!），不是 hidden 清零
        self.assertIn("exceptionsLoadError", src)
        self.assertIn("reviewBadgeText", src)


class TestFetchPolicyPure(unittest.TestCase):
    """抓数错误分类 + 短退避 + 48h 新鲜度（纯函数）。"""

    def test_temp_errors_not_credential(self):
        from ingest.fetch_policy import (
            ERROR_KIND_CREDENTIAL,
            ERROR_KIND_TEMPORARY,
            classify_fetch_error,
        )

        for msg in (
            "Timeout: connect timed out",
            "ConnectionError: Connection refused",
            "HTTP 503 Service Unavailable",
            "upstream 502 bad gateway",
            "token expired please re-login",
        ):
            self.assertEqual(
                classify_fetch_error(msg),
                ERROR_KIND_TEMPORARY,
                msg,
            )
        for msg in (
            "密码错误",
            "账号或密码不正确",
            "权限不足",
            "Forbidden: no permission",
            "invalid password",
        ):
            self.assertEqual(
                classify_fetch_error(msg),
                ERROR_KIND_CREDENTIAL,
                msg,
            )

    def test_temp_fails_do_not_set_credential_flag(self):
        from ingest.fetch_policy import next_backoff_state

        st = {}
        cfg = {"zhiyun_login_max_failures": 3, "zhiyun_login_short_backoff_seconds": 120}
        now = 1_700_000_000.0
        for i in range(3):
            st = next_backoff_state(st, f"Timeout {i}", cfg=cfg, now_ts=now + i)
        self.assertTrue(st.get("active"))
        self.assertFalse(st.get("needs_credential_check"))
        self.assertEqual(st.get("error_kind"), "temporary")
        # 短退避 ≤ 15min
        self.assertLessEqual(float(st["until_ts"]) - now, 900)
        self.assertGreater(float(st["until_ts"]), now)

    def test_credential_sets_flag_still_short_backoff(self):
        from ingest.fetch_policy import next_backoff_state

        cfg = {"zhiyun_login_max_failures": 2, "zhiyun_login_short_backoff_seconds": 180}
        now = 1_700_000_000.0
        st = next_backoff_state({}, "密码错误", cfg=cfg, now_ts=now)
        st = next_backoff_state(st, "密码错误", cfg=cfg, now_ts=now + 1)
        self.assertTrue(st.get("needs_credential_check"))
        self.assertEqual(st.get("error_kind"), "credential")
        self.assertTrue(st.get("active"))
        self.assertLessEqual(float(st["until_ts"]) - now, 900)

    def test_old_24h_config_capped_to_short(self):
        from ingest.fetch_policy import short_backoff_seconds

        sec = short_backoff_seconds({"zhiyun_login_cooldown_hours": 24})
        self.assertLessEqual(sec, 900)
        self.assertGreaterEqual(sec, 30)

    def test_freshness_48h_non_blocking(self):
        from ingest.fetch_policy import classify_source_data_state

        now = 1_700_000_000.0
        # 本次失败 + 12h 前成功 + 有副本 → 非阻断
        r = classify_source_data_state(
            fetch_ok=False,
            last_success_ts=now - 12 * 3600,
            now_ts=now,
            has_local_copy=True,
        )
        self.assertEqual(r["state"], "fetch_failed_using_fresh")
        self.assertFalse(r["blocking"])
        self.assertTrue(r["viewer_ok"])
        self.assertEqual(r["admin_level"], "info")

        # 超过 48h → 红
        r2 = classify_source_data_state(
            fetch_ok=False,
            last_success_ts=now - 50 * 3600,
            now_ts=now,
            has_local_copy=True,
        )
        self.assertEqual(r2["state"], "stale_or_missing")
        self.assertTrue(r2["blocking"])

        # 无副本 → 红
        r3 = classify_source_data_state(
            fetch_ok=False,
            last_success_ts=now - 1 * 3600,
            now_ts=now,
            has_local_copy=False,
        )
        self.assertTrue(r3["blocking"])

        # 完整性失败 → unsafe
        r4 = classify_source_data_state(
            fetch_ok=True,
            integrity_ok=False,
            now_ts=now,
        )
        self.assertEqual(r4["state"], "unsafe")
        self.assertTrue(r4["blocking"])

        # 缺列 / 低于 min_rows / 阻断 0 行
        for kw in (
            {"missing_columns": True},
            {"below_min_rows": True},
            {"zero_rows_blocking": True},
        ):
            rx = classify_source_data_state(fetch_ok=False, now_ts=now, **kw)
            self.assertEqual(rx["state"], "unsafe", kw)

    def test_register_login_failure_disk_short(self):
        from ingest import fetch_zhiyun as fz

        tmp = Path(tempfile.mkdtemp())
        cfg = {
            "data_dir": ".",
            "zhiyun_login_max_failures": 3,
            "zhiyun_login_short_backoff_seconds": 200,
        }
        for i in range(3):
            st = fz.register_login_failure(cfg, tmp, f"ConnectionError: reset {i}")
        self.assertTrue(st.get("active"))
        self.assertFalse(st.get("needs_credential_check"))
        self.assertLess(float(st["until_ts"]) - time.time(), 3600)

    def test_log_run_fresh_temp_fail_not_hard_red(self):
        """临时失败 + fetch_failed_using_fresh → 不硬红。"""
        import loaders
        import db
        from ingest import _log_run

        tmp = Path(tempfile.mkdtemp(prefix="t374_"))
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = str(tmp)
        cfg["db_path"] = str((tmp / "看板.db").resolve())
        conn = db.connect(cfg, tmp)
        try:
            report = {
                "fetch": {"status": "fetched"},
                "adjust": {"expired": 0, "missing": 0},
                "fetch_zhiyun": {
                    "orders": {"status": "local_fallback", "login_cooldown": True},
                    "receipts": {"status": "local_fallback"},
                    "project_detail": {"status": "local_fallback"},
                    "inhouse": {"status": "local_fallback"},
                },
                "zhiyun_login_cooldown": {
                    "active": True,
                    "error_kind": "temporary",
                    "backoff_kind": "short",
                    "needs_credential_check": False,
                },
                "data_freshness": {
                    "state": "fetch_failed_using_fresh",
                    "message": "本次抓取失败，正在使用仍新鲜的最后成功数据",
                },
                "db_check": {"ok": True},
                "disk": {},
            }
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            result = _log_run(conn, now, "test374", report)
            self.assertNotEqual(result, "红", f"新鲜副本临时失败不应硬红, got {result}")
        finally:
            conn.close()


class TestHelpPopoverContract(unittest.TestCase):
    def test_help_popover_component_exists(self):
        src = (FE / "components/base/HelpPopover.vue").read_text(encoding="utf-8")
        self.assertIn("Teleport", src)
        self.assertIn("DataModal", src)
        self.assertIn("aria-label", src)
        self.assertIn("Escape", src)
        self.assertIn("Enter", src)
        # 仅解释性；无「加载失败」类状态文案作唯一读数
        self.assertNotIn("无待处理", src)

    def test_key_customers_uses_help_popover(self):
        panel = (FE / "components/key-customers/KeyCustomersPanel.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("HelpPopover", panel)
        self.assertIn("kc-help", panel)
        self.assertIn("helpLines", panel)

    def test_summary_actionable_near(self):
        s = (FE / "components/key-customers/KeyCustomersSummary.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("openNear", s)
        self.assertIn("kc-near-entry", s)
        self.assertIn("当前无临界晋级名单可进入", s)


class TestMobileAndChromeCopy(unittest.TestCase):
    def test_kpi_narrow_not_two_col_word_break(self):
        bridge = (FE / "vendor/scifi-kit/scifi-bridge.css").read_text(encoding="utf-8")
        # 520 以下单列
        self.assertIn("max-width: 520px", bridge)
        self.assertIn("word-break: keep-all", bridge)
        # 禁止窄屏仍写死两列五卡
        block_520 = ""
        if "@media (max-width: 520px)" in bridge:
            i = bridge.index("@media (max-width: 520px)")
            block_520 = bridge[i : i + 400]
        self.assertIn("minmax(0, 1fr)", block_520)
        self.assertNotIn("repeat(2, minmax(0, 1fr))", block_520)

    def test_topbar_data_updated_label(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("数据更新至", app)
        self.assertIn("topbarDataDate", app)
        self.assertIn("data-freshness-strip", app)

    def test_daily_scope_hint(self):
        src = (FE / "components/DailyQuery.vue").read_text(encoding="utf-8")
        self.assertIn("仅影响下方排行", src)
        self.assertIn("daily-scope-hint", src)

    def test_export_scope_label(self):
        src = (FE / "components/TopBarActions.vue").read_text(encoding="utf-8")
        self.assertIn("exportScopeLabel", src)
        self.assertIn("导出当前整体视图", src)
        self.assertIn("导出本 BU", src)

    def test_admin_nav_buttons(self):
        src = (ADMIN / "layout" / "AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn('type="button"', src)
        self.assertIn("nav-group-see", src)
        self.assertIn("nav-group-review", src)
        # 分组导航必须是 button，不是裸 div.gtab 点击
        self.assertNotRegex(
            src,
            r'<div class="gtab"[^>]*@click="showGroup',
        )


if __name__ == "__main__":
    unittest.main()
