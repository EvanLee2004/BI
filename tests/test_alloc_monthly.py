#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代20 测试：公共费用按月比例分摊（人工填写页·可部分分摊）。
跑：.venv/bin/python tests/test_alloc_monthly.py

守卫点（明昊 2026-07-14 拍板）：
- db 写读：set/get/load 分摊比例；None=删行；0~100 校验
- 计算：逐月比例×当月公共池；部分分摊守恒（Σ各BU分摊 + 残留 == 公共池全额）；缺月=不摊
- 构成视图三处一致：公共条减、BU 条加、各条合计不变（防两处真相）
- 接口：仅管理员；未知 BU 拒；合计>100 拒（可<100）；月格式校验；C3 留痕
- UI 锚点：人工填写页分摊区块 + 设置页旧输入区已撤、留指路
"""

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import server
import db
import profit
import bu  # noqa: E402

TODAY = datetime.date(2026, 7, 15)
CATS = list(profit._LEDGER_TO_EXPENSE)


def _month_led(vals: dict[int, float]) -> dict:
    """构造 {(2026,m): 五类均分该月总额} 的公共池。"""
    out = {}
    for m, tot in vals.items():
        per = round(tot / len(CATS), 2)
        out[(2026, m)] = {c: per for c in CATS}
    return out


class TestDbAllocRatios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = loaders.load_config()
        self.conn = db.connect(self.cfg, Path(self.tmp))

    def tearDown(self):
        self.conn.close()

    def test_set_get_load_delete(self):
        db.set_alloc_ratio(self.conn, "2026-07", "游戏", 30, "t")
        db.set_alloc_ratio(self.conn, "2026-07", "数据", 20.55, "t")  # 四舍五入到 0.1
        db.set_alloc_ratio(self.conn, "2026-06", "游戏", 50, "t")
        self.assertEqual(db.get_alloc_ratios(self.conn, "2026-07"), {"游戏": 30.0, "数据": 20.6})
        allr = db.load_alloc_ratios(self.conn)
        self.assertEqual(set(allr), {"2026-07", "2026-06"})
        db.set_alloc_ratio(self.conn, "2026-07", "数据", None, "t")  # None=删行
        self.assertEqual(db.get_alloc_ratios(self.conn, "2026-07"), {"游戏": 30.0})

    def test_range_guard(self):
        with self.assertRaises(ValueError):
            db.set_alloc_ratio(self.conn, "2026-07", "游戏", 120, "t")
        with self.assertRaises(ValueError):
            db.set_alloc_ratio(self.conn, "", "游戏", 10, "t")


class TestAllocMath(unittest.TestCase):
    def test_partial_alloc_conserves(self):
        """部分分摊守恒：Σ各BU分摊 + 残留 == 公共池全额（当月）。"""
        led = _month_led({7: 1000.0})
        ratios = {"2026-07": {"游戏": 30, "数据": 20}}
        per = profit.alloc_amounts_by_period(led, ratios, ["游戏", "数据"], TODAY)
        # 找 7 月周期
        m7 = next(v for k, v in per.items() if "7月" in k)
        total_alloc = sum(m7.values())
        pool = sum(led[(2026, 7)].values())
        self.assertAlmostEqual(m7["游戏"], pool * 0.30, places=1)
        self.assertAlmostEqual(m7["数据"], pool * 0.20, places=1)
        self.assertAlmostEqual(total_alloc + pool * 0.50, pool, places=1)  # 残留 50%

    def test_missing_month_no_alloc(self):
        led = _month_led({6: 500.0, 7: 1000.0})
        ratios = {"2026-07": {"游戏": 40}}  # 6 月没填=不摊
        per = profit.alloc_amounts_by_period(led, ratios, ["游戏"], TODAY)
        m6 = [v for k, v in per.items() if k.endswith("6月")]
        self.assertTrue(all("游戏" not in v or v["游戏"] == 0 for v in m6) or not m6)
        year_key = [k for k in per if k.endswith("年")]
        if year_key:  # 全年=只含 7 月那份
            self.assertAlmostEqual(per[year_key[0]]["游戏"], 1000.0 * 0.40, places=1)

    def test_orphan_bu_ignored(self):
        led = _month_led({7: 1000.0})
        ratios = {"2026-07": {"游戏": 30, "不存在BU": 50}}
        per = profit.alloc_amounts_by_period(led, ratios, ["游戏"], TODAY)
        for v in per.values():
            self.assertNotIn("不存在BU", v)

    def test_monthly_ratio_varies(self):
        """比例按月可不同：6 月 10%、7 月 40%，年周期=各月各自比例之和。"""
        led = _month_led({6: 500.0, 7: 1000.0})
        ratios = {"2026-06": {"游戏": 10}, "2026-07": {"游戏": 40}}
        per = profit.alloc_amounts_by_period(led, ratios, ["游戏"], TODAY)
        yk = next(k for k in per if k.endswith("年"))
        self.assertAlmostEqual(per[yk]["游戏"], 500 * 0.10 + 1000 * 0.40, places=1)


class TestPcViewConsistency(unittest.TestCase):
    def test_view_moves_with_alloc_total_unchanged(self):
        """构成视图三处一致：公共条减、BU 条加正数行、各条合计一分不变。"""
        groups = [("公共", 1000.0, [("房租", 800.0), ("水电", 200.0)]), ("游戏", 300.0, [("差旅", 300.0)])]
        out = profit.apply_alloc_to_pc_view(groups, {"游戏": 300.0, "数据": 200.0})
        gm = {g: (t, dict(f)) for g, t, f in out}
        self.assertAlmostEqual(gm["公共"][0], 500.0)
        self.assertAlmostEqual(gm["游戏"][0], 600.0)
        self.assertAlmostEqual(gm["数据"][0], 200.0)  # 无直记 BU 也出现
        self.assertEqual(gm["游戏"][1][profit.ALLOC_IN_LABEL], 300.0)
        self.assertEqual(gm["公共"][1][profit.ALLOC_OUT_LABEL], -500.0)
        # 总额守恒
        self.assertAlmostEqual(sum(t for _, t, _ in out), sum(t for _, t, _ in groups))
        # 组内细类合计==组合计
        for g, t, f in out:
            self.assertAlmostEqual(sum(v for _, v in f), t, places=1, msg=g)

    def test_no_public_group_untouched(self):
        groups = [("游戏", 300.0, [("差旅", 300.0)])]
        self.assertEqual(profit.apply_alloc_to_pc_view(groups, {"游戏": 100.0}), groups)
        self.assertIsNone(profit.apply_alloc_to_pc_view(None, {"游戏": 1.0}))


class TestBuSummaryMonthlyAlloc(unittest.TestCase):
    def test_apply_monthly_into_bu_summary(self):
        """按月分摊叠进 BU summary：费用/税前联动；无比例月不动。"""
        p = {
            "range": ("2026-07-01", "2026-07-31"),
            "manual": {},
            "ledger_expenses": {c: 0.0 for c in CATS},
            "gross_profit": 1000.0,
            "surtax": 0.0,
            "other_pl": 0.0,
            "revenue_net": 2000.0,
            "expense": {"total": 0.0},
        }
        s = {"periods": {"2026年7月": p}, "meta": {}}
        led = _month_led({7: 1000.0})
        profit.apply_public_expense_allocation_monthly(s, led, {"2026-07": {"游戏": 30}}, "游戏", TODAY)
        self.assertTrue(s["meta"]["public_allocation"]["enabled"])
        self.assertEqual(s["meta"]["public_allocation"]["mode"], "monthly")
        self.assertAlmostEqual(p["expense"]["total"], 300.0, places=1)
        self.assertAlmostEqual(p["pretax_profit"], 700.0, places=1)

    def test_no_ratio_disabled(self):
        p = {
            "range": ("2026-07-01", "2026-07-31"),
            "manual": {},
            "ledger_expenses": {c: 0.0 for c in CATS},
            "gross_profit": 1000.0,
            "surtax": 0.0,
            "other_pl": 0.0,
            "revenue_net": 2000.0,
            "expense": {"total": 0.0},
        }
        s = {"periods": {"2026年7月": p}, "meta": {}}
        profit.apply_public_expense_allocation_monthly(s, _month_led({7: 1000.0}), {}, "游戏", TODAY)
        self.assertFalse(s["meta"]["public_allocation"]["enabled"])
        self.assertEqual(p["expense"]["total"], 0.0)


class TestAllocApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        bu.save_bu_config(
            cls.cfg,
            cls.root,
            [
                {"name": "游戏", "销售": ["销售A"]},
                {"name": "数据", "销售": ["销售B"]},
            ],
        )
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None, **k: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "<html>ADMIN</html>"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def test_requires_login(self):
        self.assertEqual(self.anon.get("/api/alloc_ratios?month=2026-07").status_code, 401)
        self.assertEqual(self.anon.post("/api/alloc_ratios", json={}).status_code, 401)

    def test_month_format_guard(self):
        r = self.client.get("/api/alloc_ratios?month=202607", headers=self.hdr)
        self.assertEqual(r.status_code, 400)

    def test_save_and_readback_and_partial_sum(self):
        r = self.client.post(
            "/api/alloc_ratios", headers=self.hdr, json={"归属月": "2026-07", "ratios": {"游戏": 30, "数据": 20}}
        )
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["ratios"], {"游戏": 30.0, "数据": 20.0})
        self.assertAlmostEqual(d["sum_pct"], 50.0)
        self.assertAlmostEqual(d["remain_pct"], 50.0)  # 可 <100%
        g = self.client.get("/api/alloc_ratios?month=2026-07", headers=self.hdr).json()
        self.assertEqual(g["bus"], ["游戏", "数据"])  # 与设置页 BU 同源
        # None=删行
        r2 = self.client.post(
            "/api/alloc_ratios", headers=self.hdr, json={"归属月": "2026-07", "ratios": {"数据": None}}
        )
        self.assertEqual(r2.json()["ratios"], {"游戏": 30.0})

    def test_reject_unknown_bu_and_over_100(self):
        r = self.client.post("/api/alloc_ratios", headers=self.hdr, json={"归属月": "2026-08", "ratios": {"野BU": 10}})
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post(
            "/api/alloc_ratios", headers=self.hdr, json={"归属月": "2026-08", "ratios": {"游戏": 60, "数据": 50}}
        )
        self.assertEqual(r2.status_code, 400)
        self.assertIn("100", r2.json()["detail"])

    def test_audit_logged(self):
        self.client.post("/api/alloc_ratios", headers=self.hdr, json={"归属月": "2026-05", "ratios": {"游戏": 15}})
        conn = db.connect(self.cfg, self.root)
        try:
            rows = conn.execute("SELECT 摘要 FROM manual_配置变更 WHERE 类别='分摊'").fetchall()
        finally:
            conn.close()
        self.assertTrue(any("2026-05" in r[0] for r in rows))

    def test_ui_anchors(self):
        html = server.admin_ui_source()
        self.assertIn("公共费用分摊", html)
        self.assertIn("buAllocLegacy", html)
        self.assertNotIn("buAllocRows", html)



if __name__ == "__main__":
    unittest.main(verbosity=2)
