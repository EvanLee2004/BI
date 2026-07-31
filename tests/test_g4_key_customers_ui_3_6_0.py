# -*- coding: utf-8 -*-
"""3.6.0 小修：重点客户五系列样式、无 fen 换算、UI 文案与放大。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "frontend" / "src" / "charts" / "keyCustomersChart.ts"
INSIGHT = ROOT / "frontend" / "src" / "components" / "key-customers" / "KeyCustomersInsight.vue"
USE_KC = ROOT / "frontend" / "src" / "composables" / "useKeyCustomers.ts"
COMPUTE = ROOT / "src" / "domain" / "key_customers" / "compute.py"
TOKENS = ROOT / "frontend" / "src" / "styles" / "tokens.css"
CSS = ROOT / "frontend" / "src" / "styles" / "components" / "KeyCustomersPanel.css"


class TestKeyCustomersChartContract(unittest.TestCase):
    def test_five_series_styles_unique(self):
        text = CHART.read_text(encoding="utf-8")
        self.assertIn("COMPARE_SERIES_STYLES", text)
        # 5 套 color+lineType+symbol
        n = len(re.findall(r"lineType:", text))
        self.assertGreaterEqual(n, 5)
        symbols = re.findall(r"symbol:\s*'(\w+)'", text)
        self.assertGreaterEqual(len(set(symbols)), 4)
        # 禁止浏览器 fen 兜底
        self.assertNotIn("1_000_000", text)
        self.assertNotIn("/ 1000000", text)
        self.assertIn("只认 value_wan", text)

    def test_ui_labels_and_clear_compare(self):
        insight = INSIGHT.read_text(encoding="utf-8")
        self.assertIn("明细查看", insight)
        self.assertNotIn(">放大<", insight.replace(" ", ""))
        self.assertIn("清空筛选", insight)
        self.assertIn("clear-compare", insight)
        use = USE_KC.read_text(encoding="utf-8")
        self.assertIn("function clearCompare", use)
        self.assertIn("compareKeys.value = []", use)

    def test_no_ytd_still_large_copy(self):
        src = COMPUTE.read_text(encoding="utf-8")
        self.assertNotIn("年累计仍可很大", src)
        # HELP_LINE_SILENT 仍保留静默定义
        self.assertIn("HELP_LINE_SILENT", src)
        self.assertIn("近 2 个已过去完整自然月", src)

    def test_kc_size_tokens_enlarged(self):
        tok = TOKENS.read_text(encoding="utf-8")
        self.assertIn("--kc-track-h: 280px", tok)
        self.assertIn("--kc-workbench-h: 660px", tok)
        self.assertIn("--kc-fs-help", tok)
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("var(--kc-track-h", css)
        self.assertIn("var(--kc-fs-help", css)


if __name__ == "__main__":
    unittest.main()
