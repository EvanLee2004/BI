#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·3B：ECharts 数字标签与 VM 显示串一致（结构断言）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FE = ROOT / "frontend" / "src"


def _build_summary():
    import core
    import db
    import ingest
    import loaders

    cfg = dict(loaders.load_config(ROOT))
    cfg["data_dir"] = "_golden_data"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        ingest.build_std_db(
            cfg, today.year, conn=conn, today=today, trigger="echarts", archive_backups=False
        )
        return core.summary_from_conn(cfg, conn, today), cfg
    finally:
        conn.close()


class TestEchartsVmLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "_golden_data").exists():
            raise unittest.SkipTest("缺 golden")
        cls.summary, cls.cfg = _build_summary()

    def test_components_use_echarts_host(self):
        for name in ("TrendChart.vue", "ExpenseTrend.vue", "ExpenseSection.vue", "ReceiptsCard.vue"):
            text = (FE / "components" / name).read_text(encoding="utf-8")
            self.assertIn("EchartsHost", text, name)
            self.assertIn("option", text)

    def test_theme_file(self):
        t = (FE / "echarts-theme.ts").read_text(encoding="utf-8")
        self.assertIn("--blue", t)
        self.assertIn("kanbanTheme", t)

    def test_vm_series_label_parity(self):
        import viewmodels

        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        # 趋势：每个点都有显示串
        for i, lab in enumerate(vm.trend.labels):
            self.assertTrue(lab)
            self.assertEqual(len(vm.trend.revenue_disp[i]) > 0, True)
            self.assertIn("%", vm.trend.margin_pct_disp[i])
        # 费用面积 12 月
        self.assertEqual(len(vm.expense.area_labels), 12)
        for s in vm.expense.area_series:
            self.assertEqual(len(s["data"]), 12)
            self.assertEqual(len(s["data_disp"]), 12)
            for a, d in zip(s["data"], s["data_disp"]):
                if a == 0:
                    self.assertEqual(d, "0.0")


if __name__ == "__main__":
    unittest.main()
