#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S6.C：ECharts 按需注册覆盖全部 series / 组件。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
HOST = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")


class TestEchartsRegistry230(unittest.TestCase):
    def test_core_import_not_full(self):
        self.assertIn("echarts/core", HOST)
        self.assertNotIn("from 'echarts'", HOST.replace("echarts/core", "").replace("echarts/charts", "").replace("echarts/components", "").replace("echarts/features", "").replace("echarts/renderers", ""))

    def test_both_renderers(self):
        self.assertIn("CanvasRenderer", HOST)
        self.assertIn("SVGRenderer", HOST)

    def test_series_types_registered(self):
        # 全仓 vue 里 series type
        series = set()
        for p in FE.rglob("*.vue"):
            t = p.read_text(encoding="utf-8")
            for m in re.finditer(r"type:\s*['\"](\w+)['\"]", t):
                series.add(m.group(1))
        # 业务图：bar line pie heatmap（其它 type 可能是 component）
        needed = {"bar", "line", "pie", "heatmap"} & series
        reg_map = {
            "bar": "BarChart",
            "line": "LineChart",
            "pie": "PieChart",
            "heatmap": "HeatmapChart",
        }
        for s in needed:
            self.assertIn(reg_map[s], HOST, f"series {s} not registered")

    def test_use_call_present(self):
        self.assertIn("echarts.use(", HOST)
        for name in (
            "GridComponent",
            "TooltipComponent",
            "LegendComponent",
            "TitleComponent",
            "VisualMapComponent",
            "GraphicComponent",
            "AxisPointerComponent",
        ):
            self.assertIn(name, HOST, name)


if __name__ == "__main__":
    unittest.main()
