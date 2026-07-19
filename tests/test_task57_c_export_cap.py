#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 page_size 不得被 500 静默截断——真调 query_detail 路径。"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import schema  # noqa: E402
from db import detail  # noqa: E402


class TestExportCap(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for ddl in schema.STD_TABLES.values():
            self.conn.execute(ddl)
        n = 520
        for i in range(n):
            self.conn.execute(
                """
                INSERT INTO std_费用明细(
                  定位键, 收单月份, 收单日期, 含税金额, 对应报表大类, 事项, 业务员, 业务BU, 归属月, 已删除
                ) VALUES (?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    f"k{i:04d}",
                    "2026-01",
                    "2026-01-15",
                    100,
                    "管理费用",
                    f"事项{i}",
                    "测",
                    "",
                    "2026-01",
                ),
            )
        self.conn.commit()
        self.n = n

    def tearDown(self):
        self.conn.close()

    def test_list_default_cap_500(self):
        """列表默认 max_page_size=500：请求 5000 仍夹成 500。"""
        out = detail.query_detail(
            self.conn,
            "费用明细",
            page=1,
            page_size=5000,
            audience="view",
        )
        self.assertEqual(out.get("page_size"), 500)
        self.assertEqual(len(out["rows"]), 500)
        self.assertGreaterEqual(out["total"], self.n)

    def test_export_max_page_size_5000_not_clamped(self):
        """导出：page_size=5000 + max_page_size=5000 → 返回全部 520 行，不被夹 500。"""
        out = detail.query_detail(
            self.conn,
            "费用明细",
            page=1,
            page_size=5000,
            audience="view",
            max_page_size=5000,
        )
        # page_size 字段若存在应反映 cap 后请求值
        if "page_size" in out:
            self.assertEqual(out["page_size"], 5000)
        self.assertEqual(len(out["rows"]), self.n, f"rows={len(out['rows'])} expected {self.n}")
        self.assertGreater(len(out["rows"]), 500)
        self.assertEqual(out["total"], self.n)


if __name__ == "__main__":
    unittest.main()
