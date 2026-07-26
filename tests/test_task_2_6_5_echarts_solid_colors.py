# -*- coding: utf-8 -*-
"""2.6.5 补丁：ECharts option 不得传入 CSS var() 字符串（canvas addColorStop 会 SyntaxError）。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
# 会进 ECharts option 的业务组件
CHART_VUES = [
    "components/TrendChart.vue",
    "components/ReceiptsCard.vue",
    "components/ExpenseSection.vue",
    "components/ExpenseHeatmap.vue",
]
# 禁止在这些文件里出现传给 canvas 的字面量 var(--
VAR_LITERAL = re.compile(r"""['\"]var\(--[^'\"]+\)['\"]""")


class TestEchartsSolidColors(unittest.TestCase):
    def test_no_css_var_string_literals_in_chart_vues(self):
        hits = []
        for rel in CHART_VUES:
            p = FE / rel
            text = p.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if VAR_LITERAL.search(line):
                    hits.append(f"{rel}:{i}:{line.strip()[:100]}")
        self.assertEqual(
            hits,
            [],
            "ECharts 组件禁止字面量 'var(--x)'（须 cssColor() 解析实色）:\n" + "\n".join(hits),
        )

    def test_css_color_util_never_returns_var(self):
        src = (FE / "utils" / "cssColor.ts").read_text(encoding="utf-8")
        self.assertIn("export function cssColor", src)
        self.assertIn("startsWith('var(')", src)
        self.assertIn("FALLBACKS", src)
        # 各图卡 import cssColor
        for rel in CHART_VUES:
            text = (FE / rel).read_text(encoding="utf-8")
            self.assertIn("cssColor", text, rel)


if __name__ == "__main__":
    unittest.main()
