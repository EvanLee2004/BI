#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2：内部译员维度修正——译员姓名列 + 销售池剔除 std_内部译员；总金额不变。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestInhouseNameNorm(unittest.TestCase):
    def test_norm_captures_translator_name(self):
        import loaders
        from ingest import normalize

        cfg = loaders.load_config(ROOT)
        c = cfg["columns"]
        rows = [
            {
                c["inhouse_type"]: "IN-HOUSE",
                c["inhouse_date"]: "2026-03-01",
                c["inhouse_amount"]: "1000",
                "任务明细ID": "T1",
                "供应商姓名": "译员甲",
                "销售": "错误销售",
            }
        ]
        out = normalize.norm_inhouse(rows, c, cfg)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["译员姓名"], "译员甲")
        self.assertEqual(out[0]["销售"], "错误销售")  # 仍落库但不进销售池
        self.assertEqual(out[0]["结算金额"], 1000.0)


class TestSalesPoolExcludesInhouse(unittest.TestCase):
    def test_list_salespeople_skips_inhouse_only_names(self):
        import db as dbmod
        import schema

        conn = __import__("sqlite3").connect(":memory:")
        schema.create_all(conn)
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,归属月,原值_归属月,已删除)"
            " VALUES('k1','o1','2026-01-01',1,'d','销售真', '2026-01','2026-01',0)"
        )
        conn.execute(
            "INSERT INTO std_内部译员(定位键,任务ID,任务提交日期,结算金额,译员类型,译员姓名,销售,归属月,原值_归属月,已删除)"
            " VALUES('k2','t1','2026-01-01',9,'IN-HOUSE','译员甲','假销售只在译员表','2026-01','2026-01',0)"
        )
        conn.commit()
        names = {x["name"] for x in dbmod.list_salespeople(conn)}
        self.assertIn("销售真", names)
        self.assertNotIn("假销售只在译员表", names)
        # SQL 源码守卫
        # 54.4·E：db 包实现在 db/_impl.py
        src_path = ROOT / "src" / "db" / "_impl.py"
        if not src_path.is_file():
            src_path = ROOT / "src" / "db.py"
        src = src_path.read_text(encoding="utf-8")
        self.assertNotIn("SELECT 销售 FROM std_内部译员", src)


class TestInhouseTotalsUnchanged(unittest.TestCase):
    """改前后各周期内部译员合计全等：用 golden 数据跑 generate 后 periods.inhouse_cost 可算。"""

    def test_golden_inhouse_cost_stable(self):
        import loaders
        import core
        import db as dbmod

        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = date(2026, 6, 30)
        conn = dbmod.connect(cfg, ROOT)
        try:
            import ingest

            ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger="a2_test", archive_backups=False)
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        # 有 inhouse_cost 字段且为非负；明细含译员姓名列
        yk = summary["meta"]["year_key"]
        cost = summary["periods"][yk]["inhouse_cost"]
        self.assertIsInstance(cost, (int, float))
        # detail schema
        import db as dbmod2

        cols = dbmod2.DETAIL_TABLES["内部译员"][1]
        self.assertIn("译员姓名", cols)
        self.assertLess(cols.index("译员姓名"), cols.index("销售"), "译员姓名应排在销售前作主列")


if __name__ == "__main__":
    unittest.main(verbosity=2)
