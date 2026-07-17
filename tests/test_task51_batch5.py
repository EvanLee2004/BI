#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B5/B6/B7：ledger 导出、周期月区间、轴刻度 meta。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import viewmodels  # noqa: E402
from viewmodels import packers  # noqa: E402

FAKE = ROOT / "_golden_data"


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
        # 找一个月 key
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
        self.assertIn('/api/v1/vm/ledger/export', src)
        self.assertIn("force_whitelist=True", src)


if __name__ == "__main__":
    unittest.main()
