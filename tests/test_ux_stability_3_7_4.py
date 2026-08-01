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


class TestFetchFreshnessIntegration(unittest.TestCase):
    """P1 端到端：有效 token 成功写 last_success；失败路径统一 data_freshness；恢复清错态。

    不得只测 classify_source_data_state 纯函数——必须走 fetch_all + 磁盘状态。
    """

    def _cfg(self, data_dir: Path) -> dict:
        return {
            "data_dir": str(data_dir),
            "files": {
                "orders": "下单.xlsx",
                "receipts": "回款记录.xlsx",
                "project_detail_stem": "项目明细",
                "inhouse": "内部译员.xlsx",
            },
            "columns": {
                "order_amount": "下单预估额/本币",
                "order_date": "下单日期",
                "receipt_amount": "回款金额",
                "receipt_date": "回款日期",
                "project_delivery_date": "整单交付日期",
                "project_revenue": "收入",
                "project_cost": "成本",
                "project_line": "产品线",
                "inhouse_amount": "金额",
                "inhouse_date": "日期",
                "inhouse_type": "类型",
            },
            "zhiyun_login_max_failures": 3,
            "zhiyun_login_short_backoff_seconds": 120,
        }

    def _write_zy_cfg(self, data_dir: Path, **extra) -> None:
        import json as _json

        body = {
            "base_url": "http://x.local",
            "username": "u",
            "password": "p",
            "app_id": "a",
            "account_id": "acc",
            "md_pss_id": "VALID_TOKEN",
            "tables": {s: {"worksheetId": f"w-{s}"} for s in ("orders", "receipts", "project_detail", "inhouse")},
        }
        body.update(extra)
        (data_dir / "智云配置.json").write_text(
            _json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )

    def _seed_local_xlsx(self, data_dir: Path) -> None:
        for name in ("下单.xlsx", "回款记录.xlsx", "项目明细.xlsx", "内部译员.xlsx"):
            (data_dir / name).write_bytes(b"PK\x03\x04OLD")

    def _patch_reachable(self, fz, ok: bool = True):
        orig = fz._server_reachable
        fz._server_reachable = lambda *a, **k: ok
        return orig

    def _patch_fetch_ok(self, fz):
        """四源均成功 fetched（不走真网络）。"""
        orig = fz.fetch_source

        def fake(cfg, source, root=None, post=None, zy=None):
            p = fz._dest_path(cfg, source, root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"PK\x03\x04NEW")
            return {"status": "fetched", "detail": f"{source} ok", "rows": 10}

        fz.fetch_source = fake
        return orig

    def _patch_fetch_fail(self, fz, *, reason: str = "HTTP 503 Service Unavailable", single: str | None = None):
        """实际抓取降级：单源或多源 local_fallback。"""
        orig = fz.fetch_source

        def fake(cfg, source, root=None, post=None, zy=None):
            if single is not None and source != single:
                p = fz._dest_path(cfg, source, root)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"PK\x03\x04NEW")
                return {"status": "fetched", "detail": f"{source} ok", "rows": 10}
            local = fz._dest_path(cfg, source, root)
            if local.exists():
                return {
                    "status": "local_fallback",
                    "detail": f"智云抓取失败（ConnectionError: {reason}），用数据目录现有文件",
                }
            return {"status": "no_source", "detail": f"智云抓取失败（{reason}），且无本地文件"}

        fz.fetch_source = fake
        return orig

    def test_valid_token_success_writes_last_success_without_relogin(self):
        """验收 1：有效 token 四源成功 → last_success_ts 刷新，不依赖 _auto_login。"""
        import json as _json
        from ingest import fetch_zhiyun as fz

        with tempfile.TemporaryDirectory(prefix="t374_ok_") as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            cfg = self._cfg(data)
            self._write_zy_cfg(data)
            old_ts = time.time() - 7200
            (data / "智云登录冷却.json").write_text(
                _json.dumps(
                    {
                        "fails": 0,
                        "last_success_ts": old_ts,
                        "last_success_at": "old",
                    }
                ),
                encoding="utf-8",
            )
            orig_r = self._patch_reachable(fz, True)
            orig_f = self._patch_fetch_ok(fz)
            orig_login = fz._auto_login
            login_calls = {"n": 0}

            def no_login(*a, **k):
                login_calls["n"] += 1
                raise AssertionError("有效 token 不应触发 _auto_login")

            fz._auto_login = no_login
            try:
                t0 = time.time()
                res = fz.fetch_all(cfg, root=root)
                self.assertTrue(
                    all(res[s]["status"] == "fetched" for s in fz.SOURCES),
                    res,
                )
                fr = res.get("_meta_freshness") or {}
                self.assertEqual(fr.get("state"), "ok", fr)
                new_ts = fz.last_fetch_success_ts(cfg, root)
                self.assertIsNotNone(new_ts)
                self.assertGreater(float(new_ts), old_ts + 1)
                self.assertGreaterEqual(float(new_ts), t0 - 1)
                self.assertEqual(login_calls["n"], 0)
                # 错态已清
                st = fz.load_login_cooldown(cfg, root)
                self.assertFalse(st.get("active"))
                self.assertEqual(int(st.get("fails") or 0), 0)
            finally:
                fz._server_reachable = orig_r
                fz.fetch_source = orig_f
                fz._auto_login = orig_login

    def test_success_then_503_within_48h_is_non_red_fresh(self):
        """验收 2：成功后网络/503 → fetch_failed_using_fresh，_log_run 非红。"""
        import json as _json
        import loaders
        import db
        from ingest import fetch_zhiyun as fz
        from ingest import _log_run

        with tempfile.TemporaryDirectory(prefix="t374_503_") as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            cfg = self._cfg(data)
            self._write_zy_cfg(data)
            self._seed_local_xlsx(data)
            orig_r = self._patch_reachable(fz, True)
            orig_f = self._patch_fetch_ok(fz)
            try:
                res_ok = fz.fetch_all(cfg, root=root)
                self.assertEqual((res_ok.get("_meta_freshness") or {}).get("state"), "ok")
                ok_ts = fz.last_fetch_success_ts(cfg, root)
                self.assertIsNotNone(ok_ts)
            finally:
                fz.fetch_source = orig_f

            orig_f2 = self._patch_fetch_fail(fz, reason="HTTP 503")
            try:
                res_fail = fz.fetch_all(cfg, root=root)
                fr = res_fail.get("_meta_freshness") or {}
                self.assertEqual(fr.get("state"), "fetch_failed_using_fresh", fr)
                self.assertFalse(fr.get("blocking"), fr)
                self.assertTrue(fr.get("viewer_ok"), fr)
                self.assertEqual(fr.get("admin_level"), "info", fr)
                # last_success 未因失败被抹掉
                self.assertEqual(fz.last_fetch_success_ts(cfg, root), ok_ts)

                # 体检灯：非红
                cfg_db = dict(loaders.load_config(ROOT))
                cfg_db["data_dir"] = str(data)
                cfg_db["db_path"] = str((data / "看板.db").resolve())
                conn = db.connect(cfg_db, data)
                try:
                    report = {
                        "fetch": {"status": "fetched"},
                        "adjust": {"expired": 0, "missing": 0},
                        "fetch_zhiyun": {
                            k: v
                            for k, v in res_fail.items()
                            if not str(k).startswith("_")
                        },
                        "data_freshness": fr,
                        "zhiyun_login_cooldown": {
                            "active": False,
                            "error_kind": "temporary",
                            "backoff_kind": "short",
                            "needs_credential_check": False,
                        },
                        "db_check": {"ok": True},
                        "disk": {},
                    }
                    lamp = _log_run(
                        conn, time.strftime("%Y-%m-%d %H:%M:%S"), "t374_503", report
                    )
                    self.assertNotEqual(lamp, "红", f"48h 内新鲜副本 503 不得硬红, got {lamp}")
                finally:
                    conn.close()
            finally:
                fz._server_reachable = orig_r
                fz.fetch_source = orig_f2

    def test_over_48h_and_no_copy_and_integrity_are_red(self):
        """验收 3：超 48h / 无副本 / 完整性失败 → 红态。"""
        import json as _json
        from ingest import fetch_zhiyun as fz

        with tempfile.TemporaryDirectory(prefix="t374_red_") as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            cfg = self._cfg(data)
            self._write_zy_cfg(data)
            self._seed_local_xlsx(data)
            # 超 48h
            stale_ts = time.time() - 50 * 3600
            (data / "智云登录冷却.json").write_text(
                _json.dumps({"last_success_ts": stale_ts, "fails": 0}),
                encoding="utf-8",
            )
            orig_r = self._patch_reachable(fz, True)
            orig_f = self._patch_fetch_fail(fz, reason="HTTP 503")
            try:
                res = fz.fetch_all(cfg, root=root)
                fr = res.get("_meta_freshness") or {}
                self.assertEqual(fr.get("state"), "stale_or_missing", fr)
                self.assertTrue(fr.get("blocking"), fr)
            finally:
                fz.fetch_source = orig_f
                fz._server_reachable = orig_r

            # 无副本
            with tempfile.TemporaryDirectory(prefix="t374_nocopy_") as td2:
                root2 = Path(td2)
                data2 = root2 / "数据"
                data2.mkdir()
                cfg2 = self._cfg(data2)
                self._write_zy_cfg(data2)
                (data2 / "智云登录冷却.json").write_text(
                    _json.dumps({"last_success_ts": time.time() - 3600, "fails": 0}),
                    encoding="utf-8",
                )
                # 不种本地 xlsx
                orig_r2 = self._patch_reachable(fz, True)
                orig_f2 = self._patch_fetch_fail(fz, reason="timeout")
                try:
                    res2 = fz.fetch_all(cfg2, root=root2)
                    fr2 = res2.get("_meta_freshness") or {}
                    self.assertEqual(fr2.get("state"), "stale_or_missing", fr2)
                    self.assertTrue(fr2.get("blocking"), fr2)
                finally:
                    fz.fetch_source = orig_f2
                    fz._server_reachable = orig_r2

            # 完整性：缺必需列 → unsafe
            with tempfile.TemporaryDirectory(prefix="t374_integ_") as td3:
                root3 = Path(td3)
                data3 = root3 / "数据"
                data3.mkdir()
                cfg3 = self._cfg(data3)
                self._write_zy_cfg(data3)
                self._seed_local_xlsx(data3)
                (data3 / "智云登录冷却.json").write_text(
                    _json.dumps({"last_success_ts": time.time() - 3600, "fails": 0}),
                    encoding="utf-8",
                )
                orig_r3 = self._patch_reachable(fz, True)
                orig_fs = fz.fetch_source

                def missing_cols(cfg, source, root=None, post=None, zy=None):
                    local = fz._dest_path(cfg, source, root)
                    if local.exists():
                        return {
                            "status": "local_fallback",
                            "detail": f"抓到 10 行但缺必需列 ['下单日期']（可能无权限/表不对），用数据目录现有文件",
                        }
                    return {"status": "no_source", "detail": "缺必需列"}

                fz.fetch_source = missing_cols
                try:
                    res3 = fz.fetch_all(cfg3, root=root3)
                    fr3 = res3.get("_meta_freshness") or {}
                    self.assertEqual(fr3.get("state"), "unsafe", fr3)
                    self.assertTrue(fr3.get("blocking"), fr3)
                    # 完整性失败不得刷新 last_success
                    self.assertAlmostEqual(
                        float(fz.last_fetch_success_ts(cfg3, root3) or 0),
                        time.time() - 3600,
                        delta=5,
                    )
                finally:
                    fz.fetch_source = orig_fs
                    fz._server_reachable = orig_r3

    def test_unreachable_login_fail_single_multi_all_emit_freshness(self):
        """验收：服务器不可达、首次登录失败、单源/多源降级 → 均有 _meta_freshness。"""
        import json as _json
        from ingest import fetch_zhiyun as fz
        from ingest import login_zhiyun

        with tempfile.TemporaryDirectory(prefix="t374_paths_") as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            cfg = self._cfg(data)
            self._write_zy_cfg(data)
            self._seed_local_xlsx(data)
            (data / "智云登录冷却.json").write_text(
                _json.dumps({"last_success_ts": time.time() - 3600, "fails": 0}),
                encoding="utf-8",
            )

            # 1) 服务器不可达
            orig_r = self._patch_reachable(fz, False)
            try:
                res = fz.fetch_all(cfg, root=root)
                fr = res.get("_meta_freshness") or {}
                self.assertIn("state", fr, f"不可达须产出 freshness: {res}")
                self.assertEqual(fr.get("state"), "fetch_failed_using_fresh", fr)
            finally:
                fz._server_reachable = orig_r

            # 2) 首次登录失败（空 token）
            self._write_zy_cfg(data, md_pss_id="")
            orig_r2 = self._patch_reachable(fz, True)
            orig_login = login_zhiyun.login

            def boom(zy, headless=True):
                raise login_zhiyun.LoginError("Connection refused")

            login_zhiyun.login = boom
            try:
                res2 = fz.fetch_all(cfg, root=root)
                fr2 = res2.get("_meta_freshness") or {}
                self.assertIn("state", fr2, f"登录失败须产出 freshness: {res2}")
                self.assertEqual(fr2.get("state"), "fetch_failed_using_fresh", fr2)
            finally:
                login_zhiyun.login = orig_login
                fz._server_reachable = orig_r2

            # 3) 单源降级
            self._write_zy_cfg(data, md_pss_id="VALID_TOKEN")
            (data / "智云登录冷却.json").write_text(
                _json.dumps({"last_success_ts": time.time() - 3600, "fails": 0}),
                encoding="utf-8",
            )
            orig_r3 = self._patch_reachable(fz, True)
            orig_f3 = self._patch_fetch_fail(fz, reason="HTTP 503", single="orders")
            try:
                res3 = fz.fetch_all(cfg, root=root)
                fr3 = res3.get("_meta_freshness") or {}
                self.assertIn("state", fr3, f"单源失败须产出 freshness: {res3}")
                self.assertEqual(fr3.get("state"), "fetch_failed_using_fresh", fr3)
                self.assertEqual(res3["orders"]["status"], "local_fallback")
                self.assertEqual(res3["receipts"]["status"], "fetched")
            finally:
                fz.fetch_source = orig_f3
                fz._server_reachable = orig_r3

            # 4) 多源降级
            orig_f4 = self._patch_fetch_fail(fz, reason="network down")
            orig_r4 = self._patch_reachable(fz, True)
            try:
                res4 = fz.fetch_all(cfg, root=root)
                fr4 = res4.get("_meta_freshness") or {}
                self.assertIn("state", fr4, f"多源失败须产出 freshness: {res4}")
                self.assertEqual(fr4.get("state"), "fetch_failed_using_fresh", fr4)
            finally:
                fz.fetch_source = orig_f4
                fz._server_reachable = orig_r4

    def test_recover_success_updates_ts_and_clears_error_state(self):
        """验收 4：恢复成功 → 更新 last_success、清退避/错态。"""
        import json as _json
        from ingest import fetch_zhiyun as fz

        with tempfile.TemporaryDirectory(prefix="t374_rec_") as td:
            root = Path(td)
            data = root / "数据"
            data.mkdir()
            cfg = self._cfg(data)
            self._write_zy_cfg(data)
            self._seed_local_xlsx(data)
            old_ts = time.time() - 10 * 3600
            (data / "智云登录冷却.json").write_text(
                _json.dumps(
                    {
                        "fails": 3,
                        "temp_fails": 3,
                        "cred_fails": 0,
                        "until_ts": time.time() + 60,
                        "active": True,
                        "error_kind": "temporary",
                        "last_error": "HTTP 503",
                        "needs_credential_check": False,
                        "last_success_ts": old_ts,
                        "last_success_at": "old",
                    }
                ),
                encoding="utf-8",
            )
            # 退避窗口外才能真抓：把 until 置过期
            st = _json.loads((data / "智云登录冷却.json").read_text(encoding="utf-8"))
            st["until_ts"] = time.time() - 1
            st["active"] = False
            (data / "智云登录冷却.json").write_text(
                _json.dumps(st), encoding="utf-8"
            )
            orig_r = self._patch_reachable(fz, True)
            orig_f = self._patch_fetch_ok(fz)
            try:
                t0 = time.time()
                res = fz.fetch_all(cfg, root=root)
                fr = res.get("_meta_freshness") or {}
                self.assertEqual(fr.get("state"), "ok", fr)
                new_ts = fz.last_fetch_success_ts(cfg, root)
                self.assertIsNotNone(new_ts)
                self.assertGreater(float(new_ts), old_ts + 1)
                self.assertGreaterEqual(float(new_ts), t0 - 1)
                cool = fz.load_login_cooldown(cfg, root)
                self.assertFalse(cool.get("active"))
                self.assertEqual(int(cool.get("fails") or 0), 0)
                self.assertEqual(int(cool.get("temp_fails") or 0), 0)
                self.assertFalse(cool.get("needs_credential_check"))
                self.assertFalse(cool.get("last_error") or "")
            finally:
                fz.fetch_source = orig_f
                fz._server_reachable = orig_r


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
