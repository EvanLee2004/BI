# -*- coding: utf-8 -*-
"""3.6.0 G5：老板首屏无橙色 yellow 条；KPI 利润主卡布局。"""

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


class TestKpiHeroLayout(unittest.TestCase):
    def test_kpi_cards_hero_structure(self):
        src = (FE / "components/KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn("kpi-host--hero", src)
        self.assertIn("kpi-card--hero", src)
        self.assertIn("kpi-secondary", src)
        self.assertIn("kpi-bu-strip", src)
        # 不再强制 kpi-5 五卡等高网格作为唯一布局
        self.assertNotIn('class="kpi-grid kpi-5"', src)


if __name__ == "__main__":
    unittest.main()
