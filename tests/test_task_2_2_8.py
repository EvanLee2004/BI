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
from audit_diff import (  # noqa: E402
    apply_business_health_yellow,
    build_fetch_fallback_banners,
    _run_reasons,
)
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

    def test_all_fetched_handfill_missing_lifts_yellow(self):
        """DoD⑧：管道全 fetched 绿 + 手填缺月业务警 → health 合成后黄（不盖红）。"""
        # 管道本身无业务黄 → 绿
        rep = _base_report()
        self.assertEqual(_log_run(self.conn, self.now, "t", rep), "绿")
        # 真实 shipped helper：手填缺抬绿→黄
        warn = "手填缺 3 个月未录（2026-01、2026-02、2026-03）：缺月按 0 计，请当月补填"
        result, reasons = apply_business_health_yellow(
            "绿",
            [],
            n_unassigned=0,
            health_warnings=[warn],
        )
        self.assertEqual(result, "黄")
        self.assertTrue(any("手填缺" in r for r in reasons), reasons)
        # 红不被盖
        r2, _ = apply_business_health_yellow(
            "红",
            ["收单台账本次未抓到"],
            n_unassigned=0,
            health_warnings=[warn],
        )
        self.assertEqual(r2, "红")
        # 未归属仍抬黄
        r3, rs3 = apply_business_health_yellow("绿", [], n_unassigned=2, health_warnings=[])
        self.assertEqual(r3, "黄")
        self.assertTrue(any("未归属" in r for r in rs3), rs3)


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
        parts = [int(x) for x in ver.split(".")[:3]]
        self.assertGreaterEqual(parts, [2, 2, 8], ver)
        self.assertIn("2.2.8", (ROOT / "src/version.py").read_text(encoding="utf-8"))
        self.assertIn("## [2.2.8]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        blob = (ROOT / "src/version.py").read_text(encoding="utf-8")
        # 最新产品条目应含方案 B 语义关键词
        self.assertIn("本次未抓到", blob)
        self.assertIn("口径", blob)


class TestHealthApiHandfillYellow(unittest.TestCase):
    """真实 /api/health 路径：管道绿 + health.warnings 手填缺 → result 黄。"""

    def test_api_health_green_run_handfill_warn_becomes_yellow(self):
        import json
        import tempfile

        from fastapi.testclient import TestClient

        import accounts
        import server

        tmp = Path(tempfile.mkdtemp(prefix="t228h_"))
        (tmp / "数据").mkdir()
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["db_path"] = "数据/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cfg,
            tmp,
            [{"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"}],
        )
        conn = db.connect(cfg, tmp)
        body = {
            "fetch": {"status": "fetched"},
            "fetch_zhiyun": {
                "orders": {"status": "fetched"},
                "receipts": {"status": "fetched"},
                "project_detail": {"status": "fetched"},
                "inhouse": {"status": "fetched"},
            },
            "adjust": {"expired": 0, "missing": 0},
            "db_check": {"ok": True},
        }
        conn.execute(
            "INSERT INTO meta_运行日志(时间,触发方式,结果,体检JSON) VALUES(?,?,?,?)",
            ("2026-07-22 12:00:00", "manual", "绿", json.dumps(body, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
        # 管道绿，但 summary 体检含手填缺（真实 profit 产出形态）
        server._state["summary"] = {
            "meta": {
                "health": {
                    "sources": [],
                    "warnings": [
                        "手填缺 2 个月未录（2026-05、2026-06）：缺月按 0 计，请当月补填"
                    ],
                    "ok": False,
                },
                "unassigned": {"count": 0},
            }
        }
        app = server.create_app(cfg, root=tmp)
        c = TestClient(app)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["result"], "黄", d)
        self.assertTrue(any("手填缺" in (x or "") for x in d.get("run_reasons") or []), d)
        self.assertTrue(any("手填缺" in (x or "") for x in d.get("warnings") or []), d)


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
