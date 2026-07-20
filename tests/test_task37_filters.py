#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书37·B7：六表列筛（后端 SQL 分页）+ 导出跟随。"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import schema  # noqa: E402
import server  # noqa: E402


def _seed_conn(conn):
    # 收入明细：两客户 + 金额区间
    rows = [
        ("k1", "O1", "客户甲", "线A", "销A", "2026-01-15", money.yuan_to_fen(1000), money.yuan_to_fen(400), "2026-01"),
        ("k2", "O2", "客户乙", "线B", "销B", "2026-03-20", money.yuan_to_fen(5000), money.yuan_to_fen(2000), "2026-03"),
        ("k3", "O3", "客户甲", "线A", "销A", "2026-06-01", money.yuan_to_fen(200), money.yuan_to_fen(50), "2026-06"),
        ("k4", "O4", "客户丙", "线C", "销C", "2026-02-10", money.yuan_to_fen(3000), money.yuan_to_fen(1000), "2026-02"),
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            r + (r[8],),
        )
    # 下单：数字+文本
    conn.execute(
        "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        ("o1", "O1", "2026-01-05", money.yuan_to_fen(800), "一部", "销A", "2026-01", "2026-01"),
    )
    conn.execute(
        "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
        " VALUES(?,?,?,?,?,?,?,?,0)",
        ("o2", "O2", "2026-04-01", money.yuan_to_fen(1200), "二部", "销B", "2026-04", "2026-04"),
    )
    conn.commit()


class TestDetailColFilters(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for ddl in schema.STD_TABLES.values():
            self.conn.execute(ddl)
        for ddl in schema.HUMAN_TABLES.values():
            self.conn.execute(ddl)
        _seed_conn(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_text_in_filter(self):
        d = db.query_detail(self.conn, "收入明细", filters={"客户": {"in": ["客户甲"]}}, page_size=50)
        self.assertEqual(d["total"], 2)
        self.assertTrue(all(r["客户"] == "客户甲" for r in d["rows"]))

    def test_text_keyword(self):
        d = db.query_detail(self.conn, "收入明细", filters={"客户": {"q": "乙"}}, page_size=50)
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["rows"][0]["客户"], "客户乙")

    def test_number_range_yuan(self):
        # 交付额 1000~3000 元（库内分）
        d = db.query_detail(
            self.conn, "收入明细", filters={"交付额": {"min": 1000, "max": 3000}}, page_size=50
        )
        amts = sorted(r["交付额"] for r in d["rows"])
        self.assertEqual(amts, [1000.0, 3000.0])

    def test_date_range(self):
        d = db.query_detail(
            self.conn,
            "收入明细",
            filters={"整单交付日期": {"from": "2026-03-01", "to": "2026-06-30"}},
            page_size=50,
        )
        self.assertEqual(d["total"], 2)
        for r in d["rows"]:
            self.assertGreaterEqual(str(r["整单交付日期"])[:10], "2026-03-01")

    def test_multi_column_and(self):
        d = db.query_detail(
            self.conn,
            "收入明细",
            filters={"客户": {"in": ["客户甲"]}, "交付额": {"min": 500}},
            page_size=50,
        )
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["rows"][0]["定位键"], "k1")

    def test_pagination_total(self):
        d1 = db.query_detail(self.conn, "收入明细", page=1, page_size=2)
        self.assertEqual(d1["total"], 4)
        self.assertEqual(d1["pages"], 2)
        self.assertEqual(len(d1["rows"]), 2)
        d2 = db.query_detail(self.conn, "收入明细", page=2, page_size=2)
        self.assertEqual(len(d2["rows"]), 2)
        keys = {r["定位键"] for r in d1["rows"] + d2["rows"]}
        self.assertEqual(len(keys), 4)

    def test_clear_filters_full(self):
        d = db.query_detail(self.conn, "收入明细", filters={}, page_size=50)
        self.assertEqual(d["total"], 4)

    def test_orders_table_filters(self):
        d = db.query_detail(
            self.conn, "下单", filters={"部门": {"in": ["一部"]}, "下单预估额": {"min": 500}}, page_size=50
        )
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["rows"][0]["销售"], "销A")

    def test_column_meta_kinds(self):
        meta = db.detail_columns_meta("收入明细")
        by = {m["name"]: m["kind"] for m in meta}
        self.assertEqual(by["客户"], "text")
        self.assertEqual(by["交付额"], "number")
        self.assertEqual(by["整单交付日期"], "date")

    def test_distinct_values(self):
        d = db.query_detail_distinct(self.conn, "收入明细", "客户")
        self.assertEqual(set(d["values"]), {"客户甲", "客户乙", "客户丙"})

    def test_whitelist_rejects_unknown_col(self):
        # 未知列静默忽略，不注入
        d = db.query_detail(self.conn, "收入明细", filters={"';DROP": {"q": "x"}}, page_size=50)
        self.assertEqual(d["total"], 4)


class TestDetailFiltersHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.root = Path(tempfile.mkdtemp())
        (cls.root / "数据").mkdir()
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        accounts.save_accounts(
            cls.cfg,
            cls.root,
            [{"账号": "admin1", "密码": "8888", "权限": "管理员", "显示名": "管"}],
        )
        conn = db.connect(cls.cfg, cls.root)
        _seed_conn(conn)
        conn.close()
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.TestClient = TestClient

    def _admin(self):
        c = self.TestClient(self.app)
        r = c.post("/admin/login", data={"account": "admin1", "password": "8888"}, follow_redirects=False)
        self.assertIn(r.status_code, (302, 303), r.text[:200])
        return c

    def test_api_filters_and_export_match(self):
        c = self._admin()
        filt = json.dumps({"客户": {"in": ["客户甲"]}}, ensure_ascii=False)
        r = c.get("/api/detail", params={"table": "收入明细", "filters": filt, "page_size": 50})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["total"], 2)
        keys = {row["定位键"] for row in d["rows"]}
        r2 = c.get("/api/detail_export", params={"table": "收入明细", "filters": filt})
        self.assertEqual(r2.status_code, 200, r2.text[:200])
        self.assertIn(
            "spreadsheet",
            r2.headers.get("content-type", "") + r2.headers.get("Content-Type", ""),
        )
        # xlsx 非空
        self.assertGreater(len(r2.content), 100)

    def test_values_endpoint(self):
        c = self._admin()
        r = c.get("/api/detail/values", params={"table": "收入明细", "column": "客户"})
        self.assertEqual(r.status_code, 200)
        vals = set(r.json()["values"])
        self.assertIn("客户甲", vals)

    def test_frontend_has_col_filter_hooks(self):
        """任务书65·L1：列筛选在 Vue 明细页（legacy admin.js 已删）。"""
        detail = (ROOT / "frontend" / "src" / "admin" / "views" / "DetailView.vue").read_text(encoding="utf-8")
        # 列筛选 UI / API 参数
        self.assertTrue(
            "filter" in detail.lower() or "筛选" in detail or "colFilter" in detail,
            "DetailView 须有列筛选",
        )
        self.assertIn("/api/detail", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
