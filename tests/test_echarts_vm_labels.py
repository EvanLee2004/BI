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
        # 费用面积：任务书52·F-4 裁到最后有数月（≤12），系列与 labels 等长
        n = len(vm.expense.area_labels)
        self.assertGreaterEqual(n, 1)
        self.assertLessEqual(n, 12)
        for s in vm.expense.area_series:
            self.assertEqual(len(s["data"]), n)
            self.assertEqual(len(s["data_disp"]), n)
            for a, d in zip(s["data"], s["data_disp"]):
                if a == 0:
                    self.assertEqual(d, "0.0")

    def test_y_axis_ticks_backend(self):
        """任务书50·C：Y 轴刻度显示串由后端下发，禁止 000,000。"""
        import viewmodels

        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        self.assertTrue(vm.trend.y_axis_ticks)
        for t in vm.trend.y_axis_ticks:
            self.assertIn("label", t)
            self.assertNotIn("000,000", t["label"])
        self.assertEqual([t["label"] for t in vm.trend.y_axis_ticks], vm.trend.y_axis_labels)

    def test_donut_center_not_debug(self):
        import viewmodels

        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        yk = vm.year_key
        c = (vm.expense.donut_center_by_period or {}).get(yk) or {}
        self.assertEqual(c.get("title"), "期间费用")
        blob = str(c)
        self.assertNotIn("total 50", blob)
        self.assertNotIn("50.0%", blob)

    def test_donut_items_no_total_and_pct_sums_100(self):
        """环形扇区不得混入合计键 total（曾把各类占比稀释一半）；pct 合计≈100%。"""
        import viewmodels

        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        for pk, items in (vm.expense.donut_by_period or {}).items():
            names = [i.get("name") for i in items]
            self.assertNotIn("total", names, f"{pk} 扇区混入 total")
            if items:
                s = sum(float(str(i.get("pct_disp", "0")).rstrip("%")) for i in items)
                self.assertAlmostEqual(s, 100.0, delta=0.5, msg=f"{pk} 占比合计 {s}")

    def test_ui_no_echarts_tech_label(self):
        for name in ("TrendChart.vue", "ExpenseSection.vue", "ReceiptsCard.vue", "RankingsDual.vue"):
            text = (FE / "components" / name).read_text(encoding="utf-8")
            # 卡头不得把技术栈名当用户文案
            self.assertNotIn("ECharts</span>", text, name)
            self.assertNotIn("环形 · ECharts", text, name)

    def test_rankings_use_echarts_bars(self):
        text = (FE / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("EchartsHost", text)
        self.assertIn("type: 'bar'", text)


if __name__ == "__main__":
    unittest.main()

