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
    "components/ExpenseHeatmap.vue",
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
        self.assertIn("BuNav", app)
        self.assertTrue((FE / "components" / "BuNav.vue").is_file())

    def test_client_uses_vm_api(self):
        client = (FE / "api" / "client.ts").read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/cockpit", client)

    def test_rankings_dual_binds_rankings_view_not_profit(self):
        """板块四必须绑 rankings_view；禁止再误绑 profit_rank_body（板块三）。"""
        src = (FE / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        # 去掉注释再断言，避免文档字面量误伤
        code = re.sub(r"/\*[\s\S]*?\*/", "", src)
        code = re.sub(r"//.*", "", code)
        self.assertIn("rankings_view", code)
        self.assertIn('data-source="rankings_view"', src)
        self.assertIn("order_disp", code)
        self.assertIn("receipt_disp", code)
        self.assertNotIn("profit_rank_body", code)
        # 任务书51·B8 类型化后：store.vm?.rankings?.rankings_view（旧写法 rk?.rankings_view 亦兼容）
        self.assertTrue(
            "rk?.rankings_view" in code or "rankings?.rankings_view" in code,
            "板块四须绑定 rankings.rankings_view",
        )
        # 板块三：结构化 profit_rank_by_period（任务书50·B 替代 HTML body）
        pr = (FE / "components" / "ProfitStructure.vue").read_text(encoding="utf-8")
        self.assertTrue(
            "profit_rank_by_period" in pr or "profit_rank_body" in pr,
            "板块三须绑 profit_rank_by_period 或兼容 profit_rank_body",
        )
        self.assertNotIn("rankings_view", pr.replace("profit_rank", ""))

    def test_app_login_guard_not_collapsed(self):
        """App.vue 登录守卫不得写成 pathname==('/login'||…) 形式。"""
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("path === '/login'", app)
        self.assertIn("path.startsWith('/admin')", app)
        self.assertNotIn("==('/login'", app)
        dist = ROOT / "frontend" / "dist" / "assets"
        js_files = list(dist.glob("index-*.js")) if dist.is_dir() else []
        self.assertTrue(js_files, "dist 须重建")
        blob = js_files[0].read_text(encoding="utf-8", errors="ignore")
        # 禁止打包后的错误折叠：pathname==("/login"||...
        self.assertNotIn('pathname==("/login"', blob)
        self.assertNotIn("pathname==('/login'", blob)


class TestVmLegacyDisplayParity(unittest.TestCase):
    """同一 summary：VM 与 legacy views 显示串逐字段相等。"""

    @classmethod
    def setUpClass(cls):
        if not (ROOT / "_golden_data").exists():
            raise unittest.SkipTest("缺 _golden_data")
        cls.summary, cls.cfg = _build_summary()

    def test_kpi_pl_expense_strings_equal(self):
        """vue 默认：VM 不带 legacy HTML body；结构化 cards/table 仍有。
        legacy env 下 body 与 views HTML 对齐。
        """
        import os
        import api_v1
        import viewmodels

        mode = viewmodels.frontend_mode(self.cfg)
        views = api_v1.build_cockpit_views(self.summary, self.cfg)
        vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
        if mode == "vue":
            self.assertEqual(vm.kpi.body_by_period or {}, {})
            self.assertEqual(vm.pl.body_by_period or {}, {})
            self.assertTrue(vm.kpi.cards_by_period)
            self.assertTrue(vm.pl.table_by_period)
            return
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
            # 任务书52·F-4：裁到最后有数月，系列与 totals 等长、≤12
            n = len(vm.expense.area_labels)
            self.assertGreaterEqual(n, 1)
            self.assertLessEqual(n, 12)
            self.assertEqual(len(vm.expense.area_totals_disp), n)


class TestParityAllowFile(unittest.TestCase):
    def test_allow_registered(self):
        self.assertIn("allow", ALLOW)
        self.assertTrue(ALLOW["allow"])


if __name__ == "__main__":
    unittest.main()
