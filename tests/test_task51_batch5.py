#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B5/B6/B7：ledger 导出、周期月区间、轴刻度 meta。

含 TestClient 真路径：GET /api/v1/vm/ledger/export（admin + 整体看端）。
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
import viewmodels  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"
XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TestBatch5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg
        cls.vm = viewmodels.build_cockpit_vm(cls.summary, cfg)
        cls.yk = cls.vm.year_key

    def test_period_months_on_ledger(self):
        pm = self.vm.ledger.period_months or {}
        self.assertIn(self.yk, pm)
        self.assertEqual(pm[self.yk].get("month_from"), "")
        for k, v in pm.items():
            if "月" in k and "Q" not in k and "-" not in k.split("年")[-1]:
                self.assertRegex(v.get("month_from") or "", r"^\d{4}-\d{2}$")
                self.assertEqual(v.get("month_from"), v.get("month_to"))
                break

    def test_axis_meta_fields(self):
        self.assertTrue(self.vm.trend.y_axis_ticks)
        self.assertGreaterEqual(self.vm.trend.y_axis_max, self.vm.trend.y_axis_min)
        meta = packers.pack_axis_meta([100.0, 200.0, 50.0])
        self.assertIn("interval", meta)
        self.assertEqual(meta["ticks"], packers.pack_axis_ticks([100.0, 200.0, 50.0]))

    def test_frontend_no_csv_diy_no_nearest(self):
        led = (ROOT / "frontend" / "src" / "components" / "LedgerTable.vue").read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/ledger/export", led)
        self.assertNotIn("text/csv", led)
        self.assertNotIn(".match(/", led)
        for name in ("TrendChart.vue", "ReceiptsCard.vue"):
            src = (ROOT / "frontend" / "src" / "components" / name).read_text(encoding="utf-8")
            self.assertNotIn("bestD", src)
            self.assertIn("tickLabel", src)

    def test_export_route_exists(self):
        src = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/ledger/export", src)
        self.assertIn("force_whitelist=True", src)


class TestLedgerExportRuntime(unittest.TestCase):
    """GET /api/v1/vm/ledger/export 真路径：200 + xlsx + 白名单列（admin / 整体）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = loaders.load_config(ROOT)
        self.cfg = dict(cfg)
        self.cfg["data_dir"] = str(self.tmp / "数据")
        (self.tmp / "数据").mkdir(parents=True)
        accounts.seed_defaults(self.cfg, self.tmp)
        conn = db.connect(self.cfg, self.tmp)
        try:
            import db_write

            db_write.insert_std_records(
                conn,
                "std_费用明细",
                [
                    {
                        "定位键": "export-seed-51",
                        "收单月份": "2026-03",
                        "收单日期": "2026-03-15",
                        "含税金额": 12.5,
                        "业务BU": "数据",
                        "对应报表大类": "管理费用",
                        "预算明细费用类型": "办公费",
                        "预算归属部门": "财务",
                        "事项": "导出测一行",
                        "提单人": "隐藏提单人",
                        "提单人部门": "隐藏部门",
                        "业务员": "测试员",
                        "配音费合同号": "隐合同",
                        "归属月": "2026-03",
                        "原值_归属月": "2026-03",
                    }
                ],
            )
            conn.commit()
        finally:
            conn.close()
        self.app = server.create_app(self.cfg, self.tmp)
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)

    def _login(self, account: str, password: str):
        r = self.client.post("/api/v1/login", json={"account": account, "password": password})
        self.assertEqual(r.status_code, 200, r.text[:300])
        return self.client

    def _assert_xlsx_whitelist(self, resp, *, expected_cols: list[str], label: str):
        self.assertEqual(resp.status_code, 200, f"{label} status {resp.status_code} {resp.text[:200]}")
        ct = (resp.headers.get("content-type") or "").lower()
        self.assertTrue(
            XLSX_CT in ct or "spreadsheetml" in ct or "octet-stream" in ct,
            f"{label} content-type={ct!r}",
        )
        body = resp.content
        self.assertGreater(len(body), 100, f"{label} empty body")
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        try:
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        self.assertTrue(rows, f"{label} sheet empty")
        header = [str(c) if c is not None else "" for c in rows[0]]
        for forbidden in db.VIEW_EXPENSE_HIDDEN:
            self.assertNotIn(forbidden, header, f"{label} leaked hidden col {forbidden}")
        for c in header:
            self.assertIn(c, expected_cols, f"{label} col {c!r} not in whitelist")
        # 与 GET /api/v1/vm/ledger 列序一致
        self.assertEqual(header, expected_cols, f"{label} header must match VIEW whitelist order")
        # 至少能读到种入事项（允许筛选后仍有数据行）
        flat = " ".join(str(x) for row in rows[1:] for x in (row or ()) if x is not None)
        self.assertIn("导出测", flat, f"{label} seeded row missing in xlsx")

    def test_admin_export_xlsx_whitelist(self):
        c = self._login(accounts.MASTER_ACCOUNT, accounts.DEFAULT_ADMIN_PW)
        r_led = c.get("/api/v1/vm/ledger", params={"page": 1, "page_size": 20})
        self.assertEqual(r_led.status_code, 200)
        led_cols = list(r_led.json().get("columns") or [])
        self.assertEqual(led_cols, list(db.VIEW_EXPENSE_COLUMNS))

        r = c.get("/api/v1/vm/ledger/export")
        self._assert_xlsx_whitelist(r, expected_cols=list(db.VIEW_EXPENSE_COLUMNS), label="admin export")
        # 与 ledger JSON 列集合一致
        self.assertEqual(list(db.VIEW_EXPENSE_COLUMNS), led_cols)

    def test_main_view_export_xlsx_whitelist(self):
        c = self._login("overall", accounts.DEFAULT_VIEW_PW)
        r_led = c.get("/api/v1/vm/ledger", params={"page": 1, "page_size": 20})
        self.assertEqual(r_led.status_code, 200)
        led_cols = list(r_led.json().get("columns") or [])
        self.assertEqual(led_cols, list(db.VIEW_EXPENSE_COLUMNS))
        self.assertEqual((r_led.json().get("audience") or ""), "view")

        r = c.get("/api/v1/vm/ledger/export")
        self._assert_xlsx_whitelist(r, expected_cols=list(db.VIEW_EXPENSE_COLUMNS), label="main export")

    def test_anon_export_401(self):
        r = self.client.get("/api/v1/vm/ledger/export")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
