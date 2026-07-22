#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.2.8：抓数行数容差 + 灯色方案 B + 横幅「本次未抓到」+ 台账未配置 share。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
from audit_diff import build_fetch_fallback_banners, _run_reasons  # noqa: E402
from ingest import _log_run  # noqa: E402
from ingest import fetch as fetch_mod  # noqa: E402
from ingest import fetch_zhiyun as fz  # noqa: E402


def _base_report(**kw):
    r = {
        "fetch": {"status": "fetched", "detail": "ok"},
        "adjust": {"expired": 0, "missing": 0, "applied": 0},
        "fetch_zhiyun": {
            "orders": {"status": "fetched"},
            "receipts": {"status": "fetched"},
            "project_detail": {"status": "fetched"},
            "inhouse": {"status": "fetched"},
        },
        "duplicate_locators": {},
        "db_check": {"ok": True},
        "disk": {},
    }
    r.update(kw)
    return r


class TestRowTotalTolerance(unittest.TestCase):
    def test_production_case_23498_23501(self):
        total, actual = 23498, 23501
        rows = [{"i": n} for n in range(actual)]

        def post(path, body):
            d = {"data": rows if body["pageIndex"] == 1 else []}
            if body["pageIndex"] == 1:
                d["count"] = total
            return {"data": d}

        self.assertEqual(len(fz.fetch_all_rows(post, "ws", "app")), actual)

    def test_equal_ok(self):
        def post(path, body):
            return {"data": {"data": [{"i": 1}] * 100, "count": 100}}

        self.assertEqual(len(fz.fetch_all_rows(post, "ws", "app")), 100)


class TestLightColorSchemeB(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t228_"))
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = str(self.tmp)
        self.cfg["db_path"] = str((self.tmp / "看板.db").resolve())
        self.conn = db.connect(self.cfg, self.tmp)
        self.now = time.strftime("%Y-%m-%d %H:%M:%S")

    def tearDown(self):
        self.conn.close()

    def test_all_fetched_green(self):
        rep = _base_report()
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "绿")

    def test_one_local_fallback_red(self):
        rep = _base_report(
            fetch_zhiyun={
                "orders": {"status": "fetched"},
                "receipts": {"status": "local_fallback", "detail": "行数对账失败"},
                "project_detail": {"status": "fetched"},
                "inhouse": {"status": "fetched"},
            }
        )
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "红")

    def test_fetched_with_manual_adjust_yellow(self):
        rep = _base_report(adjust={"expired": 1, "missing": 0, "applied": 0})
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "黄")

    def test_fetched_with_row_drop_warning_yellow(self):
        rep = _base_report(
            fetch_zhiyun={
                "orders": {"status": "fetched", "warnings": ["行数骤降：上次成功 100 → 本次 50"]},
                "receipts": {"status": "fetched"},
                "project_detail": {"status": "fetched"},
                "inhouse": {"status": "fetched"},
            }
        )
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "黄")

    def test_zhiyun_auto_off_no_zy_key_not_red(self):
        """zhiyun_auto_fetch 关 → 管道无 fetch_zhiyun 键，不因智云未抓而红。"""
        rep = _base_report()
        rep.pop("fetch_zhiyun")
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "绿")

    def test_login_cooldown_red(self):
        rep = _base_report(zhiyun_login_cooldown={"active": True, "until": "x"})
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "红")

    def test_ledger_fallback_red(self):
        rep = _base_report(fetch={"status": "local_fallback", "detail": "共享不可达"})
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "红")

    def test_dup_locator_info_not_yellow(self):
        rep = _base_report(duplicate_locators={"std_回款": ["a", "b"]})
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "绿")
        self.assertTrue(any("定位键重复" in str(x) for x in (rep.get("info") or [])))

    def test_same_name_control_info_not_yellow(self):
        """同名控件只 info 上浮，不进 warnings → 不黄。"""
        rep = _base_report(
            fetch_zhiyun={
                "orders": {
                    "status": "fetched",
                    "info": ["表模板「下单日期」同名控件 2 个，已按规则取首个有值"],
                },
                "receipts": {"status": "fetched"},
                "project_detail": {"status": "fetched"},
                "inhouse": {"status": "fetched"},
            }
        )
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "绿")
        self.assertTrue(any("同名控件" in str(x) for x in (rep.get("info") or [])))
        rs = _run_reasons(rep)
        self.assertFalse(any("同名控件" in r for r in rs), rs)


class TestBanners228(unittest.TestCase):
    def test_banner_text_本次未抓到(self):
        tmp = Path(tempfile.mkdtemp())
        ddir = tmp / "数据"
        ddir.mkdir()
        (ddir / "收单台账.xlsx").write_bytes(b"PK\x03\x04fake")
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["files"] = dict(cfg.get("files") or {})
        cfg["files"]["ledger"] = "收单台账.xlsx"
        b = build_fetch_fallback_banners(
            {
                "fetch": {"status": "local_fallback", "detail": "共享不可达"},
                "fetch_zhiyun": {"orders": {"status": "fetched"}},
            },
            cfg,
            tmp,
        )
        texts = [x["text"] for x in b]
        self.assertTrue(any("本次未抓到" in t for t in texts), texts)
        self.assertFalse(any("今日未抓到" in t for t in texts))
        self.assertTrue(any("沿用本地文件" in t for t in texts), texts)

    def test_all_fetched_empty(self):
        cfg = loaders.load_config(ROOT)
        b = build_fetch_fallback_banners(
            {
                "fetch": {"status": "fetched"},
                "fetch_zhiyun": {
                    "orders": {"status": "fetched"},
                    "receipts": {"status": "fetched"},
                },
            },
            cfg,
            ROOT,
        )
        self.assertEqual(b, [])

    def test_no_source_banner(self):
        cfg = loaders.load_config(ROOT)
        b = build_fetch_fallback_banners(
            {"fetch": {"status": "no_source", "detail": "无本地"}, "fetch_zhiyun": {}},
            cfg,
            ROOT,
        )
        self.assertTrue(any("且无本地可用文件" in x["text"] for x in b), b)


class TestVersion228(unittest.TestCase):
    def test_version_files(self):
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(ver, "2.2.8")
        self.assertIn("2.2.8", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.8]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        blob = (ROOT / "src/version.py").read_text(encoding="utf-8")
        # 最新产品条目应含方案 B 语义关键词
        self.assertIn("本次未抓到", blob)
        self.assertIn("口径", blob)


class TestLedgerNoShareNotRed(unittest.TestCase):
    def test_unconfigured_share_with_local_is_fetched(self):
        tmp = Path(tempfile.mkdtemp())
        ddir = tmp / "数据"
        ddir.mkdir()
        led = ddir / "收单台账.xlsx"
        led.write_bytes(b"PK\x03\x04x")
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["ledger_share_path"] = ""
        cfg["files"] = dict(cfg.get("files") or {})
        cfg["files"]["ledger"] = "收单台账.xlsx"
        r = fetch_mod.fetch_ledger(cfg, tmp)
        self.assertEqual(r["status"], "fetched", r)
        self.assertIn("未配置", r["detail"])

        # 管道灯色不红
        conn = db.connect(
            {**cfg, "db_path": str((tmp / "t.db").resolve())},
            tmp,
        )
        try:
            rep = _base_report(fetch=r)
            rep.pop("fetch_zhiyun")  # auto off
            self.assertEqual(_log_run(conn, time.strftime("%Y-%m-%d %H:%M:%S"), "t", rep), "绿")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
