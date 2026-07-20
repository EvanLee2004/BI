#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·D：登录冷却 / 行数护栏 / 重复键不黄（真调 _log_run）。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestLoginCooldown(unittest.TestCase):
    def test_register_and_active(self):
        from ingest import fetch_zhiyun as fz

        tmp = Path(tempfile.mkdtemp())
        cfg = {"data_dir": ".", "zhiyun_login_max_failures": 3, "zhiyun_login_cooldown_hours": 24}
        for i in range(3):
            st = fz.register_login_failure(cfg, tmp, f"err{i}")
        self.assertTrue(st.get("until_ts", 0) > time.time())
        act = fz.login_cooldown_active(cfg, tmp)
        self.assertIsNotNone(act)
        self.assertTrue(act.get("active"))
        fz.clear_login_cooldown(cfg, tmp)
        self.assertIsNone(fz.login_cooldown_active(cfg, tmp))


class TestRowDrop(unittest.TestCase):
    def test_check_row_drop(self):
        from ingest.fetch_zhiyun import check_row_drop

        self.assertIsNone(check_row_drop(None, 10, 0.3))
        self.assertIsNone(check_row_drop(100, 80, 0.3))
        self.assertIsNotNone(check_row_drop(100, 60, 0.3))


class TestLogRunNoDupYellow(unittest.TestCase):
    def test_dups_not_yellow_via_log_run(self):
        """真调 ingest._log_run：仅有定位键重复 → 结果绿 + info 含重复文案。"""
        import loaders
        from ingest import _log_run

        import db

        tmp = Path(tempfile.mkdtemp(prefix="t66d_"))
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = str(tmp)
        cfg["db_path"] = str((tmp / "看板.db").resolve())
        # 空库也有 meta 表
        conn = db.connect(cfg, tmp)
        try:
            report = {
                "fetch": {"status": "fetched"},
                "adjust": {"expired": 0, "missing": 0, "applied": 0},
                "fetch_zhiyun": {
                    "orders": {"status": "fetched"},
                    "receipts": {"status": "fetched"},
                    "project_detail": {"status": "fetched"},
                    "inhouse": {"status": "fetched"},
                },
                "duplicate_locators": {"std_回款": ["k1", "k2", "k3"]},
                "db_check": {"ok": True},
                "disk": {},
            }
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            result = _log_run(conn, now, "test66d", report)
            self.assertEqual(result, "绿", f"dups alone must not yellow/red, got {result}")
            info = report.get("info") or []
            self.assertTrue(any("定位键重复" in str(x) for x in info), info)
            # 对照：local_fallback 仍黄
            report2 = {
                "fetch": {"status": "local_fallback"},
                "adjust": {"expired": 0, "missing": 0},
                "fetch_zhiyun": {"orders": {"status": "fetched"}},
                "duplicate_locators": {},
                "db_check": {"ok": True},
                "disk": {},
            }
            r2 = _log_run(conn, now, "test66d2", report2)
            self.assertEqual(r2, "黄")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
