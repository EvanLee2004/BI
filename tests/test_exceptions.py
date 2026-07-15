#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.4 异常处理中心测试：排名（未填）置底拆分 / 下单未填部门清单 / 总览计数 / 接口鉴权与路由。
跑：.venv/bin/python tests/test_exceptions.py

守卫点（迭代计划13批次A）：
- 清单口径 == 排名「（未填）」口径（同一 WHERE，一处改两边同步）
- 守恒：items+others+unfilled 合计 == total（置底不藏行不改总额）
- 处理一条（部门补上）→ 清单和排名（未填）两边同步减
- 「复核」改名「异常处理」后各页签路由可达
"""

import datetime
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db, loaders, profit, render, server  # noqa: E402


def _seed_orders(cfg, root):
    conn = db.connect(cfg, root)
    rows = [
        # 定位键, 订单号, 日期, 金额, 部门, 销售, 已删除
        ("O1", "SO1", "2026-03-01", 1000.0, "部门B", "张三", 0),
        ("O2", "SO2", "2026-03-05", 2000.0, "", "李四", 0),  # 未填部门
        ("O3", "SO3", "2026-04-02", 3000.0, None, "王五", 0),  # 未填部门(NULL)
        ("O4", "SO4", "2026-04-03", 0.0, "", "赵六", 0),  # 金额0 → 不算异常
        ("O5", "SO5", "2026-04-04", 500.0, "  ", "钱七", 0),  # 空白 → 未填
        ("O6", "SO6", "2026-04-05", 800.0, "", "孙八", 1),  # 已删除 → 排除
        ("O7", "SO7", "2026-05-06", 4000.0, "部门A", "周九", 0),
    ]
    for k, o, d, a, dep, sal, rm in rows:
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (k, o, d, a, dep, sal, d[:7], d[:7], rm),
        )
    conn.commit()
    return conn


class TestRankingUnfilled(unittest.TestCase):
    """profit.compute_ranking：（未填）拆分置底 + 守恒。"""

    ROWS = [
        {"下单日期": "2026-03-01", "下单预估额": 1000.0, "部门": "部门B"},
        {"下单日期": "2026-03-05", "下单预估额": 2000.0, "部门": ""},
        {"下单日期": "2026-04-02", "下单预估额": 3000.0, "部门": None},
        {"下单日期": "2026-05-06", "下单预估额": 4000.0, "部门": "部门A"},
    ]

    def _rk(self, top=10):
        return profit.compute_ranking(
            self.ROWS, "部门", "下单预估额", "下单日期", datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), top=top
        )

    def test_unfilled_separated_from_items(self):
        rk = self._rk()
        names = [it["name"] for it in rk["items"]]
        self.assertNotIn("（未填）", names)
        self.assertEqual(rk["unfilled"], {"amount": 5000.0, "count": 2})

    def test_conservation_items_others_unfilled_eq_total(self):
        rk = self._rk(top=1)  # 逼出 others
        s = sum(it["amount"] for it in rk["items"])
        s += (rk["others"] or {}).get("amount", 0)
        s += (rk["unfilled"] or {}).get("amount", 0)
        self.assertAlmostEqual(s, rk["total"], places=2)
        self.assertEqual(rk["total"], 10000.0)

    def test_no_unfilled_is_none(self):
        rows = [r for r in self.ROWS if (r["部门"] or "").strip()]
        rk = profit.compute_ranking(
            rows, "部门", "下单预估额", "下单日期", datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
        )
        self.assertIsNone(rk["unfilled"])

    def test_render_hides_unfilled_on_user_page(self):
        """用户端排名卡不展示「（未填）」——归类只在管理端异常处理。"""
        html = render._rank_card("下单 · 按部门", "测", self._rk())
        self.assertNotIn("rk-unfilled", html)
        self.assertNotIn("待归类", html)
        self.assertNotIn("（未填）", html)
        self.assertIn("部门A", html)  # 正常排名仍在

    def test_render_only_unfilled_shows_empty(self):
        """仅有未填、无正式 items → 用户端显示本期无数据（不露未填行）。"""
        rk = {"items": [], "others": None, "unfilled": {"amount": 9.0, "count": 1}, "total": 9.0}
        html = render._rank_card("下单 · 按部门", "测", rk)
        self.assertNotIn("rk-unfilled", html)
        self.assertIn("本期无数据", html)


class TestUnfilledDeptQueries(unittest.TestCase):
    """db 层：清单查询 / 部门清单 / 总览计数 / 与排名口径一致。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.cfg = loaders.load_config()
        self.conn = _seed_orders(self.cfg, self.root)

    def tearDown(self):
        self.conn.close()

    def test_query_unfilled_dept_rows(self):
        d = db.query_detail(self.conn, "下单", unfilled_dept=True)
        self.assertEqual(d["total"], 3)  # O2/O3/O5；O4金额0、O6已删 排除
        self.assertEqual({r["订单号"] for r in d["rows"]}, {"SO2", "SO3", "SO5"})

    def test_unfilled_dept_wrong_table_rejected(self):
        with self.assertRaises(KeyError):
            db.query_detail(self.conn, "回款", unfilled_dept=True)

    def test_list_order_depts(self):
        self.assertEqual(db.list_order_depts(self.conn), ["部门A", "部门B"])

    def test_exceptions_summary_counts(self):
        ex = db.exceptions_summary(self.conn)
        self.assertEqual(ex["order_unfilled_dept"], 3)
        self.assertEqual(ex["expense_unclassified"], 0)
        self.assertEqual(ex["adjust_expired"], 0)
        self.assertEqual(ex["adjust_missing"], 0)

    def test_list_matches_ranking_unfilled(self):
        """清单口径 == 排名（未填）口径（金额0那笔：清单不列，但排名计1笔0元——共用非零条件故一致）。"""
        rows = db.load_orders(self.cfg, self.conn)
        rk = profit.compute_ranking(
            rows,
            "部门",
            self.cfg["columns"]["order_amount"],
            self.cfg["columns"]["order_date"],
            datetime.date(2026, 1, 1),
            datetime.date(2026, 12, 31),
        )
        d = db.query_detail(self.conn, "下单", unfilled_dept=True)
        amt = sum(r["下单预估额"] for r in d["rows"])
        self.assertAlmostEqual(amt, rk["unfilled"]["amount"], places=2)

    def test_fix_one_both_sides_drop(self):
        """处理一条（部门补上）→ 清单 total 与排名 unfilled 同步减。"""
        self.conn.execute("UPDATE std_下单 SET 部门='Video' WHERE 定位键='O2'")
        self.conn.commit()
        self.assertEqual(db.query_detail(self.conn, "下单", unfilled_dept=True)["total"], 2)
        rows = db.load_orders(self.cfg, self.conn)
        rk = profit.compute_ranking(
            rows,
            "部门",
            self.cfg["columns"]["order_amount"],
            self.cfg["columns"]["order_date"],
            datetime.date(2026, 1, 1),
            datetime.date(2026, 12, 31),
        )
        self.assertEqual(rk["unfilled"]["count"], 3)  # O3/O5 + O4（0元也算1笔，金额守恒不受影响）
        self.assertAlmostEqual(rk["unfilled"]["amount"], 3500.0, places=2)

    def test_adjust_dept_field_allowed(self):
        """「部门」在可调字段白名单内（R1 黑名单制），异常处理归类走 /api/adjust 的前提。"""
        self.assertIn("部门", db.adjustable_fields()["下单"])


