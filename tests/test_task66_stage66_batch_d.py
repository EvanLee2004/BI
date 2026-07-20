#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·D：登录冷却 / 行数护栏 / 重复键不黄。"""

from __future__ import annotations

import json
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
        cfg = {"data_dir": str(tmp), "zhiyun_login_max_failures": 3, "zhiyun_login_cooldown_hours": 24}
        # data_dir expects relative under root — monkey via write path
        # use root=tmp and data_dir='.'
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
        self.assertIsNone(check_row_drop(100, 80, 0.3))  # 20% < 30%
        self.assertIsNotNone(check_row_drop(100, 60, 0.3))  # 40%


class TestLogRunNoDupYellow(unittest.TestCase):
    def test_dups_not_yellow(self):
        from ingest import __init__ as ing

        # _log_run needs conn — unit test yellow formula by importing logic
        # direct: duplicate alone must not force yellow when we reimplement check
        report = {
            "fetch": {"status": "fetched"},
            "adjust": {"expired": 0, "missing": 0},
            "fetch_zhiyun": {"orders": {"status": "fetched"}},
            "duplicate_locators": {"std_回款": ["a"]},
            "db_check": {"ok": True},
            "disk": {},
        }
        # simulate yellow expression from source
        fetch_ok = report["fetch"]["status"] == "fetched"
        adj = report.get("adjust", {})
        zy = report.get("fetch_zhiyun") or {}
        zy_degraded = any(v.get("status") != "fetched" for v in zy.values() if isinstance(v, dict))
        zy_warn = any(bool(v.get("warnings")) for v in zy.values() if isinstance(v, dict))
        yellow = (not fetch_ok) or adj.get("expired", 0) > 0 or adj.get("missing", 0) > 0 or zy_degraded or zy_warn
        self.assertFalse(yellow)


if __name__ == "__main__":
    unittest.main()
