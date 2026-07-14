#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.5 按天明细测试（迭代计划13批次B）：compute_daily 守恒/边界 + /api/daily 只读接口校验 + 前端入口。
跑：.venv/bin/python tests/test_daily.py

守卫点：
- ∑按天 == compute_orders/compute_receipts 同区间合计（守恒红线）
- 空区间/单日边界/非法入参（格式/顺序/超366天）
- 接口纯只读：POST /api/daily 不存在（405）；v7.8 起须整体页/管理员会话（未登录 401）
- 用户页含「按天明细」入口与面板；显示串由后端下发（days/totals/rankings 全是 *_disp）
"""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db, loaders, profit, server  # noqa: E402

D1, D31 = datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)


def _seed(cfg, root):
    conn = db.connect(cfg, root)
    orders = [
        ("O1", "SO1", "2026-03-01", 1000.0, "部门B", "张三"),
        ("O2", "SO2", "2026-03-01", 2000.0, "", "李四"),
        ("O3", "SO3", "2026-03-05", 300.0, "部门A", "王五"),
        ("O4", "SO4", "2026-04-01", 999.0, "部门A", "王五"),   # 区间外
    ]
    for k, o, d, a, dep, sal in orders:
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,0)", (k, o, d, a, dep, sal, d[:7], d[:7]))
    receipts = [("R1", "HK1", "2026-03-05", 500.0, "客户甲"), ("R2", "HK2", "2026-03-31", 700.0, "客户乙")]
    for k, rid, d, a, cu in receipts:
        conn.execute(
            "INSERT INTO std_回款(定位键,回款ID,到账日期,到账金额,客户,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,0)", (k, rid, d, a, cu, d[:7], d[:7]))
    conn.commit()
    conn.close()


class TestComputeDaily(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.cfg = loaders.load_config()
        _seed(self.cfg, self.root)
        conn = db.connect(self.cfg, self.root)
        self.orders = db.load_orders(self.cfg, conn)
        self.receipts = db.load_receipts(self.cfg, conn)
        conn.close()
        self.cols = self.cfg["columns"]

    def _daily(self, s=D1, e=D31):
        return profit.compute_daily(self.orders, self.receipts, self.cols, s, e)

    def test_days_sparse_sorted_and_grouped(self):
        d = self._daily()
        self.assertEqual([r["day"] for r in d["days"]], ["2026-03-01", "2026-03-05", "2026-03-31"])
        d0 = d["days"][0]
        self.assertEqual((d0["orders"], d0["orders_count"], d0["receipts_count"]), (3000.0, 2, 0))
        d1 = d["days"][1]
        self.assertEqual((d1["orders"], d1["receipts"]), (300.0, 500.0))

    def test_conservation_sum_days_eq_period_total(self):
        """守恒红线：∑按天 == 同区间 compute_orders / compute_receipts。"""
        d = self._daily()
        self.assertAlmostEqual(sum(r["orders"] for r in d["days"]),
                               profit.compute_orders(self.orders, self.cols, D1, D31), places=2)
        self.assertAlmostEqual(sum(r["receipts"] for r in d["days"]),
                               profit.compute_receipts(self.receipts, self.cols, D1, D31), places=2)
        self.assertAlmostEqual(d["totals"]["orders"], 3300.0, places=2)
        self.assertAlmostEqual(d["totals"]["receipts"], 1200.0, places=2)

    def test_single_day_boundary(self):
        d = self._daily(datetime.date(2026, 3, 31), datetime.date(2026, 3, 31))
        self.assertEqual(len(d["days"]), 1)
        self.assertEqual(d["days"][0]["receipts"], 700.0)
        self.assertEqual(d["totals"]["orders_count"], 0)

    def test_empty_range(self):
        d = self._daily(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        self.assertEqual(d["days"], [])
        self.assertEqual(d["totals"]["orders"], 0.0)

    def test_rankings_present_with_unfilled(self):
        d = self._daily()
        rk = d["rankings"]["orders_by_dept"]
        self.assertEqual(rk["unfilled"], {"amount": 2000.0, "count": 1})
        self.assertEqual({i["name"] for i in rk["items"]}, {"部门A", "部门B"})

    def test_orders_by_bu_when_sales_map(self):
        """配了销售→BU 映射时，时间段查询也应出 orders_by_bu（与全年预渲染同口径）。"""
        orders = [
            {"下单日期": "2026-03-01", "下单预估额": 1000.0, "部门": "部门B", "销售": "张三"},
            {"下单日期": "2026-03-01", "下单预估额": 2000.0, "部门": "", "销售": "李四"},
            {"下单日期": "2026-03-05", "下单预估额": 300.0, "部门": "部门A", "销售": "王五"},
        ]
        receipts = []
        cols = {"order_amount": "下单预估额", "order_date": "下单日期",
                "receipt_amount": "到账金额", "receipt_date": "到账日期"}
        # 张三+李四 → 游戏；王五未映射 → 未归属
        d = profit.compute_daily(orders, receipts, cols, D1, D31,
                                 sales_to_bu={"张三": "游戏", "李四": "游戏"})
        self.assertIn("orders_by_bu", d["rankings"])
        bu = d["rankings"]["orders_by_bu"]
        self.assertEqual(bu["items"][0]["name"], "游戏")
        self.assertEqual(bu["items"][0]["amount"], 3000.0)
        self.assertEqual(bu["unfilled"]["amount"], 300.0)
        # 无映射时不挂该键（前端回退按部门）
        d0 = profit.compute_daily(orders, receipts, cols, D1, D31)
        self.assertNotIn("orders_by_bu", d0["rankings"])


class TestDailyEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed(cls.cfg, cls.root)
        server._state["user_html"] = "<html>USER</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.raw = TestClient(cls.app, follow_redirects=False)     # 真·未登录（v7.8 起接口要看板会话）
        cls.anon = TestClient(cls.app, follow_redirects=False)    # 整体页会话（原"公开"改为登录后可用）
        r = cls.anon.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        assert r.status_code == 303

    def test_requires_viewer_session(self):
        """v7.8：/api/daily 是全公司口径出口，未登录 401（防拿 BU 链接的人绕过页面隔离）。"""
        r = self.raw.get("/api/daily", params={"start": "2026-03-01", "end": "2026-03-31"})
        self.assertEqual(r.status_code, 401)

    def test_public_and_display_strings(self):
        r = self.anon.get("/api/daily", params={"start": "2026-03-01", "end": "2026-03-31"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["days"]), 3)
        row = d["days"][0]
        self.assertIn("orders_disp", row)
        self.assertIn("万", row["orders_disp"])
        self.assertNotIn("orders", [k for k in row if k not in ("orders_disp", "orders_count")])
        self.assertIn("万", d["totals"]["orders_disp"])
        rk = d["rankings"]["orders_by_dept"]
        self.assertIn("disp", rk["items"][0])
        self.assertNotIn("amount", rk["items"][0])
        self.assertNotIn("total", rk)          # 原始数值不下发，前端无从运算
        self.assertIn("disp", rk["unfilled"])

    def test_bad_inputs_400(self):
        for q in ({"start": "2026/03/01", "end": "2026-03-31"},
                  {"start": "2026-03-31", "end": "2026-03-01"},
                  {"start": "2025-01-01", "end": "2026-03-01"},
                  {"start": "", "end": ""}):
            r = self.anon.get("/api/daily", params=q)
            self.assertEqual(r.status_code, 400, q)

    def test_read_only_no_write_route(self):
        self.assertEqual(self.anon.post("/api/daily", json={}).status_code, 405)

    def test_top_param_full_ranking(self):
        """top=2000 拿全量（「其余点开看明细」用）：items 含全部名字、others 消失；top 越界被钳制不报错。"""
        r = self.anon.get("/api/daily", params={"start": "2026-03-01", "end": "2026-03-31", "top": "2000"})
        d = r.json()
        rk = d["rankings"]["orders_by_dept"]
        self.assertIsNone(rk["others"])
        self.assertEqual({i["name"] for i in rk["items"]}, {"部门A", "部门B"})
        r2 = self.anon.get("/api/daily", params={"start": "2026-03-01", "end": "2026-03-31", "top": "999999"})
        self.assertEqual(r2.status_code, 200)
        r3 = self.anon.get("/api/daily", params={"start": "2026-03-01", "end": "2026-03-31", "top": "1"})
        self.assertIsNotNone(r3.json()["rankings"]["orders_by_dept"]["others"])


class TestDailyFrontend(unittest.TestCase):
    def test_user_page_has_entry_and_no_math(self):
        """迭代17 批次A：板块③日期区常显、默认全年、「本年」在本月旁、跟顶钩子；无折叠入口。"""
        import assets, render
        cfg = loaders.load_config()
        today = loaders.pinned_today(cfg)
        lh, lr = loaders.load_ledger(cfg, str(today.year))
        summary = profit.build_summary(
            cfg, loaders.load_project_detail(cfg), loaders.load_orders(cfg),
            loaders.load_receipts(cfg), loaders.load_inhouse(cfg), lh, lr, today.year, today)
        html = render.render_dashboard(summary, cfg, assets.load_logo_base64(cfg))
        for token in ("dailyPanel", "/api/daily", "按时间段看", "rankViews", "rkCustom", "dailyClose",
                      "本年", "rkModal", "rk-more", 'data-kind="orders_by_dept"', "data-start=",
                      "_syncDailyDates", "restoreYear", "yearRange", "window.applyPeriod",
                      "orders_by_bu", "下单 · 按BU"):  # 时间段查询优先按 BU（与全年预渲染一致）
            self.assertIn(token, html, token)
        # 「本年」与「本月」同排在 daily-bar，不再挂在 card-h 右侧
        self.assertIn('id="dailyMonth"', html)
        self.assertIn('id="dailyClose"', html)
        self.assertNotIn("返回默认（年）", html)
        bar = html.split('class="daily-bar"')[1].split("</div>")[0]
        self.assertLess(bar.find("dailyMonth"), bar.find("dailyClose"))
        # 常显：面板不得默认 display:none；无折叠入口 dailyBtn
        self.assertNotIn('id="dailyPanel" style="display:none', html)
        self.assertNotIn("dailyBtn", html)
        self.assertNotIn("收起并还原", html)
        # 默认全年起止痕迹（数据年）
        y = str(summary["meta"]["year"])
        self.assertIn(f"{y}-01-01", html)  # yearRange / data-start 全年
        for bad in ("toFixed(", "parseFloat(", "parseInt("):
            self.assertNotIn(bad, html)

    def test_bu_page_has_no_daily_outlet(self):
        """铁律12：BU 页不得出现 /api/daily 与按时间段控件。"""
        import assets, render
        cfg = loaders.load_config()
        today = loaders.pinned_today(cfg)
        s = profit.build_bu_summary(
            cfg, loaders.load_project_detail(cfg), loaders.load_orders(cfg),
            loaders.load_receipts(cfg), loaders.load_inhouse(cfg), today, {"合成销售"})
        h = render.render_bu_page("合成BU", s, cfg, assets.load_logo_base64(cfg))
        for leak in ("/api/daily", "dailyPanel", "dailyBtn", "dailyClose", "dailyGo"):
            self.assertNotIn(leak, h, leak)


if __name__ == "__main__":
    unittest.main(verbosity=2)
