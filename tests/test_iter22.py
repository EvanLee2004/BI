#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代22 测试：2026-07-14 陆总过盘反馈（批次A小改 + 批次B 分摊沿用/销售利润率）。
跑：.venv/bin/python tests/test_iter22.py

守卫点：
- A1 回款图率%标在折线点旁（class="rl"），柱底不再有率行；图例改「线上」
- A2/A3 回款卡不再出现防误读长句与峰值/谷值徽章
- A5 板块③「系统成本率」=cost_pct；按销售卡不显示率列
- B1 分摊比例沿用最近填写月（effective_alloc_month / effective_alloc_ratios）
- B2 利润表「销售利润率」行（整体 + BU 两版）
"""

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import charts
import db
import loaders
import profit
import render  # noqa: E402

S, E = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
COLS = {"project_delivery_date": "整单交付日期", "project_revenue": "交付额", "project_cost": "项目成本"}


def _proj_rows():
    return [
        {"整单交付日期": "2026-03-01", "交付额": 2120, "项目成本": 500, "客户": "客户甲", "销售": "销售A"},
        {"整单交付日期": "2026-04-01", "交付额": 3180, "项目成本": 2000, "客户": "客户乙", "销售": "销售B"},
    ]


class TestReceiptChartLabels(unittest.TestCase):
    def test_ratio_label_on_line_point(self):
        svg = charts.receipt_order_chart([("1月", 100.0, 200.0, 50.0), ("2月", 80.0, 100.0, 80.0)])
        self.assertIn('class="rl"', svg)  # 率%标签挂折线点
        self.assertIn("线上·%", svg)  # 图例改口
        self.assertNotIn("月下·%", svg)

    def test_no_receipt_note_and_pills_in_card(self):
        html = render.render_receipts([("1月", 100.0, 200.0, 50.0)])
        self.assertNotIn("当月回款多对应往月下单", html)  # A2 防误读长句删除
        self.assertNotIn("峰值", html)  # A3 峰谷徽章删除
        self.assertNotIn("谷值", html)
        self.assertNotIn("rc-pills", html)


class TestSystemCostRate(unittest.TestCase):
    def test_cost_pct_computed(self):
        rk = profit.compute_profit_ranking(_proj_rows(), "客户", COLS, S, E, 0.06)
        by = {it["name"]: it for it in rk["items"]}
        self.assertEqual(by["客户甲"]["cost_pct"], 25.0)  # 500/2000
        self.assertEqual(by["客户乙"]["cost_pct"], 66.7)  # 2000/3000

    def test_sales_card_hides_rate(self):
        period = {
            "range": ("2026-01-01", "2026-12-31"),
            "profit_rankings": {
                "revenue_by_customer": profit.compute_profit_ranking(_proj_rows(), "客户", COLS, S, E, 0.06),
                "revenue_by_sales": profit.compute_profit_ranking(_proj_rows(), "销售", COLS, S, E, 0.06),
            },
        }
        html = render.render_profit_rankings(period)
        cust_card = html.split('data-dim="sales"')[0]
        sales_card = html.split('data-dim="sales"')[1]
        self.assertIn("系统成本率", cust_card)
        self.assertNotIn("系统成本率", sales_card)
        self.assertNotIn("项目毛利率", html)  # 旧名彻底退场


class TestAllocCarryForward(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_effective_month_carries_latest(self):
        db.set_alloc_ratio(self.conn, "2026-01", "游戏", 60, "t")
        db.set_alloc_ratio(self.conn, "2026-01", "数据", 40, "t")
        db.set_alloc_ratio(self.conn, "2026-05", "游戏", 30, "t")
        # 3月没填 → 沿用 1 月
        r, src = db.effective_alloc_month(self.conn, "2026-03")
        self.assertEqual((r, src), ({"游戏": 60.0, "数据": 40.0}, "2026-01"))
        # 5月自己填了 → 用自己（数据在5月未填=不分摊，不继承1月）
        r, src = db.effective_alloc_month(self.conn, "2026-05")
        self.assertEqual((r, src), ({"游戏": 30.0}, "2026-05"))
        # 7月没填 → 沿用 5 月
        r, src = db.effective_alloc_month(self.conn, "2026-07")
        self.assertEqual((r, src), ({"游戏": 30.0}, "2026-05"))

    def test_effective_before_first_fill_is_empty(self):
        db.set_alloc_ratio(self.conn, "2026-05", "游戏", 30, "t")
        r, src = db.effective_alloc_month(self.conn, "2026-02")
        self.assertEqual((r, src), ({}, None))
        eff = db.effective_alloc_ratios(self.conn, 2026, 7)
        self.assertNotIn("2026-02", eff)  # 首填前不摊
        self.assertEqual(eff["2026-06"], {"游戏": 30.0})  # 首填后逐月沿用
        self.assertEqual(eff["2026-07"], {"游戏": 30.0})

    def test_no_records_empty(self):
        self.assertEqual(db.effective_alloc_ratios(self.conn, 2026, 7), {})
        self.assertEqual(db.effective_alloc_month(self.conn, "2026-07"), ({}, None))

    def test_zero_pct_blocks_carry_semantics(self):
        # 填 0 = 该月显式不分摊（区别于留空=沿用）
        db.set_alloc_ratio(self.conn, "2026-01", "游戏", 50, "t")
        db.set_alloc_ratio(self.conn, "2026-03", "游戏", 0, "t")
        r, src = db.effective_alloc_month(self.conn, "2026-04")
        self.assertEqual((r, src), ({"游戏": 0.0}, "2026-03"))


class TestSalesProfitMarginRow(unittest.TestCase):
    def _period(self):
        cats = list(profit._LEDGER_TO_EXPENSE)
        return {
            "revenue_net": 1000.0,
            "production_cost": 400.0,
            "gross_profit": 600.0,
            "system_direct_cost": 400.0,
            "inhouse_cost": 0.0,
            "surtax": 7.2,
            "other_pl": 0.0,
            "pretax_profit": 500.0,
            "pretax_margin_pct": 50.0,
            "range": ("2026-01-01", "2026-12-31"),
            "expense": {
                "营销费用": 10.0,
                "管理费用": 20.0,
                "固定运营费用": 30.0,
                "研发费用": 0.0,
                "财务费用": 0.0,
                "total": 60.0,
            },
            "manual": {
                k: 0.0
                for k in (
                    "营销人力成本",
                    "管理人力成本",
                    "研发人力成本",
                    "财务费用补充",
                    "PM人力成本",
                    "VM人力成本",
                    "实际内部译员成本",
                    "税费损失",
                    "技术流量成本",
                    "其他（生产成本）",
                    "其他损益",
                )
            },
            "ledger_expenses": {c: 0.0 for c in cats},
        }

    def test_main_pl_has_row(self):
        html = render.render_pl_table(self._period(), {})
        self.assertIn("税前利润率", html)
        self.assertIn("50.0%", html)
        self.assertIn("税前利润÷交付收入", html)

    def test_bu_pl_has_row(self):
        html, _note = render.render_bu_pl_table(self._period())
        self.assertIn("税前利润率", html)
        self.assertIn("50.0%", html)


class TestOrdersByBU(unittest.TestCase):
    """批次C：下单排名按 BU（销售→BU 映射）+ 下单卡 BU 进度块。"""

    def test_ranking_with_name_of(self):
        rows = [
            {"下单日期": "2026-02-01", "预估金额": 100.0, "销售": "张三"},
            {"下单日期": "2026-03-01", "预估金额": 50.0, "销售": "李四"},
            {"下单日期": "2026-03-02", "预估金额": 30.0, "销售": "王麻子"},
        ]  # 未归属
        m = {"张三": "游戏", "李四": "游戏"}
        rk = profit.compute_ranking(
            rows,
            "销售",
            "预估金额",
            "下单日期",
            S,
            E,
            empty_label="（未归属）",
            name_of=lambda r: m.get(str(r.get("销售") or "").strip(), ""),
        )
        self.assertEqual(rk["items"][0], {"name": "游戏", "amount": 150.0, "count": 2})
        self.assertEqual(rk["unfilled"], {"amount": 30.0, "count": 1})  # 未归属置底
        self.assertEqual(rk["total"], 180.0)  # 守恒

    def test_rank_card_swaps_to_bu(self):
        # A6：双血条两卡按销售/按客户；不再按部门/按BU 首卡切换
        p = {
            "range": ("2026-01-01", "2026-12-31"),
            "rankings": {
                "orders_by_sales": {
                    "items": [{"name": "甲", "amount": 1, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 1, "count": 1}],
                    "total": 1,
                },
                "receipts_by_sales": {
                    "items": [{"name": "甲", "amount": 1, "count": 1}],
                    "full_items": [{"name": "甲", "amount": 1, "count": 1}],
                    "total": 1,
                },
                "orders_by_customer": {"items": [], "total": 0},
                "receipts_by_customer": {"items": [], "total": 0},
            },
        }
        html = render.render_rankings(p)
        self.assertIn("下单/回款 · 按销售", html)
        self.assertIn("下单/回款 · 按客户", html)
        self.assertIn("dual-bar", html)
        self.assertNotIn("按部门", html)

    def test_bu_orders_block(self):
        lst = [
            {"name": "游戏", "amount": 500000.0, "year_amount": 1200000.0, "target": 2000000.0, "pct": 60.0},
            {"name": "数据", "amount": 0.0, "year_amount": 0.0, "target": None, "pct": None},
        ]
        html = render._bu_orders_block(lst)
        self.assertIn("kpi-bus", html)
        self.assertIn("游戏", html)
        self.assertIn("60%", html)
        self.assertIn("未设目标", html)
        self.assertEqual(render._bu_orders_block(None), "")  # BU 页不传 → 空（铁律12）

    def test_render_basic_only_orders_card_gets_block(self):
        # bu_orders 只挂下单卡；其他卡不出现；无迷你折线、有峰值/已交付未回款脚
        import copy

        p = {k: 0.0 for k in ("orders", "revenue_gross", "revenue_net", "gross_profit", "pretax_profit", "receipts")}
        p.update({"gross_margin_pct": 0.0, "pretax_margin_pct": 0.0, "receipt_order_ratio_pct": None})
        p1 = copy.deepcopy(p)
        p1["orders"] = 100.0
        p1["receipts"] = 40.0
        p1["revenue_gross"] = 80.0
        P = {"2026年": copy.deepcopy(p1), "2026年1月": copy.deepcopy(p1), "2026年2月": copy.deepcopy(p)}
        months = ["2026年1月", "2026年2月"]
        lst = [{"name": "游戏", "amount": 1.0, "year_amount": 1.0, "target": None, "pct": None}]
        html = render.render_basic("2026年", P, 2026, months, None, bu_orders=lst)
        self.assertEqual(html.count("kpi-bus"), 1)
        self.assertNotIn("kpi-spark", html)
        self.assertNotIn('class="spark"', html)
        self.assertIn("全年峰值", html)
        # A3：默认隐藏「已交付未回款」；显式打开才出现
        self.assertNotIn("已交付未回款", html)
        html_ar = render.render_basic("2026年", P, 2026, months, None, bu_orders=lst, show_delivered_unpaid=True)
        self.assertIn("已交付未回款", html_ar)
        self.assertIn("交付占下单", html)
        html2 = render.render_basic("2026年", P, 2026, months, None)  # 不传=不渲染
        self.assertNotIn("kpi-bus", html2)


class TestBuPageAlignment(unittest.TestCase):
    """批次D：BU 页对齐整体页（费用类别视图 / 利润表下钻 / 收入结构 / 回款卡 / 导出钩子）。"""

    def _fine(self):
        return {"管理费用": [("办公费", 300.0), ("差旅费", 100.0)], "市场费用": [("差旅费", 50.0)]}

    def test_fine_to_rows_merges_across_cats(self):
        rows = render._fine_to_rows(self._fine())
        by = {n: (v, d) for n, v, d in rows}
        self.assertEqual(by["差旅费"][0], 150.0)  # 跨大类合并
        self.assertEqual(rows[0][0], "办公费")  # 降序
        self.assertEqual(render._fine_to_rows(None), [])

    def _bu_period(self, alloc_added=None):
        cats = list(profit._LEDGER_TO_EXPENSE)
        led = {c: 0.0 for c in cats}
        led["管理费用"] = 400.0
        p = {
            "revenue_net": 1000.0,
            "production_cost": 400.0,
            "gross_profit": 600.0,
            "system_direct_cost": 400.0,
            "inhouse_cost": 0.0,
            "surtax": 7.2,
            "other_pl": 0.0,
            "pretax_profit": 192.8,
            "pretax_margin_pct": 19.3,
            "range": ("2026-01-01", "2026-12-31"),
            "expense": {
                "营销费用": 0.0,
                "管理费用": 400.0,
                "固定运营费用": 0.0,
                "研发费用": 0.0,
                "财务费用": 0.0,
                "total": 400.0,
            },
            "manual": {
                k: 0.0
                for k in (
                    "营销人力成本",
                    "管理人力成本",
                    "研发人力成本",
                    "财务费用补充",
                    "PM人力成本",
                    "VM人力成本",
                    "实际内部译员成本",
                    "税费损失",
                    "技术流量成本",
                    "其他（生产成本）",
                    "其他损益",
                )
            },
            "ledger_expenses": led,
        }
        if alloc_added:
            p["alloc_added"] = alloc_added
        return p

    def test_bu_pl_drilldown_blocks(self):
        p = self._bu_period()
        html, _ = render.render_bu_pl_table(p, {"enabled": False}, fine=self._fine())
        self.assertIn('data-cat="admin"', html)  # 费用行可下钻
        self.assertIn("管理费用构成", html)
        self.assertIn("办公费", html)  # 细类进抽屉
        self.assertNotIn("分摊自公共", html)  # 未分摊不出该行

    def test_bu_pl_alloc_decomposed(self):
        p = self._bu_period(
            alloc_added={"管理费用": 100.0, "市场费用": 0.0, "固定运营费用": 0.0, "技术服务费": 0.0, "财务费用": 0.0}
        )
        html, _ = render.render_bu_pl_table(p, {"enabled": True, "ratio_disp": "按月比例"}, fine=self._fine())
        self.assertIn("分摊自公共", html)
        # 直记与分摊分行展示（468d131 起不再标「台账直记」字样）：管理费用抽屉里
        # 台账直记额（led−分摊）与独立「分摊自公共」行并列，不并进大类总额
        admin_drawer = html.split('data-title="管理费用构成"', 1)[1]
        self.assertIn('pl-name">管理费用', admin_drawer)  # 台账直记额单独成行
        self.assertIn('pl-name">分摊自公共', admin_drawer)  # 分摊单独成行

    def test_bu_expense_views_no_dept(self):
        html = render.render_bu_expense_views(self._bu_period(), self._fine())
        self.assertIn("按类别", html)
        self.assertIn("按大类", html)
        self.assertNotIn("按部门", html)  # BU 页无部门口径
        self.assertNotIn("按费用类别", html)  # 文案与整体页统一为「按类别」


class TestCostVatManual(unittest.TestCase):
    """批次E1：手填「直接成本增值税」从生产成本中扣除（默认0=数字与旧口径一分不差）。"""

    def setUp(self):
        self.cfg = loaders.load_config()
        self.today = datetime.date(2026, 7, 15)

    def _summary(self, manual_raw):
        header = list(profit._BU_EMPTY_LEDGER_HEADER)
        return profit.build_summary(self.cfg, [], [], [], [], header, [], 2026, self.today, manual_raw=manual_raw)

    def test_item_registered(self):
        names = {it["name"] for it in self.cfg["manual_items"]}
        self.assertIn("直接成本增值税", names)

    def test_default_zero_no_change(self):
        s0 = self._summary({})
        self.assertEqual(s0["periods"]["2026年"]["production_cost"], 0.0)

    def test_vat_reduces_production_cost(self):
        s = self._summary({"2026-01": {"直接成本增值税": 100.0, "PM人力成本": 300.0}})
        p = s["periods"]["2026年"]
        # 生产成本 = 系统直接成本0 − 内译0 + 手填300 − 增值税100 = 200
        self.assertEqual(p["production_cost"], 200.0)
        self.assertEqual(p["gross_profit"], -200.0)

    def test_row_in_pl_drawers(self):
        s = self._summary({"2026-01": {"直接成本增值税": 100.0}})
        html = render.render_pl_table(s["periods"]["2026年"], {})
        self.assertIn("直接成本增值税", html)
        self.assertNotIn("减：直接成本增值税", html)  # 看端抽屉去掉加/减前缀
        bu_html, _ = render.render_bu_pl_table(s["periods"]["2026年"])
        self.assertIn("直接成本增值税", bu_html)


class TestManualItemsInjected(unittest.TestCase):
    """迭代22修：管理端手填清单从 config 注入（曾硬编码致「直接成本增值税」不出现在填写页）。"""

    def test_admin_page_contains_new_item(self):
        import server

        cfg = loaders.load_config()
        # 手填清单由 /admin/app.js 注入；此处模拟注入结果
        js = server.admin_ui_source()
        self.assertIn("__MANUAL_ITEMS__", js)  # 磁盘模板占位
        injected = js.replace("__MANUAL_ITEMS__", server._manual_items_json(cfg))
        self.assertIn("直接成本增值税", injected)
        self.assertNotIn("__MANUAL_ITEMS__", injected)

    def test_placeholder_exists_in_template(self):
        import server

        self.assertIn("__MANUAL_ITEMS__", server.admin_ui_source())  # 别名→static/admin


class TestReceiptDeliveredUnpaid(unittest.TestCase):
    """A3 回款侧栏：总下单/总回款首行；已交付未回款默认隐藏、可开关恢复。"""

    SERIES = [("1月", 200_000.0, 500_000.0, 40.0), ("2月", 200_000.0, 500_000.0, 40.0)]  # 累计回款 40 万、下单 100 万

    def test_totals_first_line_and_default_hide_ar(self):
        html = render.render_receipts(self.SERIES, delivered_gross=1_000_000.0)
        self.assertIn("总下单", html)
        self.assertIn("总回款", html)
        self.assertIn("下单未回款", html)
        self.assertNotIn("已交付未回款", html)  # A3 默认隐藏
        self.assertNotIn("rc-recv", html)
        self.assertNotIn("缺口（下单 − 回款）", html)

    def test_show_delivered_unpaid_switch(self):
        html = render.render_receipts(self.SERIES, delivered_gross=1_000_000.0, show_delivered_unpaid=True)
        self.assertIn("已交付未回款", html)
        self.assertIn("rc-recv", html)
        self.assertIn("60.0万", html)

    def test_amount_string_when_shown(self):
        html_neg = render.render_receipts(
            [("1月", 1_500_000.0, 100_000.0, None)], delivered_gross=1_000_000.0, show_delivered_unpaid=True
        )
        self.assertIn("−50.0万", html_neg)

    def test_chart_has_order_bars(self):
        import charts

        svg = charts.receipt_order_chart(self.SERIES)
        self.assertIn("bar-ord", svg)
        self.assertIn("下单额", svg)


class TestBuExportGate(unittest.TestCase):
    """D5：BU 导出出口的登录闸（未登录 401、未知 BU 404）——铁律12 隔离守卫。"""

    @classmethod
    def setUpClass(cls):
        import server
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.cfg = loaders.load_config()
        cls.app = server.create_app(cls.cfg, root=Path(cls.tmp))
        cls.client = TestClient(cls.app, follow_redirects=False)
        server._state["bu_pages"] = {"游戏": {"name": "游戏", "html": "<html><body>x</body></html>"}}

    def test_unknown_bu_404(self):
        self.assertEqual(self.client.get("/bu/不存在/export.png").status_code, 404)

    def test_anonymous_401(self):
        self.assertEqual(self.client.get("/bu/游戏/export.png").status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=1)
