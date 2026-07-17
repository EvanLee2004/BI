#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书54.1：V1–V8 视觉整改结构守卫（纯前端，禁新库/禁碰后端算账）。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestV1SectionContrast(unittest.TestCase):
    def test_sec_n_high_contrast_in_bridge(self):
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn(".sec-n", css)
        self.assertIn("#04101c", css)
        self.assertIn("clip-path", css)
        self.assertIn(".sec-t", css)


class TestV2KpiFiveCols(unittest.TestCase):
    def test_kpi_cards_use_kpi5(self):
        src = (FE / "components" / "KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn("kpi-grid kpi-5", src)
        self.assertIn("kpi-5", src)


class TestV3PlFill(unittest.TestCase):
    def test_pl_card_flex_fill_in_bridge(self):
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn(".scifi-panel.pl-card", css)
        self.assertIn("justify-content: space-between", css)
        self.assertIn("flex: 1 1 auto", css)


class TestV4V6ChartFx(unittest.TestCase):
    def test_chart_fx_module(self):
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("prefersReducedMotion", src)
        self.assertIn("breathScatterSeries", src)
        self.assertIn("effectScatter", src)
        self.assertIn("dataLabelStyle", src)
        self.assertIn("fontSize: 11", src)
        self.assertIn("pieEmphasis", src)

    def test_charts_import_fx(self):
        for name in (
            "TrendChart.vue",
            "ExpenseTrend.vue",
            "ExpenseSection.vue",
            "ReceiptsCard.vue",
        ):
            src = (FE / "components" / name).read_text(encoding="utf-8")
            self.assertIn("chart-fx", src, name)
        # RankingsDual 经 dual-rank-option 间接用 chart-fx
        rank = (FE / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("dual-rank-option", rank)
        self.assertIn("chart-fx", (FE / "dual-rank-option.ts").read_text(encoding="utf-8"))


class TestV5StarBg(unittest.TestCase):
    def test_star_twinkle_css(self):
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("scifiStarTwinkle", css)
        self.assertIn("body::before", css)
        self.assertIn("prefers-reduced-motion", css)


class TestV8ResizeObserver(unittest.TestCase):
    def test_echarts_host_resize_observer(self):
        src = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")
        self.assertIn("ResizeObserver", src)
        self.assertIn("chart?.resize()", src)
        self.assertIn("ro.disconnect", src)


class TestNoNewDeps(unittest.TestCase):
    def test_package_json_no_new_libs(self):
        pkg = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        for bad in ("gsap", "animejs", "three", "particles", "lottie", "framer", "motion"):
            self.assertNotIn(bad, pkg.lower())


class TestLiveReviewFixes54p1(unittest.TestCase):
    """人审补刀：抽屉横排 / 12月轴 / 双榜共用 option。"""

    def test_drawer_two_col_css(self):
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: minmax(10em, 1fr) auto", css)
        self.assertIn("writing-mode: horizontal-tb", css)

    def test_pad_year_months_helper(self):
        src = (FE / "chart-months.ts").read_text(encoding="utf-8")
        self.assertIn("padYearMonths", src)
        self.assertIn("axisMaxCover", src)

    def test_dual_rank_shared(self):
        src = (FE / "dual-rank-option.ts").read_text(encoding="utf-8")
        self.assertIn("dualRankBarOption", src)
        daily = (FE / "components" / "DailyQuery.vue").read_text(encoding="utf-8")
        rank = (FE / "components" / "RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("dualRankBarOption", daily)
        self.assertIn("dualRankBarOption", rank)
        self.assertIn("rank-chart-host", rank)


if __name__ == "__main__":
    unittest.main()
