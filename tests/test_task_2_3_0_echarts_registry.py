#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S6.C / 2.6.3·D1：ECharts 按需注册（实现已迁到 echarts-loader 异步加载）。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
LOADER = (FE / "echarts-loader.ts").read_text(encoding="utf-8")
HOST = (FE / "components" / "charts" / "EchartsHost.vue").read_text(encoding="utf-8")


class TestEchartsRegistry230(unittest.TestCase):
    def test_core_import_not_full(self):
        # 2.6.3：静态 import 在 loader；Host 只动态 loadEcharts
        self.assertIn("echarts/core", LOADER)
        self.assertIn("loadEcharts", HOST)
        blob = LOADER + HOST
        self.assertNotIn(
            "from 'echarts'",
            blob.replace("echarts/core", "")
            .replace("echarts/charts", "")
            .replace("echarts/components", "")
            .replace("echarts/features", "")
            .replace("echarts/renderers", ""),
        )

    def test_both_renderers(self):
        self.assertIn("CanvasRenderer", LOADER)
        self.assertIn("SVGRenderer", LOADER)

    def test_series_types_registered(self):
        series = set()
        for p in FE.rglob("*.vue"):
            t = p.read_text(encoding="utf-8")
            for m in re.finditer(r"type:\s*['\"](\w+)['\"]", t):
                series.add(m.group(1))
        needed = {"bar", "line", "pie", "heatmap"} & series
        reg_map = {
            "bar": "BarChart",
            "line": "LineChart",
            "pie": "PieChart",
            "heatmap": "HeatmapChart",
        }
        for s in needed:
            self.assertIn(reg_map[s], LOADER, f"series {s} not registered")

    def test_use_call_present(self):
        self.assertIn("echarts.use(", LOADER)
        for name in (
            "GridComponent",
            "TooltipComponent",
            "LegendComponent",
            "TitleComponent",
            "VisualMapComponent",
            "GraphicComponent",
            "AxisPointerComponent",
        ):
            self.assertIn(name, LOADER, name)


if __name__ == "__main__":
    unittest.main()
