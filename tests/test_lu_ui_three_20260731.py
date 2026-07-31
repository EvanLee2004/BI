# -*- coding: utf-8 -*-
"""陆总三项 UI：附加税费无公式文案、KC 三卡、下单回款区块顺序。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestSurtaxFormulaHidden(unittest.TestCase):
    def test_structure_附加税费_formula_empty(self):
        from domain.pl.structure import pl_structure

        p = {
            "revenue": 100,
            "revenue_net": 94.34,
            "production_cost": 10,
            "gross_profit": 84.34,
            "gross_margin_pct": 89.4,
            "surtax": 0.68,
            "other_pl": 0,
            "pretax_profit": 50,
            "pretax_margin_pct": 53,
            "expense": {},
            "manual": {},
            "ledger": {},
            "fine": {},
        }
        try:
            out = pl_structure(p, is_bu=False)
            rows = out.get("rows") if isinstance(out, dict) else []
            hit = [r for r in rows if (r.get("name") or r.get("label")) == "附加税费"]
            if hit:
                self.assertEqual(hit[0].get("formula") or "", "")
                # 金额仍绑定 surtax（展示负号在结构层）
                self.assertIn("surtax", (ROOT / "src/domain/pl/structure.py").read_text(encoding="utf-8"))
                return
        except TypeError:
            pass
        src = (ROOT / "src/domain/pl/structure.py").read_text(encoding="utf-8")
        self.assertIn('"附加税费"', src)
        self.assertNotIn("净收入×", src)
        self.assertIn('p.get("surtax")', src)


class TestKcThreeSummaryCards(unittest.TestCase):
    def test_summary_no_silent_card(self):
        vue = (FE / "components/key-customers/KeyCustomersSummary.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-testid="kc-card-total"', vue)
        self.assertIn('data-testid="kc-card-contrib"', vue)
        self.assertIn('data-testid="kc-card-near"', vue)
        self.assertNotIn("kc-card-silent", vue)
        tmpl = vue.split("<template>")[-1] if "<template>" in vue else vue
        self.assertNotIn("需跟进重点客", tmpl)
        self.assertNotIn("silent_focus", tmpl)

    def test_css_three_columns(self):
        css = (FE / "styles/components/KeyCustomersPanel.css").read_text(encoding="utf-8")
        compact = css.replace(" ", "")
        self.assertIn("repeat(3,minmax(0,1fr))", compact)
        self.assertNotIn("repeat(4,minmax(0,1fr))", compact)


class TestOrderDeptBlockOrder(unittest.TestCase):
    def test_app_and_bu_daily_rank_receipts(self):
        for rel in ("App.vue", "components/BUPage.vue"):
            text = (FE / rel).read_text(encoding="utf-8")
            tmpl = text.split("<template>")[-1] if "<template>" in text else text
            i_d = tmpl.index("<DailyQuery")
            i_r = tmpl.index("<RankingsDual")
            i_c = tmpl.index("<ReceiptsCard")
            self.assertLess(i_d, i_r, f"{rel}: DailyQuery before RankingsDual")
            self.assertLess(i_r, i_c, f"{rel}: RankingsDual before ReceiptsCard")


if __name__ == "__main__":
    unittest.main()
