# -*- coding: utf-8 -*-
"""3.7.5 G3：看端三组件契约守卫（ReceiptsCard / 重点客户 / 热力 / HelpPopover）。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestReceiptsCard375(unittest.TestCase):
    def test_year_progress_side_and_aria(self):
        vue = (FE / "components/ReceiptsCard.vue").read_text(encoding="utf-8")
        self.assertIn('aria-label="下单/回款摘要"', vue)
        self.assertIn('data-testid="rc-year-progress"', vue)
        self.assertIn("rc-metric-value", vue)
        self.assertIn("order_remain_disp", vue)
        self.assertIn("receipt_remain_disp", vue)
        self.assertIn("barMaxWidth: 28", vue)
        self.assertIn("barGap: '12%'", vue)
        # 金额显示走 withWanUnit / VM disp，无前端金额运算
        self.assertNotRegex(vue, r"orders\s*\+\s*receipts|parseFloat\(.*disp")

    def test_backend_remain_fields(self):
        src = (ROOT / "src/viewmodels/__init__.py").read_text(encoding="utf-8")
        self.assertIn("remain_disp", src)
        self.assertIn("remain_hint", src)


class TestKeyCustomersSummary375(unittest.TestCase):
    def test_three_cards_no_silent_summary(self):
        vue = (FE / "components/key-customers/KeyCustomersSummary.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-testid="kc-card-total"', vue)
        self.assertIn('data-testid="kc-card-contrib"', vue)
        self.assertIn('data-testid="kc-card-near"', vue)
        self.assertNotIn('data-testid="kc-card-silent"', vue)
        self.assertIn("kc-summary-cards--triple", vue)
        # 行动队列仍在 panel/insight
        panel = (FE / "components/key-customers/KeyCustomersPanel.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("KeyCustomersInsight", panel)
        self.assertIn("HelpPopover", panel)


class TestHelpPopover375(unittest.TestCase):
    def test_hover_pin_esc_place(self):
        vue = (FE / "components/base/HelpPopover.vue").read_text(encoding="utf-8")
        self.assertIn("placePanel", vue)
        self.assertIn("Teleport", vue)
        self.assertIn("Escape", vue)
        self.assertIn("onHoverIn", vue)
        self.assertIn("togglePin", vue)
        self.assertIn("DataModal", vue)
        self.assertIn("isNarrow", vue)


class TestExpenseHeat375(unittest.TestCase):
    def test_pack_has_range_and_missing(self):
        util = (FE / "utils/expense-heat.ts").read_text(encoding="utf-8")
        self.assertIn("missingMap", util)
        self.assertIn("vmid", util)
        self.assertIn("unit:", util)
        vue = (FE / "components/ExpenseHeatmap.vue").read_text(encoding="utf-8")
        self.assertIn("expense-heatmap-legend", vue)
        self.assertIn("暂无数据", vue)
        self.assertIn("确认 0", vue)
        self.assertIn("borderRadius: 4", vue)


if __name__ == "__main__":
    unittest.main()
