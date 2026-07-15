#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书33·A4/A6/A7：定位键重复审计、备份恢复、quick_check。"""
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
from ingest import adjust, archive  # noqa: E402


def _cfg(tmp: Path) -> dict:
    cfg = dict(loaders.load_config(ROOT))
    cfg["db_path"] = str((tmp / "看板.db").resolve())
    cfg["data_dir"] = str(tmp)
    return cfg


class TestDuplicateLocatorsA4(unittest.TestCase):
    """A4：两行全同 → 同哈希；写调整拒；重放过期疑似；audit 报告。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp)
        self.conn = db.connect(self.cfg, self.tmp)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _two_same(self):
        fen = money.yuan_to_fen(100.0)
        for _ in range(2):
            self.conn.execute(
                "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
                "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                ("DUPKEY", "6", "2026-06-15", fen, "语言", "管理费用", "办公", "部", "2026-06", "2026-06"),
            )
        self.conn.commit()

    def test_add_rejected_and_audit_lists(self):
        self._two_same()
        with self.assertRaises(ValueError):
            db.add_adjustment(self.conn, "t", "std_费用明细", "DUPKEY", "含税金额", "200", "测", "改值")
        audit = db.audit_duplicate_locators(self.conn)
        self.assertIn("std_费用明细", audit)
        self.assertEqual(audit["std_费用明细"]["DUPKEY"], 2)

    def test_replay_expires_not_silent_multi(self):
        fen = money.yuan_to_fen(100.0)
        self.conn.execute(
            "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
            "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            ("ONE", "6", "2026-06-15", fen, "语言", "管理费用", "办公", "部", "2026-06", "2026-06"),
        )
        self.conn.commit()
        db.add_adjustment(self.conn, "t", "std_费用明细", "ONE", "含税金额", "200", "测", "改值")
        # 新批次冒出重复
        self.conn.execute(
            "INSERT INTO std_费用明细(定位键,收单月份,收单日期,含税金额,业务BU,对应报表大类,"
            "预算明细费用类型,预算归属部门,归属月,原值_归属月,已删除)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            ("ONE", "6", "2026-06-15", fen, "语言", "管理费用", "办公", "部", "2026-06", "2026-06"),
        )
        self.conn.commit()
        rep = adjust.apply_adjustments(self.conn, "2026-07-16 00:00:00")
        self.assertEqual(rep["expired"], 1)
        self.assertEqual(rep["applied"], 0)
        vals = [int(v[0]) for v in self.conn.execute("SELECT 含税金额 FROM std_费用明细 WHERE 定位键='ONE'")]
        self.assertEqual(vals, [fen, fen])


class TestQuickCheckA7(unittest.TestCase):
    def test_ok_on_fresh(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = _cfg(tmp)
            conn = db.connect(cfg, tmp)
            r = db.pragma_quick_check(conn)
            self.assertTrue(r["ok"])
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBackupRestoreA6(unittest.TestCase):
    def test_backup_restore_roundtrip(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = _cfg(tmp)
            conn = db.connect(cfg, tmp)
            db.set_manual(conn, "2026-06", "闲置人力", 123.45, "tester")
            conn.close()

            import datetime

            bak = archive.backup_db(cfg, datetime.date(2026, 7, 16), tmp)
            self.assertEqual(bak["status"], "ok")
            self.assertTrue(bak.get("ok"))
            bak_path = Path(bak["path"])
            self.assertTrue(bak_path.exists())

            # 破坏当前库
            conn = db.connect(cfg, tmp)
            db.set_manual(conn, "2026-06", "闲置人力", 99999.0, "wrecker")
            m = db.load_manual(cfg, conn)
            self.assertEqual(m["2026-06"]["闲置人力"], 9999900)  # 分
            conn.close()

            # 恢复
            res = archive.restore_db_from_backup(cfg, bak_path, tmp)
            self.assertEqual(res["status"], "ok")
            conn = db.connect(cfg, tmp)
            m2 = db.load_manual(cfg, conn)
            self.assertEqual(m2["2026-06"]["闲置人力"], 12345)  # 123.45 元
            q = db.pragma_quick_check(conn)
            self.assertTrue(q["ok"])
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
