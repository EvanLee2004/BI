#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33 skeptic 补洞：预算比率勿走分；adj 原值元→分迁移；list 原值/新值同为元。"""
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
from profit import build_budget_block  # noqa: E402


class TestBudgetRateNotFen(unittest.TestCase):
    def test_set_load_rate_and_pct(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = dict(loaders.load_config(ROOT))
            cfg["db_path"] = str((tmp / "看板.db").resolve())
            cfg["data_dir"] = str(tmp)
            conn = db.connect(cfg, tmp)
            db.set_budget(conn, "2026", "毛利率年目标", 35.0, "t")
            db.set_budget(conn, "2026", "下单年预算", 1_000_000.0, "t")
            raw = conn.execute(
                "SELECT 指标,金额 FROM manual_预算 WHERE 年份='2026'"
            ).fetchall()
            by = {a: b for a, b in raw}
            # 比率存百分位点 35→3500，不是 yuan_to_fen(35)=3500 的「分」语义但数值同构；
            # 关键：load 后是 35.0 百分数，不是 3500
            self.assertEqual(int(by["毛利率年目标"]), 3500)
            self.assertEqual(int(by["下单年预算"]), 100_000_000)  # 100万=1e8 分
            loaded = db.load_budget(conn)
            self.assertEqual(loaded["2026"]["毛利率年目标"], 35.0)
            self.assertEqual(loaded["2026"]["下单年预算"], 100_000_000)
            # 完成率：实际 40% / 目标 35% ≈ 114%
            blk = build_budget_block(loaded, 2026, {"orders": 50_000_000, "receipts": 0, "gross_margin_pct": 40.0})
            self.assertIsNotNone(blk["margin"])
            self.assertAlmostEqual(blk["margin"]["target"], 35.0)
            self.assertAlmostEqual(blk["margin"]["pct"], 40.0 / 35.0 * 100.0, places=1)
            # 管理端 get：比率 35，金额 元
            rows = db.get_budget(conn, "2026")
            m = {r["指标"]: r["金额"] for r in rows}
            self.assertEqual(m["毛利率年目标"], 35.0)
            self.assertAlmostEqual(m["下单年预算"], 1_000_000.0, places=2)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestAdjYuanToFenMigrate(unittest.TestCase):
    def test_stock_yuan_原值_still_applies_after_migrate(self):
        """存量 原值='100'（元）+ std 10000 分 → 迁移后匹配仍套用。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            import sqlite3

            path = tmp / "看板.db"
            conn = sqlite3.connect(str(path))
            # 模拟 v1 库：金额 REAL 元 + adj 原值元文本
            conn.executescript(
                """
                CREATE TABLE std_下单(
                    id INTEGER PRIMARY KEY, 定位键 TEXT, 订单号 TEXT, 下单日期 TEXT,
                    下单预估额 REAL, 部门 TEXT, 销售 TEXT, 客户 TEXT,
                    归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
                );
                CREATE TABLE adj_调整记录(
                    id INTEGER PRIMARY KEY, 创建时间 TEXT, 经手人 TEXT,
                    目标表 TEXT, 定位键 TEXT, 字段 TEXT, 原值 TEXT, 新值 TEXT,
                    原因 TEXT, 类型 TEXT, 状态 TEXT
                );
                CREATE TABLE meta_schema(key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO meta_schema VALUES('version','1');
                INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月,已删除)
                VALUES('SO1','SO1','2026-01-01',100.0,'部','销','客','2026-01','2026-01',0);
                INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)
                VALUES('t','u','std_下单','SO1','下单预估额','100','250.5','测','改值','生效');
                """
            )
            conn.commit()
            conn.close()

            cfg = dict(loaders.load_config(ROOT))
            cfg["db_path"] = str(path.resolve())
            cfg["data_dir"] = str(tmp)
            conn = db.connect(cfg, tmp)  # migrate v1→3
            self.assertEqual(schema._schema_version(conn), schema.SCHEMA_VERSION)
            o, n = conn.execute(
                "SELECT 原值,新值 FROM adj_调整记录 WHERE 定位键='SO1'"
            ).fetchone()
            self.assertEqual(str(o), "10000")  # 100 元 → 分
            self.assertEqual(str(n), "25050")  # 250.5 元 → 分
            fen = conn.execute("SELECT 下单预估额 FROM std_下单 WHERE 定位键='SO1'").fetchone()[0]
            self.assertEqual(int(fen), 10000)
            rep = adjust.apply_adjustments(conn, "2026-07-16 00:00:00")
            self.assertEqual(rep["applied"], 1, rep)
            self.assertEqual(rep["expired"], 0)
            fen2 = conn.execute("SELECT 下单预估额 FROM std_下单 WHERE 定位键='SO1'").fetchone()[0]
            self.assertEqual(int(fen2), 25050)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_match_heuristic_yuan_integer_without_migrate(self):
        """未迁 adj：原值='100' 元 vs 库内 10000 分 → 仍匹配（双解）。"""
        self.assertTrue(adjust._values_match(10000, "100", "下单预估额"))
        self.assertTrue(adjust._values_match(10000, "10000", "下单预估额"))
        self.assertTrue(adjust._values_match(10050, "100.5", "下单预估额"))
        self.assertFalse(adjust._values_match(10000, "99", "下单预估额"))


class TestListAdjustmentsYuanYuan(unittest.TestCase):
    def test_list_shows_yuan_for_both(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = dict(loaders.load_config(ROOT))
            cfg["db_path"] = str((tmp / "看板.db").resolve())
            cfg["data_dir"] = str(tmp)
            conn = db.connect(cfg, tmp)
            conn.execute(
                "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,0)",
                ("K1", "K1", "2026-01-01", 10000, "部", "销", "客", "2026-01", "2026-01"),
            )
            conn.commit()
            db.add_adjustment(conn, "t", "std_下单", "K1", "下单预估额", "250.5", "测", "改值")
            # 库内均为分
            o, n = conn.execute("SELECT 原值,新值 FROM adj_调整记录").fetchone()
            self.assertEqual(str(o), "10000")
            self.assertEqual(str(n), "25050")
            # 列表展示均为元
            lst = db.list_adjustments(conn)
            self.assertEqual(lst[0]["原值"], "100")
            self.assertEqual(lst[0]["新值"], "250.5")
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
