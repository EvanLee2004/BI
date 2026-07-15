#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33·A3：金额整数分（Decimal 进料、库内分、读回元、迁移幂等）。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import money  # noqa: E402
import schema  # noqa: E402
from ingest import adjust  # noqa: E402


class TestYuanFenConvert(unittest.TestCase):
    def test_half_up_and_extremes(self):
        self.assertEqual(money.yuan_to_fen("0.005"), 1)  # 0.5 分 → 1 分
        self.assertEqual(money.yuan_to_fen("0.004"), 0)
        self.assertEqual(money.yuan_to_fen("0.015"), 2)
        self.assertEqual(money.yuan_to_fen(-1.23), -123)
        self.assertEqual(money.yuan_to_fen("1,234.56"), 123456)
        self.assertEqual(money.yuan_to_fen("¥100.00"), 10000)
        self.assertEqual(money.yuan_to_fen(0), 0)
        self.assertIsNone(money.yuan_to_fen(None))
        self.assertIsNone(money.yuan_to_fen(""))
        self.assertIsNone(money.yuan_to_fen("-"))
        self.assertEqual(money.yuan_to_fen("not-a-number"), 0)
        # 超大金额
        self.assertEqual(money.yuan_to_fen("999999999.99"), 99999999999)

    def test_roundtrip(self):
        for yuan in (0, 0.01, 1, 12.34, 100.5, -0.01, 1_000_000.99):
            fen = money.yuan_to_fen(yuan)
            self.assertEqual(money.fen_to_yuan(fen), float(yuan) if not isinstance(yuan, float) else money.fen_to_yuan(fen))
            # 两分位内 round-trip
            self.assertAlmostEqual(money.fen_to_yuan(fen), float(yuan), places=2)

    def test_fen_to_yuan_none(self):
        self.assertIsNone(money.fen_to_yuan_or_none(None))
        self.assertEqual(money.fen_to_yuan_or_none(100), 1.0)
        self.assertEqual(money.fen_to_yuan(None), 0.0)


class TestMigrateAndAdjust(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["db_path"] = str((self.tmp / "看板.db").resolve())
        self.cfg["data_dir"] = str(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_db_is_v2(self):
        conn = db.connect(self.cfg, self.tmp)
        self.assertEqual(schema._schema_version(conn), schema.SCHEMA_VERSION)
        # 幂等
        r = schema.migrate_money_to_fen_if_needed(conn)
        self.assertEqual(r["status"], "skip")
        conn.close()

    def test_legacy_yuan_manual_migrates(self):
        """模拟 v1 库：手填存元 REAL → 迁移后为分，load 回元。"""
        import sqlite3

        path = self.tmp / "看板.db"
        conn = sqlite3.connect(str(path))
        # 故意建 v1 形状（金额 REAL 元）并写入
        conn.executescript(
            """
            CREATE TABLE manual_手填(
                归属月 TEXT, 项目 TEXT, 金额 REAL, 填写时间 TEXT, 经手人 TEXT,
                PRIMARY KEY (归属月, 项目)
            );
            CREATE TABLE meta_schema(key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO meta_schema(key,value) VALUES('version','1');
            INSERT INTO manual_手填 VALUES('2026-01','闲置人力',1234.56,'t','u');
            INSERT INTO manual_手填 VALUES('2026-01','直接成本增值税',0.005,'t','u');
            """
        )
        conn.commit()
        conn.close()

        # connect → create_all → migrate
        conn = db.connect(self.cfg, self.tmp)
        raw = conn.execute("SELECT 金额 FROM manual_手填 WHERE 项目='闲置人力'").fetchone()[0]
        self.assertEqual(int(raw), 123456)
        raw2 = conn.execute("SELECT 金额 FROM manual_手填 WHERE 项目='直接成本增值税'").fetchone()[0]
        self.assertEqual(int(raw2), 1)  # 0.005 元 → 1 分
        loaded = db.load_manual(self.cfg, conn)
        self.assertEqual(loaded["2026-01"]["闲置人力"], 123456)  # 分
        self.assertEqual(loaded["2026-01"]["直接成本增值税"], 1)
        self.assertEqual(schema._schema_version(conn), schema.SCHEMA_VERSION)
        # 幂等再迁
        r2 = schema.migrate_money_to_fen_if_needed(conn)
        self.assertEqual(r2["status"], "skip")
        raw3 = conn.execute("SELECT 金额 FROM manual_手填 WHERE 项目='闲置人力'").fetchone()[0]
        self.assertEqual(int(raw3), 123456)
        conn.close()

    def test_adjust_amount_applies_in_fen(self):
        """改值调整：原值元文本 vs 库内分；套用后库内为新分。"""
        conn = db.connect(self.cfg, self.tmp)
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月,已删除) "
            "VALUES(?,?,?,?,?,?,?,?,?,0)",
            ("SO-A", "SO-A", "2026-03-01", 10000, "部", "销", "客", "2026-03", "2026-03"),  # 100 元
        )
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            # 原值/新值均存分（10000=100元，25050=250.5元）
            ("2026-01-01", "t", "std_下单", "SO-A", "下单预估额", "10000", "25050", "测", "改值", "生效"),
        )
        conn.commit()
        rep = adjust.apply_adjustments(conn, "2026-07-16 00:00:00")
        self.assertEqual(rep["applied"], 1)
        self.assertEqual(rep["expired"], 0)
        fen = conn.execute("SELECT 下单预估额 FROM std_下单 WHERE 定位键='SO-A'").fetchone()[0]
        self.assertEqual(int(fen), 25050)
        # load 返回分
        orders = db.load_orders(self.cfg, conn)
        amt_key = self.cfg["columns"]["order_amount"]
        hit = [o for o in orders if o.get("订单号") == "SO-A"][0]
        self.assertEqual(int(hit[amt_key]), 25050)
        conn.close()

    def test_adjust_expired_when_source_changed(self):
        conn = db.connect(self.cfg, self.tmp)
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月,已删除) "
            "VALUES(?,?,?,?,?,?,?,?,?,0)",
            ("SO-B", "SO-B", "2026-03-01", 20000, "部", "销", "客", "2026-03", "2026-03"),  # 200 元
        )
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("2026-01-01", "t", "std_下单", "SO-B", "下单预估额", "10000", "300", "测", "改值", "生效"),  # 原值分≠现值
        )
        conn.commit()
        rep = adjust.apply_adjustments(conn, "2026-07-16 00:00:00")
        self.assertEqual(rep["expired"], 1)
        fen = conn.execute("SELECT 下单预估额 FROM std_下单 WHERE 定位键='SO-B'").fetchone()[0]
        self.assertEqual(int(fen), 20000)  # 未套用
        conn.close()

    def test_set_manual_stores_fen(self):
        conn = db.connect(self.cfg, self.tmp)
        db.set_manual(conn, "2026-06", "闲置人力", 88.88, "tester")
        raw = conn.execute("SELECT 金额 FROM manual_手填 WHERE 归属月='2026-06'").fetchone()[0]
        self.assertEqual(int(raw), 8888)
        m = db.load_manual(self.cfg, conn)
        self.assertEqual(m["2026-06"]["闲置人力"], 8888)
        conn.close()


if __name__ == "__main__":
    unittest.main()
