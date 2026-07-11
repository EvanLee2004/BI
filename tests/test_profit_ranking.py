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
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db, loaders, profit, render, server  # noqa: E402

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
    def _period(self, top=10):
        return {"range": ("2026-01-01", "2026-12-31"),
                "profit_rankings": {
                    "revenue_by_customer": profit.compute_profit_ranking(_rows(), "客户", COLS, S, E, 0.06, top=top),
                    "revenue_by_sales": profit.compute_profit_ranking(_rows(), "销售", COLS, S, E, 0.06, top=top)}}

    def test_render_structure_and_strings(self):
        html = render.render_profit_rankings(self._period())
        self.assertIn("收入 · 按客户", html)
        self.assertIn("收入 · 按销售", html)
        self.assertIn("grid-2e", html)
        self.assertIn("毛利率 75%", html)          # 客户甲 率75
        self.assertIn("毛利率 33%", html)          # 客户乙 率33.3→33
        self.assertIn("前5大占收入 <b>91%</b>", html)   # 集中度 90.9→91（.0f）·数字放大突出
        self.assertIn('class="conc"', html)              # 集中度独立高亮块（放大）
        self.assertIn("客户乙", html)
        self.assertIn("（未填）", html)            # 未填置底
        self.assertNotIn("客户丙", html)           # 期外不出现

    def test_name_hover_and_expand_hooks(self):
        # 长名悬浮全名：data-tip（双层转义）+ title 兜底；「其余」可点开：pr-more + 维度/区间钩子
        html = render.render_profit_rankings(self._period(top=1))   # top=1 → 造出「其余」行
        self.assertIn("data-tip=", html)                 # 名称悬浮
        self.assertIn('data-dim="customer"', html)       # 客户卡维度
        self.assertIn('data-dim="sales"', html)          # 销售卡维度
        self.assertIn('class="grid-2e pr-grid"', html)
        self.assertIn('data-start="2026-01-01"', html)   # 区间给弹窗取数用
        self.assertIn("pr-more", html)                   # 「其余」可点
        self.assertIn("点开看明细", html)

    def test_no_client_side_math(self):
        # 渲染串里不得残留可被前端拿去算的原始 total/裸数值键（金额都成显示串）
        html = render.render_profit_rankings(self._period())
        self.assertNotIn("total_revenue", html)
        self.assertNotIn("margin_pct", html)

    def test_empty_period_safe(self):
        html = render.render_profit_rankings({"range": ("2026-01-01", "2026-12-31"), "profit_rankings": {
            "revenue_by_customer": profit.compute_profit_ranking([], "客户", COLS, S, E, 0.06),
            "revenue_by_sales": profit.compute_profit_ranking([], "销售", COLS, S, E, 0.06)}})
        self.assertIn("本期无数据", html)


def _seed_project(cfg, root):
    """种入 std_收入明细（供 /api/profit_ranking 端到端）。"""
    conn = db.connect(cfg, root)
    rows = [
        ("P1", "SO1", "客户甲", "线1", "销售A", "2026-03-10", 1060.0, 300.0),
        ("P2", "SO2", "客户甲", "线1", "销售A", "2026-04-10", 1060.0, 200.0),
        ("P3", "SO3", "客户乙", "线2", "销售B", "2026-05-10", 3180.0, 2000.0),
        ("P4", "SO4", "",       "线2", "",       "2026-06-10", 530.0, 100.0),   # 未填
    ]
    for k, so, cu, ln, sal, d, rev, cost in rows:
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_交付日期,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)", (k, so, cu, ln, sal, d, rev, cost, d[:7], d, d[:7]))
    conn.commit()
    conn.close()


class TestProfitRankingEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed_project(cls.cfg, cls.root)
        server._state["user_html"] = "<html>USER</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.raw = TestClient(cls.app, follow_redirects=False)      # 未登录
        cls.main = TestClient(cls.app, follow_redirects=False)     # 整体会话
        r = cls.main.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        assert r.status_code == 303, r.text

    def _q(self, **kw):
        p = {"start": "2026-01-01", "end": "2026-12-31"}
        p.update(kw)
        return self.main.get("/api/profit_ranking", params=p)

    def test_requires_viewer_session(self):
        r = self.raw.get("/api/profit_ranking", params={"dim": "customer", "start": "2026-01-01", "end": "2026-12-31"})
        self.assertEqual(r.status_code, 401)     # 全公司口径出口，未登录挡

    def test_bad_dim_400(self):
        self.assertEqual(self._q(dim="bogus").status_code, 400)
        self.assertEqual(self._q(dim="").status_code, 400)

    def test_bad_dates_400(self):
        self.assertEqual(self._q(dim="customer", start="2026/01/01").status_code, 400)
        self.assertEqual(self._q(dim="customer", start="2026-12-31", end="2026-01-01").status_code, 400)
        self.assertEqual(self._q(dim="customer", start="2025-01-01", end="2026-06-01").status_code, 400)

    def test_customer_full_list_and_disp(self):
        d = self._q(dim="customer").json()
        names = [it["name"] for it in d["items"]]
        self.assertEqual(names[:2], ["客户乙", "客户甲"])     # 按收入降序
        self.assertEqual(names[-1], "（未填）")               # 未填置底
        self.assertTrue(d["items"][-1].get("unfilled"))
        it0 = d["items"][0]
        self.assertIn("万", it0["revenue_disp"])              # 金额成串
        self.assertIn("毛利率", it0["margin_disp"])
        self.assertNotIn("revenue", it0)                      # 原始数值不下发（前端零运算）
        self.assertNotIn("margin_pct", it0)

    def test_sales_dim(self):
        d = self._q(dim="sales").json()
        self.assertEqual([it["name"] for it in d["items"]][:2], ["销售B", "销售A"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
