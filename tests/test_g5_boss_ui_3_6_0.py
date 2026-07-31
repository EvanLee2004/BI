# -*- coding: utf-8 -*-
"""3.6.0 G5：老板首屏无橙色 yellow 条；KPI 保持五卡并排（撤回利润主卡实验）。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestBossNoYellowBanner(unittest.TestCase):
    def test_app_uses_neutral_freshness(self):
        app = (FE / "App.vue").read_text(encoding="utf-8")
        self.assertIn("data-freshness-strip", app)
        self.assertIn("数据更新至", app)
        # 不再用 archive-banner 挂 data-integrity 橙条
        self.assertNotRegex(
            app,
            r'class="archive-banner"[^>]*data-testid="data-integrity-strip"',
        )

    def test_css_yellow_lamp_not_warn_border(self):
        css = (FE / "styles/components/App.css").read_text(encoding="utf-8")
        # yellow lamp 不再用 --warn 边
        block = css.split('.data-integrity-strip[data-lamp="yellow"]')[1][:120]
        self.assertIn("var(--line)", block)


class TestKpiFiveCardLayout(unittest.TestCase):
    """产品拍板：恢复 3.5 五卡并排，禁止 3.6.0 利润通栏主卡。"""

    def test_kpi_cards_five_grid(self):
        src = (FE / "components/KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn('class="kpi-grid kpi-5"', src)
        self.assertIn("kpi-bus", src)
        self.assertNotIn("kpi-host--hero", src)
        self.assertNotIn("kpi-card--hero", src)
        self.assertNotIn("kpi-secondary", src)
        self.assertNotIn("kpi-bu-strip", src)


if __name__ == "__main__":
    unittest.main()
