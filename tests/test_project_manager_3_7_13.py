# -*- coding: utf-8 -*-
"""3.7.13 A1：收入明细「项目经理」入库 + 管理端只读列 + 兼容迁移。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import schema  # noqa: E402
from ingest import normalize  # noqa: E402


class TestNormProjectManager(unittest.TestCase):
    """normalize 读「项目经理」，空则回退「PM」。"""

    def test_project_manager_column(self):
        c = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额",
            "project_cost": "项目成本",
            "project_line": "业务线",
        }
        rows = [
            {
                "订单号": "SO-PM-1",
                "SOD": "SOD-PM-1",
                "客户": "客甲",
                "业务线": "语言",
                "销售": "销甲",
                "项目经理": "张三",
                "整单交付日期": "2026-06-01",
                "交付额": "1000",
                "项目成本": "200",
            }
        ]
        out = normalize.norm_project_detail(rows, c)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["项目经理"], "张三")
        self.assertEqual(out[0]["订单号"], "SO-PM-1")

    def test_pm_fallback_when_project_manager_empty(self):
        c = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额",
            "project_cost": "项目成本",
            "project_line": "业务线",
        }
        rows = [
            {
                "订单号": "SO-PM-2",
                "SOD": "SOD-PM-2",
                "客户": "客乙",
                "业务线": "语言",
                "销售": "销乙",
                "项目经理": "",
                "PM": "李四",
                "整单交付日期": "2026-06-02",
                "交付额": "500",
                "项目成本": "100",
            }
        ]
        out = normalize.norm_project_detail(rows, c)
        self.assertEqual(out[0]["项目经理"], "李四")

    def test_both_empty_is_blank(self):
        c = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额",
            "project_cost": "项目成本",
        }
        rows = [
            {
                "订单号": "SO-PM-3",
                "SOD": "SOD-PM-3",
                "客户": "客丙",
                "整单交付日期": "2026-06-03",
                "交付额": "1",
                "项目成本": "0",
            }
        ]
        out = normalize.norm_project_detail(rows, c)
        self.assertEqual(out[0]["项目经理"], "")


class TestSchemaAndDetailPm(unittest.TestCase):
    def test_ddl_and_add_column_and_not_adjustable(self):
        self.assertIn("项目经理", schema.STD_TABLES["std_收入明细"])
        add_names = [n for n, _ in schema._ADD_COLUMNS.get("std_收入明细", [])]
        self.assertIn("项目经理", add_names)
        # 只读：不在可调字段
        self.assertNotIn("项目经理", schema.ADJUSTABLE_FIELDS.get("std_收入明细", ()))
        self.assertIn("项目经理", schema.NON_ADJUSTABLE)

    def test_old_db_migrate_adds_column(self):
        """存量库无列时 create_all/_ensure_columns 补列。"""
        conn = sqlite3.connect(":memory:")
        # 故意建旧表（无项目经理）；其余表用 create_all 齐备
        conn.execute(
            """
            CREATE TABLE std_收入明细 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                定位键 TEXT, 订单号 TEXT, 客户 TEXT, 业务线 TEXT, 销售 TEXT,
                整单交付日期 TEXT, 交付额 INTEGER, 项目成本 INTEGER,
                归属月 TEXT, 原值_交付日期 TEXT, 原值_归属月 TEXT,
                已删除 INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        have0 = {r[1] for r in conn.execute("PRAGMA table_info(std_收入明细)")}
        self.assertNotIn("项目经理", have0)
        # create_all 幂等建其余表 + _ensure_columns 给旧表补列
        schema.create_all(conn)
        have1 = {r[1] for r in conn.execute("PRAGMA table_info(std_收入明细)")}
        self.assertIn("项目经理", have1)
        conn.close()

    def test_detail_columns_include_pm(self):
        from db.constants import DETAIL_TABLES

        cols = DETAIL_TABLES["收入明细"][1]
        self.assertIn("项目经理", cols)

    def test_insert_and_query_detail_has_pm(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "数据").mkdir()
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["db_path"] = "看板.db"
        conn = db.connect(cfg, tmp)
        schema.create_all(conn)
        # 经 insert_std_records 路径写一行
        import db_write

        db_write.insert_std_records(
            conn,
            "std_收入明细",
            [
                {
                    "定位键": "SOD-PM-X",
                    "订单号": "SO-X",
                    "客户": "客X",
                    "业务线": "语言",
                    "销售": "销X",
                    "项目经理": "王五",
                    "整单交付日期": "2026-06-10",
                    "交付额": 100.0,
                    "项目成本": 20.0,
                    "归属月": "2026-06",
                    "原值_交付日期": "2026-06-10",
                    "原值_归属月": "2026-06",
                }
            ],
        )
        conn.commit()
        d = db.query_detail(conn, "收入明细", page=1, page_size=50, audience="admin")
        self.assertIn("项目经理", d["columns"])
        self.assertGreaterEqual(d["total"], 1)
        hit = next((r for r in d["rows"] if r.get("定位键") == "SOD-PM-X"), None)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("项目经理"), "王五")
        conn.close()


if __name__ == "__main__":
    unittest.main()
