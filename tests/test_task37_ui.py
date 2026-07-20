#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书37 A1–A6 UI 收口守卫：提示条删除、双血条图例、50/50、周期标注、sticky、H1 行序。"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 任务书65：legacy admin.css/js 已删；UI 守卫改扫 theme + Vue/templates
ADMIN_HTML = ROOT / "static" / "admin" / "admin.html"  # 重定向页
THEME = ROOT / "static" / "css" / "theme.css"
DUAL_CARD = ROOT / "static" / "templates" / "render" / "dual_card.html"
RANKINGS_JS = ROOT / "static" / "js" / "assemble" / "rankings.js"
RC_TOTALS = ROOT / "static" / "templates" / "render" / "rc_totals.html"


class TestA1RemoveRefreshNote(unittest.TestCase):
    def test_no_auto_refresh_banner(self):
        html = ADMIN_HTML.read_text(encoding="utf-8")
        self.assertNotIn("改数后此看板会自动刷新（秒级重算）", html)
        golden = ROOT / "golden" / "admin_baseline.html"
        if golden.exists():
            self.assertNotIn("改数后此看板会自动刷新（秒级重算）", golden.read_text(encoding="utf-8"))


class TestA2DualBarLegend(unittest.TestCase):
    def test_legend_in_python_template(self):
        t = DUAL_CARD.read_text(encoding="utf-8")
        self.assertIn("上·紫=下单", t)
        self.assertIn("下·青=回款", t)
        self.assertIn("dual-legend", t)

    def test_legend_in_js_assembler_and_monthly(self):
        js = RANKINGS_JS.read_text(encoding="utf-8")
        self.assertIn("上·紫=下单", js)
        self.assertIn("下·青=回款", js)
        # 月度弹窗路径也有图例
        self.assertIn("paintMonthlyFromAttr", js)
        self.assertGreaterEqual(js.count("上·紫=下单"), 2)

    def test_legend_css(self):
        css = THEME.read_text(encoding="utf-8")
        self.assertIn(".dual-legend", css)
        self.assertIn(".dual-leg", css)


class TestA3DualGridEqual(unittest.TestCase):
    def test_dual_grid_sales_cust_ratio(self):
        """任务书41·C：按销售 45% / 按客户 55%（原 50/50）。"""
        css = THEME.read_text(encoding="utf-8")
        self.assertIn(".dual-grid", css)
        self.assertRegex(css, r"\.dual-grid\s*\{[^}]*0\.45fr")
        self.assertRegex(css, r"\.dual-grid\s*\{[^}]*0\.55fr")


class TestA4PeriodOnTotals(unittest.TestCase):
    def test_template_has_period_slot(self):
        t = RC_TOTALS.read_text(encoding="utf-8")
        self.assertIn("period_label", t)
        self.assertIn("rc-period", t)

    def test_render_injects_period(self):
        import render

        html = render._receipt_insight_totals(1_000_000, 500_000, period_label="2026年")
        self.assertIn("2026年", html)
        self.assertIn("总下单", html)
        self.assertIn("总回款", html)
        self.assertIn("rc-period", html)

    def test_period_from_period_key_path(self):
        import render

        p = {"orders": 100.0, "receipts": 50.0, "revenue_gross": 80.0, "label": "2026年Q1"}
        html = render._receipt_insight_from_period(p, period_label="2026年Q1")
        self.assertIn("2026年Q1", html)


class TestA5StickyManual(unittest.TestCase):
    def test_manual_view_exists_in_vue(self):
        """任务书65：legacy admin sticky CSS 已随单轨删除；人工填写在 Vue ManualView。"""
        manual = (ROOT / "frontend" / "src" / "admin" / "views" / "ManualView.vue").read_text(encoding="utf-8")
        self.assertTrue(manual.strip())
        self.assertIn("人工", manual + (ROOT / "frontend" / "src" / "admin" / "layout" / "AdminLayout.vue").read_text(encoding="utf-8"))


class TestA6BudgetH1First(unittest.TestCase):
    def test_h1_rows_before_year_rows(self):
        """Vue admin/utils.ts BUDGET_METRICS 行序：H1 在前、年目标在后。"""
        js = (ROOT / "frontend" / "src" / "admin" / "utils.ts").read_text(encoding="utf-8")
        m = re.search(r"export const BUDGET_METRICS = \[([\s\S]*?)\] as const", js)
        self.assertIsNotNone(m, "BUDGET_METRICS not found")
        block = m.group(1)
        keys = re.findall(r"k:\s*'([^']+)'", block)
        self.assertEqual(
            keys,
            [
                "下单H1目标",
                "回款H1目标",
                "毛利率H1目标",
                "税前利润率H1目标",
                "下单年预算",
                "回款年预算",
                "毛利率年目标",
                "税前利润率年目标",
            ],
            f"展示行序应 H1 在上年目标在下，得 {keys}",
        )
        self.assertIn("下单年预算", keys)
        self.assertIn("回款年预算", keys)


class TestTask37InRunVerify(unittest.TestCase):
    """四个 test_task37_*.py 必须登记进 run_verify，避免一键验证漏跑。"""

    def test_listed_in_run_verify(self):
        sh = (ROOT / "tests" / "run_verify.sh").read_text(encoding="utf-8")
        for name in (
            "tests/test_task37_ui.py",
            "tests/test_task37_filters.py",
            "tests/test_task37_expense_perm.py",
            "tests/test_task37_fetch_banner.py",
        ):
            self.assertIn(name, sh, f"{name} 未写入 run_verify SERIAL/PARALLEL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
