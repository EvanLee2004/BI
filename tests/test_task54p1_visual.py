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
        """54.4：默认零动画；breathScatter 恒 null；无 effectScatter 系列体。"""
        src = (FE / "chart-fx.ts").read_text(encoding="utf-8")
        self.assertIn("prefersReducedMotion", src)
        self.assertIn("animation: false", src)
        self.assertIn("breathScatterSeries", src)
        # 兼容桩保留但恒 return null，源码不得再声明 effectScatter 系列体
        self.assertNotIn("type: 'effectScatter'", src)
        self.assertNotIn("showEffectOn:", src)
        self.assertIn("return null", src)
        self.assertIn("dataLabelStyle", src)
        self.assertIn("fontSize: 11", src)
        self.assertIn("pieEmphasis", src)
        self.assertIn("shadowBlur: 0", src)

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
    def test_star_static_no_twinkle(self):
        """54.4·A6：星空静态，无 twinkle 动画与 filter:brightness。"""
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("body::before", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertNotIn("@keyframes scifiStarTwinkle", css)
        # 静态星点：animation: none
        self.assertIn("animation: none", css)
        self.assertNotIn("filter: brightness", css)


class Test54p4PerfA(unittest.TestCase):
    """任务书54.4 批次 A 性能收口守卫。"""

    def test_echarts_host_lazy_and_no_anim(self):
        src = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")
        self.assertIn("IntersectionObserver", src)
        self.assertIn("animation: false", src)
        self.assertIn("renderer", src)
        self.assertIn("ResizeObserver", src)

    def test_panel_no_backdrop_blur(self):
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("backdrop-filter: none", css)
        self.assertIn("rgba(8, 16, 32, 0.92)", css)

    def test_no_breath_calls_in_charts(self):
        for name in ("TrendChart.vue", "ExpenseTrend.vue", "ReceiptsCard.vue"):
            src = (FE / "components" / name).read_text(encoding="utf-8")
            self.assertNotIn("breathScatterSeries", src, name)
            self.assertNotIn("effectScatter", src, name)


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
        # 任务书54.3·B-01：查询结果不再由 DailyQuery 自渲染（会挤走回款总图/版面跳动），
        # 改为写入 store（setDaily），由 RankingsDual「原位」用同一 dualRankBarOption 渲染——
        # 「默认排名与区间结果同用一套 option、样式顺序一致」的不变式仍成立，只是收敛到一处。
        self.assertIn("setDaily", daily)
        self.assertIn("dualRankBarOption", rank)
        self.assertIn("dailyDual", rank)
        self.assertIn("rank-chart-host", rank)


class TestTask54p2DeepSpace(unittest.TestCase):
    """54.2 深空指挥舱：图例/金线/双柱/KPI 结构守卫。"""

    def test_donut_labels_off_legend_row(self):
        src = (FE / "components" / "ExpenseSection.vue").read_text(encoding="utf-8")
        self.assertIn("label: { show: false }", src)
        self.assertIn("ev-legend-row", src)

    def test_trend_gold_margin(self):
        src = (FE / "components" / "TrendChart.vue").read_text(encoding="utf-8")
        self.assertIn("#fbbf24", src)

    def test_receipts_dual_bars(self):
        src = (FE / "components" / "ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn("name: '下单'", src)
        self.assertIn("name: '回款'", src)
        self.assertIn("type: 'bar'", src)
        self.assertIn("padYearMonths", src)

    def test_kpi_five_and_bridge_kpi(self):
        kpi = (FE / "components" / "KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn("kpi-grid kpi-5", kpi)
        css = (FE / "vendor" / "scifi-kit" / "scifi-bridge.css").read_text(encoding="utf-8")
        self.assertIn("scifi-panel.kpi-card", css)
        self.assertIn("54.2", css)

    def test_no_backend_html_in_vue_components(self):
        for p in (FE / "components").rglob("*.vue"):
            src = p.read_text(encoding="utf-8")
            self.assertNotIn("v-html", src, p.name)

    def test_rank_axis_no_truncate(self):
        """V6：排名行名禁止 overflow truncate（54.2 补刀）。"""
        src = (FE / "dual-rank-option.ts").read_text(encoding="utf-8")
        self.assertNotIn("overflow: 'truncate'", src)
        self.assertNotIn('overflow: "truncate"', src)
        self.assertIn("overflow: 'break'", src)
        self.assertIn("nameColW", src)


if __name__ == "__main__":
    unittest.main()
