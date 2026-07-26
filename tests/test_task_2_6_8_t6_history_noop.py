# -*- coding: utf-8 -*-
"""2.6.8 T6：manual_*历史 不记空操作（新旧值相等跳过）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import loaders  # noqa: E402
import schema  # noqa: E402


class TestHistorySkipNoop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "数据").mkdir()
        self.cfg = dict(loaders.load_config(ROOT))
        self.cfg["data_dir"] = "数据"
        self.cfg["db_path"] = "看板.db"
        self.conn = db.connect(self.cfg, self.tmp)
        schema.create_all(self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_set_manual_same_value_no_history(self):
        db.set_manual(self.conn, "2026-07", "测试项", 100.0, "测")
        n1 = self.conn.execute("SELECT COUNT(*) FROM manual_历史").fetchone()[0]
        db.set_manual(self.conn, "2026-07", "测试项", 100.0, "测")
        n2 = self.conn.execute("SELECT COUNT(*) FROM manual_历史").fetchone()[0]
        self.assertEqual(n1, n2)
        db.set_manual(self.conn, "2026-07", "测试项", 200.0, "测")
        n3 = self.conn.execute("SELECT COUNT(*) FROM manual_历史").fetchone()[0]
        self.assertEqual(n3, n1 + 1)

    def test_set_alloc_ratio_same_no_history(self):
        db.set_alloc_ratio(self.conn, "2026-07", "语言", 30, "测")
        n1 = self.conn.execute("SELECT COUNT(*) FROM manual_分摊比例历史").fetchone()[0]
        db.set_alloc_ratio(self.conn, "2026-07", "语言", 30, "测")
        n2 = self.conn.execute("SELECT COUNT(*) FROM manual_分摊比例历史").fetchone()[0]
        self.assertEqual(n1, n2)
        db.set_alloc_ratio(self.conn, "2026-07", "语言", 40, "测")
        n3 = self.conn.execute("SELECT COUNT(*) FROM manual_分摊比例历史").fetchone()[0]
        self.assertEqual(n3, n1 + 1)

    def test_set_alloc_delete_empty_no_history(self):
        n0 = self.conn.execute("SELECT COUNT(*) FROM manual_分摊比例历史").fetchone()[0]
        db.set_alloc_ratio(self.conn, "2026-08", "不存在BU", None, "测")
        n1 = self.conn.execute("SELECT COUNT(*) FROM manual_分摊比例历史").fetchone()[0]
        self.assertEqual(n0, n1)


if __name__ == "__main__":
    unittest.main()
