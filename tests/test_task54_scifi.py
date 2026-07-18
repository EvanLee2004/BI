#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54·B/C：SciFi kit 落地守卫；任务书54.1·V7 费用多系列折线 + 无第二 UI 库。"""
from __future__ import annotations

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
        """看端 boot-cockpit 引 SciFi kit；管理端可引 Element Plus（MIT·54.4·D）；禁 CDN。"""
        boot = (FE / "boot-cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("vendor/scifi-kit/DynamicSciFiDashboardKit.css", boot)
        self.assertIn("scifi-bridge.css", boot)
        main = (FE / "main.ts").read_text(encoding="utf-8")
        self.assertIn("boot-cockpit", main)
        self.assertIn("admin/bootstrap", main)
        # 看端路径（排除 admin/）不得出现 element-plus / CDN
        cockpit_blob = "\n".join(
            p.read_text(encoding="utf-8")
            for p in FE.rglob("*")
            if p.suffix in {".ts", ".vue", ".css", ".html"}
            and "node_modules" not in str(p)
            and "/admin/" not in str(p).replace("\\", "/")
            and not str(p).endswith("main.ts")
        )
        for bad in ("cdn.jsdelivr", "unpkg.com", "vuetify", "element-plus", "nuxt", "@element-plus"):
            self.assertNotIn(bad, cockpit_blob.lower())
        # 管理端入口确有 EP（动态 import）
        admin_boot = (FE / "admin" / "bootstrap.ts").read_text(encoding="utf-8")
        self.assertIn("element-plus", admin_boot)

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


class TestExpenseMultiLine54p1(unittest.TestCase):
    """54.1·V7：费用月度 = 多系列发光折线（仍用 area_* 数据，零口径变化）。"""

    def test_expense_trend_is_multi_line_not_stack_bar(self):
        src = (FE / "components" / "ExpenseTrend.vue").read_text(encoding="utf-8")
        self.assertIn("type: 'line'", src)
        self.assertNotIn("areaStyle", src)
        self.assertNotIn("stack: 'total'", src)
        self.assertNotIn("堆叠柱", src)
        self.assertIn("area_totals_disp", src)
        self.assertIn("area_labels", src)
        self.assertIn("area_series", src)
        self.assertIn("多系列折线", src)
        # 54.4：删呼吸特效，保留折线样式
        self.assertNotIn("breathScatterSeries", src)
        self.assertIn("lineGlowStyle", src)
        self.assertNotIn("var(--ink", src)
        self.assertNotIn("CanvasGraphPanel", src)
        self.assertNotIn("TrueCanvasGraph", src)

    def test_theme_ink_helper_exported(self):
        src = (FE / "echarts-theme.ts").read_text(encoding="utf-8")
        self.assertIn("export function themeInkColor", src)


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
