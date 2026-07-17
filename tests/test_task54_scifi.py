#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54·B/C：SciFi kit 落地守卫 + 费用堆叠柱图型 + 无第二 UI 库。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestSciFiVendor54(unittest.TestCase):
    def test_vendor_dir_has_css_license(self):
        kit = FE / "vendor" / "scifi-kit"
        self.assertTrue((kit / "DynamicSciFiDashboardKit.css").is_file())
        self.assertTrue((kit / "LICENSE").is_file())
        self.assertTrue((kit / "scifi-bridge.css").is_file())
        css = (kit / "DynamicSciFiDashboardKit.css").read_text(encoding="utf-8")
        self.assertIn("MIT", css[:400] + (kit / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn("--dsdk-", css)

    def test_main_imports_vendor_not_cdn(self):
        main = (FE / "main.ts").read_text(encoding="utf-8")
        self.assertIn("vendor/scifi-kit/DynamicSciFiDashboardKit.css", main)
        self.assertIn("scifi-bridge.css", main)
        blob = "\n".join(
            p.read_text(encoding="utf-8")
            for p in FE.rglob("*")
            if p.suffix in {".ts", ".vue", ".css", ".html"} and "node_modules" not in str(p)
        )
        for bad in ("cdn.jsdelivr", "unpkg.com", "vuetify", "element-plus", "nuxt", "@element-plus"):
            self.assertNotIn(bad, blob.lower() if bad.islower() else blob)

    def test_scifi_panel_component(self):
        p = FE / "components" / "SciFiPanel.vue"
        self.assertTrue(p.is_file())
        src = p.read_text(encoding="utf-8")
        self.assertIn("dsdk-panel", src)
        self.assertIn("dsdk-panel-header", src)

    def test_echarts_theme_reads_dsdk_vars(self):
        src = (FE / "echarts-theme.ts").read_text(encoding="utf-8")
        self.assertIn("--dsdk-accent-color-secondary", src)
        self.assertIn("--dsdk-text-color", src)


class TestExpenseStackedBar54(unittest.TestCase):
    def test_expense_trend_is_stacked_bar_not_area(self):
        src = (FE / "components" / "ExpenseTrend.vue").read_text(encoding="utf-8")
        self.assertIn("type: 'bar'", src)
        self.assertNotIn("areaStyle", src)
        self.assertIn("stack: 'total'", src)
        self.assertIn("area_totals_disp", src)
        self.assertIn("area_labels", src)
        self.assertIn("堆叠柱", src)
        # 禁止误用 kit 图表画金额
        self.assertNotIn("CanvasGraphPanel", src)
        self.assertNotIn("TrueCanvasGraph", src)


class TestCardsUseSciFiShell(unittest.TestCase):
    def test_key_cards_import_scifi_panel(self):
        names = (
            "KpiCards.vue",
            "TrendChart.vue",
            "PLTable.vue",
            "ExpenseSection.vue",
            "ExpenseTrend.vue",
            "ReceiptsCard.vue",
            "RankingsDual.vue",
            "ProfitStructure.vue",
            "DailyQuery.vue",
            "LedgerTable.vue",
            "LoginView.vue",
        )
        for n in names:
            src = (FE / "components" / n).read_text(encoding="utf-8")
            self.assertIn("SciFiPanel", src, n)


if __name__ == "__main__":
    unittest.main()
