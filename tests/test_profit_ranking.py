#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块③ 收入与毛利结构（compute_profit_ranking + render_profit_rankings）。
跑：.venv/bin/python tests/test_profit_ranking.py

守卫点：
- 口径：收入=Σ交付额÷1.06、毛利=收入−Σ项目成本、毛利率=毛利÷收入（1 位小数）
- 按收入降序；top/others 切分；未填名字置底 unfilled（不进 top、计入 total）
- 守恒：Σitems收入 + others收入 + unfilled收入 == total_revenue（毛利同）
- 集中度：前 k 大占总收入%
- 边界：收入 0 → 毛利率 None；空数据 → items 空
- 渲染：卡片标题/毛利率串/集中度串在位；前端零运算（无 JS 金额计算）
"""
import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import profit, render  # noqa: E402

COLS = {"project_delivery_date": "整单交付日期", "project_revenue": "交付额", "project_cost": "项目成本"}
S, E = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)


def _rows():
    def r(cu, sal, gross, cost, d):
        return {"客户": cu, "销售": sal, "整单交付日期": d, "交付额": gross, "项目成本": cost}
    return [
        r("客户甲", "销售A", 1060, 300, "2026-03-10"),   # 收入1000 毛利700
        r("客户甲", "销售A", 1060, 200, "2026-04-10"),   # 收入1000 毛利800  → 客户甲合计 收入2000 毛利1500 率75
        r("客户乙", "销售B", 3180, 2000, "2026-05-10"),  # 收入3000 毛利1000 率33.3
        r("",        "",     530, 100, "2026-06-10"),    # 收入500  毛利400 → 未填
        r("客户丙", "销售C", 1060, 400, "2025-12-31"),   # 期外，应被过滤
    ]


class TestComputeProfitRanking(unittest.TestCase):
    def test_customer_caliber_sort_and_margin(self):
        rk = profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06)
        names = [it["name"] for it in rk["items"]]
        self.assertEqual(names, ["客户乙", "客户甲"])            # 按收入降序
        self.assertEqual(rk["items"][0]["revenue"], 3000.0)
        self.assertEqual(rk["items"][0]["profit"], 1000.0)
        self.assertEqual(rk["items"][0]["margin_pct"], 33.3)     # 1000/3000
        self.assertEqual(rk["items"][1]["revenue"], 2000.0)
        self.assertEqual(rk["items"][1]["margin_pct"], 75.0)
        self.assertEqual(rk["unfilled"]["revenue"], 500.0)       # 空名置底
        self.assertEqual(rk["unfilled"]["profit"], 400.0)

    def test_conservation_and_total(self):
        rk = profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06)
        self.assertEqual(rk["total_revenue"], 5500.0)            # 1000+1000+3000+500
        self.assertEqual(rk["total_profit"], 2900.0)             # 700+800+1000+400
        got_rev = sum(it["revenue"] for it in rk["items"]) + rk["unfilled"]["revenue"]
        got_prof = sum(it["profit"] for it in rk["items"]) + rk["unfilled"]["profit"]
        self.assertEqual(got_rev, rk["total_revenue"])
        self.assertEqual(got_prof, rk["total_profit"])

    def test_top_and_others_split_conserves(self):
        rk = profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06, top=1)
        self.assertEqual([it["name"] for it in rk["items"]], ["客户乙"])
        self.assertEqual(rk["others"]["names"], 1)               # 客户甲进「其余」
        self.assertEqual(rk["others"]["revenue"], 2000.0)
        self.assertEqual(rk["others"]["margin_pct"], 75.0)       # 合并后再算率
        got = rk["items"][0]["revenue"] + rk["others"]["revenue"] + rk["unfilled"]["revenue"]
        self.assertEqual(got, rk["total_revenue"])              # 守恒不因切分变

    def test_concentration(self):
        rk = profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06, conc_k=5)
        # 前5大（实际2个）收入=5000，总5500 → 90.9%
        self.assertEqual(rk["conc_pct"], 90.9)
        self.assertEqual(rk["conc_k"], 5)

    def test_sales_caliber(self):
        rk = profit.compute_profit_ranking(_rows(), "销售", COLS, S, E, 0.06)
        self.assertEqual([it["name"] for it in rk["items"]], ["销售B", "销售A"])
        self.assertEqual(rk["items"][1]["revenue"], 2000.0)     # 销售A

    def test_zero_revenue_margin_none(self):
        rows = [{"客户": "客户零", "销售": "S", "整单交付日期": "2026-03-01",
                 "交付额": 0, "项目成本": 100}]
        rk = profit.compute_profit_ranking(rows, "客户", COLS, S, E, 0.06)
        self.assertIsNone(rk["items"][0]["margin_pct"])         # 收入0 → 率 None
        self.assertIsNone(rk["conc_pct"])                       # 总收入0 → 集中度 None

    def test_empty(self):
        rk = profit.compute_profit_ranking([], "客户", COLS, S, E, 0.06)
        self.assertEqual(rk["items"], [])
        self.assertIsNone(rk["others"])
        self.assertIsNone(rk["unfilled"])
        self.assertEqual(rk["total_revenue"], 0.0)


class TestRenderProfitRankings(unittest.TestCase):
    def _period(self):
        return {"profit_rankings": {
            "revenue_by_customer": profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06),
            "revenue_by_sales": profit.compute_profit_ranking(_rows(), "销售", COLS, S, E, 0.06)}}

    def test_render_structure_and_strings(self):
        html = render.render_profit_rankings(self._period())
        self.assertIn("收入 · 按客户", html)
        self.assertIn("收入 · 按销售", html)
        self.assertIn("grid-2e", html)
        self.assertIn("毛利率 75%", html)          # 客户甲 率75
        self.assertIn("毛利率 33%", html)          # 客户乙 率33.3→33
        self.assertIn("前5大占收入 91%", html)     # 集中度 90.9→91（.0f）
        self.assertIn("客户乙", html)
        self.assertIn("（未填）", html)            # 未填置底
        self.assertNotIn("客户丙", html)           # 期外不出现

    def test_no_client_side_math(self):
        # 渲染串里不得残留可被前端拿去算的原始 total/裸数值键（金额都成显示串）
        html = render.render_profit_rankings(self._period())
        self.assertNotIn("total_revenue", html)
        self.assertNotIn("margin_pct", html)

    def test_empty_period_safe(self):
        html = render.render_profit_rankings({"profit_rankings": {
            "revenue_by_customer": profit.compute_profit_ranking([], "客户", COLS, S, E, 0.06),
            "revenue_by_sales": profit.compute_profit_ranking([], "销售", COLS, S, E, 0.06)}})
        self.assertIn("本期无数据", html)


if __name__ == "__main__":
    unittest.main(verbosity=1)
