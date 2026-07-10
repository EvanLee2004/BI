#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.5 按天明细测试（迭代计划13批次B）：compute_daily 守恒/边界 + /api/daily 只读接口校验 + 前端入口。
跑：.venv/bin/python tests/test_daily.py

守卫点：
- ∑按天 == compute_orders/compute_receipts 同区间合计（守恒红线）
- 空区间/单日边界/非法入参（格式/顺序/超366天）
- 接口纯只读：POST /api/daily 不存在（405）；公开可访问（与用户页同级）
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
        cls.anon = TestClient(cls.app, follow_redirects=False)   # 不登录：接口是公开的

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


class TestDailyFrontend(unittest.TestCase):
    def test_user_page_has_entry_and_no_math(self):
        import assets, render
        cfg = loaders.load_config()
        today = loaders.pinned_today(cfg)
        lh, lr = loaders.load_ledger(cfg, str(today.year))
        summary = profit.build_summary(
            cfg, loaders.load_project_detail(cfg), loaders.load_orders(cfg),
            loaders.load_receipts(cfg), loaders.load_inhouse(cfg), lh, lr, today.year, today)
        html = render.render_dashboard(summary, cfg, assets.load_logo_base64(cfg))
        for token in ("dailyBtn", "dailyPanel", "/api/daily", "按天明细"):
            self.assertIn(token, html, token)
        for bad in ("toFixed(", "parseFloat(", "parseInt("):
            self.assertNotIn(bad, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
