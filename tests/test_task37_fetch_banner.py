#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书37·B9/B10：抓数降级黄横幅 + 未来日期体检黄。"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import profit  # noqa: E402
import server  # noqa: E402


class TestFetchFallbackBanners(unittest.TestCase):
    def test_all_fetched_empty(self):
        cfg = loaders.load_config(ROOT)
        b = server.build_fetch_fallback_banners(
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

    def test_local_fallback_banner_text(self):
        tmp = Path(tempfile.mkdtemp())
        ddir = tmp / "数据"
        ddir.mkdir()
        led = ddir / "收单台账.xlsx"
        led.write_bytes(b"PK\x03\x04fake")  # exist for mtime
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["files"] = dict(cfg.get("files") or {})
        cfg["files"]["ledger"] = "收单台账.xlsx"
        b = server.build_fetch_fallback_banners(
            {
                "fetch": {"status": "local_fallback", "detail": "共享不可达"},
                "fetch_zhiyun": {
                    "orders": {"status": "local_fallback", "detail": "离线"},
                    "receipts": {"status": "fetched"},
                },
            },
            cfg,
            tmp,
        )
        texts = [x["text"] for x in b]
        self.assertTrue(any("收单台账" in t and "今日未抓到" in t and "沿用" in t for t in texts), texts)
        self.assertTrue(any("智云·下单" in t for t in texts), texts)
        self.assertFalse(any("回款" in t and "今日未抓到" in t for t in texts))
        # 月日标签
        self.assertTrue(any("月" in x["as_of"] and "日" in x["as_of"] for x in b if x["source"] == "收单台账"))

    def test_health_api_exposes_banners(self):
        from fastapi.testclient import TestClient
        import accounts
        import db

        tmp = Path(tempfile.mkdtemp())
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
        # 写一条含 local_fallback 的运行日志
        import json

        body = {
            "fetch": {"status": "local_fallback", "detail": "x"},
            "fetch_zhiyun": {"orders": {"status": "local_fallback", "detail": "y"}},
        }
        conn.execute(
            "INSERT INTO meta_运行日志(时间,触发方式,结果,体检JSON) VALUES(?,?,?,?)",
            ("2026-07-16 10:00:00", "manual", "黄", json.dumps(body, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
        app = server.create_app(cfg, root=tmp)
        c = TestClient(app)
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("fetch_banners", d)
        self.assertGreaterEqual(len(d["fetch_banners"]), 1)
        self.assertTrue(any("今日未抓到" in (x.get("text") or "") for x in d["fetch_banners"]))

    def test_ui_hooks(self):
        self.assertIn("fetchBanner", (ROOT / "static/templates/render/dashboard_body.html").read_text(encoding="utf-8"))
        self.assertIn("fetch_banners", (ROOT / "static/js/cockpit.js").read_text(encoding="utf-8"))
        self.assertIn("paintFetchBanners", (ROOT / "static/admin/admin.js").read_text(encoding="utf-8"))
        self.assertIn("fetchBanner", (ROOT / "static/admin/admin.html").read_text(encoding="utf-8"))


class TestFutureDateWarnings(unittest.TestCase):
    def test_future_inhouse_in_health(self):
        today = datetime.date(2026, 7, 16)
        cc = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额/本币",
            "order_date": "下单日期",
            "order_amount": "下单预估额",
            "receipt_date": "到账日期",
            "receipt_amount": "到账金额",
            "inhouse_date": "任务提交日期",
            "inhouse_amount": "结算金额",
            "inhouse_type": "译员类型-资源库",
        }
        # 内部译员 10 月任务
        inhouse = [
            {"任务提交日期": "2026-10-05", "结算金额": "100", "译员类型-资源库": "IN-HOUSE"},
            {"任务提交日期": "2026-10-12", "结算金额": "200", "译员类型-资源库": "IN-HOUSE"},
            {"任务提交日期": "2026-06-01", "结算金额": "50", "译员类型-资源库": "IN-HOUSE"},
        ]
        cfg = {"inhouse_keyword": "IN-HOUSE"}
        year_key = "2026年"
        P = {year_key: {"revenue_net": 0, "expense": {"total": 0}, "label": "2026年"}}
        health = profit._data_health(
            cfg,
            cc,
            [],
            [],
            [],
            inhouse,
            [],
            2026,
            {"含税金额": 0, "收单日期": 1, "收单月份": 2},
            P,
            today,
            {"expense": {"count": 0, "amount": 0}},
            [],
            {},
        )
        joined = "\n".join(health["warnings"])
        self.assertIn("内部译员", joined)
        self.assertIn("2 行", joined)
        self.assertIn("2026-10", joined)
        self.assertTrue(health["ok"] is False or len(health["warnings"]) > 0)

    def test_no_future_no_extra_warn(self):
        today = datetime.date(2026, 12, 31)
        n, s = profit._scan_future_dates_dict(
            [{"d": "2026-06-01"}], "d", today
        )
        self.assertEqual(n, 0)
        self.assertEqual(s, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
