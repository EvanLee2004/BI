#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33·A1/A2：std 重建单事务 + WAL 并发读。

- 第 3 张表插入抛异常 → 旧 std 行完整保留（非空、非半新）
- 重建事务未提交期间另一连接可读旧数据
- connect() 开启 WAL + busy_timeout
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import ingest  # noqa: E402
import loaders  # noqa: E402
import schema  # noqa: E402


def _cfg(tmp: Path) -> dict:
    cfg = dict(loaders.load_config(ROOT))
    cfg["db_path"] = str((tmp / "看板.db").resolve())
    cfg["data_dir"] = str(tmp)
    return cfg


def _seed_std(conn, n: int = 3) -> None:
    """写入可识别的旧 std 数据（金额单位：分）。"""
    for i in range(n):
        conn.execute(
            "INSERT INTO std_下单(定位键,订单号,下单日期,下单预估额,部门,销售,客户,归属月,原值_归属月) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (f"OLD-{i}", f"SO{i}", "2026-01-0%d" % (i + 1), (1000 + i) * 100, "部", "销", "客", "2026-01", "2026-01"),
        )
    conn.execute(
        "INSERT INTO std_收入明细(定位键,订单号,客户,业务线,销售,整单交付日期,交付额,项目成本,归属月,原值_归属月) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("OLD-P", "SO0", "客", "线", "销", "2026-01-15", 5000 * 100, 1000 * 100, "2026-01", "2026-01"),
    )
    conn.commit()


class TestAtomicRebuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp)
        self.conn = db.connect(self.cfg, self.tmp)
        _seed_std(self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_fail_on_third_table_preserves_old_rows(self):
        """第 3 张表（std_回款）插入失败 → 旧下单/收入仍在。"""
        old_orders = self.conn.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0]
        old_proj = self.conn.execute("SELECT COUNT(*) FROM std_收入明细").fetchone()[0]
        self.assertGreater(old_orders, 0)
        self.assertGreater(old_proj, 0)

        import db_write

        real_insert = db_write.insert_std_records
        order = ["std_收入明细", "std_下单", "std_回款", "std_内部译员", "std_费用明细"]
        third = order[2]  # std_回款

        def boom(conn, table, records):
            if table == third:
                raise RuntimeError("simulated insert fail on table 3")
            return real_insert(conn, table, records)

        new_records = {
            "std_收入明细": [
                {
                    "定位键": "NEW-P",
                    "订单号": "N1",
                    "客户": "新客",
                    "业务线": "线",
                    "销售": "销",
                    "整单交付日期": "2026-06-01",
                    "交付额": 999.0,
                    "项目成本": 1.0,
                    "归属月": "2026-06",
                    "原值_交付日期": "2026-06-01",
                    "原值_归属月": "2026-06",
                }
            ],
            "std_下单": [
                {
                    "定位键": "NEW-O",
                    "订单号": "N1",
                    "下单日期": "2026-06-01",
                    "下单预估额": 888.0,
                    "部门": "部",
                    "销售": "销",
                    "客户": "新客",
                    "归属月": "2026-06",
                    "原值_归属月": "2026-06",
                }
            ],
            "std_回款": [{"定位键": "NEW-R", "回款ID": "R1", "到账日期": "2026-06-02", "到账金额": 1.0,
                         "客户": "新客", "销售": "销", "归属月": "2026-06", "原值_归属月": "2026-06"}],
            "std_内部译员": [],
            "std_费用明细": [],
        }

        orig = db_write.insert_std_records
        db_write.insert_std_records = boom
        try:
            with self.assertRaises(RuntimeError):
                ingest._rebuild_std(self.conn, new_records)
        finally:
            db_write.insert_std_records = orig

        # 旧数据完整
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0], old_orders)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM std_收入明细").fetchone()[0], old_proj)
        keys = [r[0] for r in self.conn.execute("SELECT 定位键 FROM std_下单").fetchall()]
        self.assertTrue(all(k.startswith("OLD-") for k in keys), keys)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM std_下单 WHERE 定位键 LIKE 'NEW%'").fetchone()[0], 0
        )

    def test_successful_rebuild_replaces(self):
        new_records = {
            "std_收入明细": [],
            "std_下单": [
                {
                    "定位键": "ONLY-NEW",
                    "订单号": "X",
                    "下单日期": "2026-03-01",
                    "下单预估额": 42.0,
                    "部门": "d",
                    "销售": "s",
                    "客户": "c",
                    "归属月": "2026-03",
                    "原值_归属月": "2026-03",
                }
            ],
            "std_回款": [],
            "std_内部译员": [],
            "std_费用明细": [],
        }
        ingest._rebuild_std(self.conn, new_records)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0], 1)
        self.assertEqual(
            self.conn.execute("SELECT 定位键 FROM std_下单").fetchone()[0], "ONLY-NEW"
        )


class TestWalMode(unittest.TestCase):
    def test_connect_sets_wal_and_busy_timeout(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = _cfg(tmp)
        conn = db.connect(cfg, tmp)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(str(mode).lower(), "wal")
            bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            self.assertGreaterEqual(int(bt), 5000)
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            # NORMAL == 1
            self.assertIn(int(sync), (1, 2))  # NORMAL or FULL acceptable if platform maps
        finally:
            conn.close()

    def test_reader_sees_old_snapshot_during_uncommitted_rebuild(self):
        """重建事务未提交时，第二连接读到旧快照且不报锁错。"""
        tmp = Path(tempfile.mkdtemp())
        cfg = _cfg(tmp)
        w = db.connect(cfg, tmp)
        _seed_std(w, n=2)
        old_n = w.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0]
        self.assertEqual(old_n, 2)

        # 手动开事务模拟「清表后未提交」
        w.commit()
        w.isolation_level = None
        w.execute("BEGIN IMMEDIATE")
        schema.reset_std_tables(w, commit=False)
        # 写方连接内已空
        self.assertEqual(w.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0], 0)

        r = db.connect(cfg, tmp)
        try:
            # WAL：读方应看到提交前的旧快照
            n = r.execute("SELECT COUNT(*) FROM std_下单").fetchone()[0]
            self.assertEqual(n, old_n, "读方应仍见旧数据")
        finally:
            r.close()
            try:
                w.execute("ROLLBACK")
            except Exception:
                pass
            w.isolation_level = ""
            w.close()


if __name__ == "__main__":
    unittest.main()
