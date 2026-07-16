#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·3：DOM/显示串 parity。

1) 组件清单与 dist
2) 铁律2：无金额四则
3) 真实路径：同一 summary → VM 显示串与 build_cockpit_views / extract_numbers 全等
4) 板块顺序：Vue App 源含 一..五 与「收入与毛利结构」
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "frontend" / "src"
sys.path.insert(0, str(ROOT / "src"))

REQUIRED = [
    "api/client.ts",
    "stores/cockpit.ts",
    "components/KpiCards.vue",
    "components/TrendChart.vue",
    "components/PLTable.vue",
    "components/ExpenseSection.vue",
    "components/RankingsDual.vue",
    "components/ReceiptsCard.vue",
    "components/DailyQuery.vue",
    "components/LedgerTable.vue",
    "components/ExpenseTrend.vue",
    "components/PeriodPicker.vue",
    "components/ThemeToggle.vue",
    "components/LoginView.vue",
    "components/BUPage.vue",
    "components/ProfitStructure.vue",
    "echarts-theme.ts",
]

ALLOW = json.loads((ROOT / "tests/frontend/parity/parity_allow.json").read_text(encoding="utf-8"))


def _build_summary():
    import core
    import db
    import ingest
    import loaders

    cfg = loaders.load_config(ROOT)
    cfg = dict(cfg)
    cfg["data_dir"] = "_golden_data"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        ingest.build_std_db(
            cfg, today.year, conn=conn, today=today, trigger="parity", archive_backups=False
        )
        return core.summary_from_conn(cfg, conn, today), cfg
    finally:
        conn.close()


class TestFrontendScaffold(unittest.TestCase):
    def test_required_components_exist(self):
        for rel in REQUIRED:
            self.assertTrue((FE / rel).is_file(), f"缺组件 {rel}")

    def test_dist_built(self):
        self.assertTrue((ROOT / "frontend" / "dist" / "index.html").is_file())

    def test_no_amount_math_in_vue(self):
        bad = re.compile(r"(/\s*10000|/\s*100\b|\*\s*0\.0)")
        for p in FE.rglob("*"):
            if p.suffix not in (".vue", ".ts") or not p.is_file():
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s.startswith("//") or s.startswith("*"):
                    continue
                if bad.search(line):
                    self.fail(f"疑似金额运算 {p}:{i}: {s}")

    def test_app_section_order(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        i1 = app.index("基本情况")
        i2 = app.index("经营利润")
        i3 = app.index("收入与毛利结构")
        i4 = app.index("下单与回款")
        i5 = app.index("费用明细")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        self.assertLess(i3, i4)
        self.assertLess(i4, i5)
        self.assertIn("ProfitStructure", app)

    def test_client_uses_vm_api(self):
        client = (FE / "api" / "client.ts").read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/cockpit", client)


class TestVmLegacyDisplayParity(unittest.TestCase):
    """同一 summary：VM 与 legacy views 显示串逐字段相等。"""

    @classmethod
    def setUpClass(cls):
        if not (ROOT / "_golden_data").exists():
            raise unittest.SkipTest("缺 _golden_data")
        cls.summary, cls.cfg = _build_summary()

    def test_kpi_pl_expense_strings_equal(self):
        import api_v1
        import viewmodels

        views = api_v1.build_cockpit_views(self.summary, self.cfg)
        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        self.assertEqual(vm.kpi.body_by_period, views.get("kpi_body") or {})
        self.assertEqual(vm.pl.body_by_period, views.get("pl_body") or {})
        self.assertEqual(vm.expense.body_by_period, views.get("donut_body") or {})
        self.assertEqual(vm.rankings.profit_rank_body, views.get("profit_rank_body") or {})
        self.assertEqual(vm.period_bar, views.get("period_bar") or "")

    def test_numbers_equal_extract(self):
        import api_v1
        import viewmodels

        exp = api_v1.extract_numbers(self.summary)
        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        self.assertEqual(vm.numbers["meta_year_key"], exp["meta_year_key"])
        self.assertEqual(vm.numbers["period_keys"], exp["period_keys"])
        for pk in list(exp["periods"])[:5]:
            self.assertEqual(
                vm.numbers["periods"][pk].get("pretax_profit"),
                exp["periods"][pk].get("pretax_profit"),
            )

    def test_chart_labels_match_series_length(self):
        import viewmodels

        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        self.assertEqual(len(vm.trend.labels), len(vm.trend.revenue_disp))
        self.assertEqual(len(vm.trend.labels), len(vm.trend.margin_pct_disp))
        if vm.expense.area_labels:
            self.assertEqual(len(vm.expense.area_labels), 12)
            self.assertEqual(len(vm.expense.area_totals_disp), 12)


class TestParityAllowFile(unittest.TestCase):
    def test_allow_registered(self):
        self.assertIn("allow", ALLOW)
        self.assertTrue(ALLOW["allow"])


if __name__ == "__main__":
    unittest.main()