def ex_count(rk):
    return (rk.get("unfilled") or {}).get("count", 0)


class TestExceptionEndpoints(unittest.TestCase):
    """接口：鉴权 + 数据 + 改名后路由可达。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        _seed_orders(cls.cfg, cls.root).close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None: server._state.__setitem__("built_at", "RECOMPUTED")
        server._state["user_html"] = "<html>USER</html>"
        server._state["admin_html"] = "ready"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.anon = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        cls.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def test_endpoints_require_login(self):
        for p in ("/api/exceptions", "/api/order_depts", "/api/detail?table=%E4%B8%8B%E5%8D%95&unfilled_dept=1"):
            self.assertEqual(self.anon.get(p).status_code, 401, p)

    def test_exceptions_summary_endpoint(self):
        ex = self.client.get("/api/exceptions", headers=self.hdr).json()
        self.assertEqual(ex["order_unfilled_dept"], 3)
        for k in ("expense_unclassified", "adjust_expired", "adjust_missing"):
            self.assertIn(k, ex)

    def test_order_depts_endpoint(self):
        self.assertEqual(self.client.get("/api/order_depts", headers=self.hdr).json(), ["部门A", "部门B"])

    def test_detail_unfilled_dept_endpoint(self):
        d = self.client.get("/api/detail", params={"table": "下单", "unfilled_dept": "1"}, headers=self.hdr).json()
        self.assertEqual(d["total"], 3)

    def test_detail_unfilled_dept_wrong_table_400(self):
        r = self.client.get("/api/detail", params={"table": "回款", "unfilled_dept": "1"}, headers=self.hdr)
        self.assertEqual(r.status_code, 400)

    def test_admin_console_renamed_tabs(self):
        html = self.client.get("/admin", headers=self.hdr).text
        for t in ("异常处理", "总览", "下单未填部门", "费用未分类（台账）", "数据修正", "历史快照", "配置变更记录"):
            self.assertIn(t, html)
        self.assertNotIn(">复核<", html)

    def test_adjust_dept_via_api(self):
        """异常处理归类的完整写链：POST /api/adjust 部门改值 → 记录入台账。"""
        r = self.client.post(
            "/api/adjust",
            headers=self.hdr,
            json={
                "目标表": "std_下单",
                "定位键": "O3",
                "字段": "部门",
                "新值": "部门A",
                "原因": "异常处理·归类部门",
                "类型": "改值",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        adjs = self.client.get("/api/adjustments", headers=self.hdr).json()
        a = [x for x in adjs if x["定位键"] == "O3"][0]
        self.assertEqual((a["字段"], a["新值"], a["状态"]), ("部门", "部门A", "生效"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
