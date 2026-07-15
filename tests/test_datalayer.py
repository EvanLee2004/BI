#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刀1 数据层测试：ingest 无损落库 + 手填一次性迁移忠实 + 标准表重建不碰人工表 + 回归红线。
跑：python3 tests/test_datalayer.py"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders
import db
import schema
import ingest
import profit
import columns  # noqa: E402
import regress_db_vs_files as regress  # noqa: E402


def _tmp_conn():
    """临时库连接（隔离真实 数据/看板.db）；源文件仍读真实 数据/。"""
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fd.close()
    conn = sqlite3.connect(fd.name)
    schema.create_all(conn)
    return conn


class TestIngestRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = loaders.load_config()
        cls.yr = loaders.pinned_today(cls.cfg).year
        cls.conn = _tmp_conn()
        cls.report = ingest.build_std_db(cls.cfg, cls.yr, conn=cls.conn)

    def test_std_rowcounts_match_source(self):
        # 标准表行数 = 源行数（智云四源逐行不塌；台账逐行原样含空行）
        c = self.report["counts"]
        self.assertEqual(c["std_收入明细"], len(loaders.load_project_detail(self.cfg)))
        self.assertEqual(c["std_下单"], len(loaders.load_orders(self.cfg)))
        self.assertEqual(c["std_回款"], len(loaders.load_receipts(self.cfg)))
        # 台账逐行原样（含全空行），与旧读法行数一致
        _, lr_old = loaders.load_ledger(self.cfg, str(self.yr))
        self.assertEqual(c["std_费用明细"], len(lr_old))

    def test_revenue_sum_lossless(self):
        # 从库读回的收入合计（分）== 从文件读的收入合计元→分
        import money as _money

        cc = self.cfg["columns"]
        from_db = sum(int(r.get(cc["project_revenue"]) or 0) for r in db.load_project_detail(self.cfg, self.conn))
        from_file = sum(
            _money.yuan_to_fen(loaders.parse_amount(r.get(cc["project_revenue"]))) or 0
            for r in loaders.load_project_detail(self.cfg)
        )
        self.assertEqual(from_db, from_file)

    def test_locator_key_present(self):
        n_empty = self.conn.execute("SELECT COUNT(*) FROM std_收入明细 WHERE 定位键 IS NULL OR 定位键=''").fetchone()[0]
        self.assertEqual(n_empty, 0)


class TestManualMigration(unittest.TestCase):
    def test_migration_faithful(self):
        cfg = loaders.load_config()
        conn = _tmp_conn()
        ingest.build_std_db(cfg, loaders.pinned_today(cfg).year, conn=conn)
        import money as _money

        from_db = db.load_manual(cfg, conn)
        from_file = loaders.load_manual(cfg)
        # 库=分；xlsx=元 → 对齐后再比
        from_file_fen = {
            m: {k: (_money.yuan_to_fen(v) or 0) for k, v in items.items()} for m, items in from_file.items()
        }
        self.assertEqual(from_db, from_file_fen)

    def test_migration_idempotent(self):
        cfg = loaders.load_config()
        conn = _tmp_conn()
        yr = loaders.pinned_today(cfg).year
        r1 = ingest.build_std_db(cfg, yr, conn=conn)["migrate_manual"]
        r2 = ingest.build_std_db(cfg, yr, conn=conn)["migrate_manual"]  # 二次跑
        self.assertIn(r1["status"], ("migrated", "empty_source"))
        self.assertEqual(r2["status"], "skipped")  # 人工表已有数据，不再覆盖


class TestHumanTablesSurvive(unittest.TestCase):
    def test_std_rebuild_keeps_adjustments(self):
        cfg = loaders.load_config()
        conn = _tmp_conn()
        conn.execute(
            "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型) "
            "VALUES('t','明昊','std_收入明细','abc','整单交付日期','x','y','测试','改值')"
        )
        conn.commit()
        ingest.build_std_db(cfg, loaders.pinned_today(cfg).year, conn=conn)  # 全量重建标准表
        n = conn.execute("SELECT COUNT(*) FROM adj_调整记录").fetchone()[0]
        self.assertEqual(n, 1)  # 人工表不被标准表重建清空


class TestUnclassifiedQuery(unittest.TestCase):
    """B3：query_detail(unclassified=True) 只返回"未填对应报表大类"的费用明细行，
    且笔数与 build_unclassified_summary(全年)一致（DB费用明细只含当年台账）。"""

    def test_unclassified_filter_matches_summary(self):
        cfg = loaders.load_config()
        yr = loaders.pinned_today(cfg).year
        conn = _tmp_conn()
        ingest.build_std_db(cfg, yr, conn=conn)
        res = db.query_detail(conn, "费用明细", unclassified=True, page_size=500)
        # 每行的"对应报表大类"都为空
        for r in res["rows"]:
            self.assertIn(str(r.get("对应报表大类") or "").strip(), ("", "None"))
        # 笔数与体检口径一致
        lh, lr = db.load_ledger(cfg, conn)
        lcols = columns.resolve_ledger_columns(lh)
        summ = columns.build_unclassified_summary(lr, cfg, lcols)
        self.assertEqual(res["total"], summ["expense"]["count"])

    def test_unclassified_rejects_other_tables(self):
        cfg = loaders.load_config()
        conn = _tmp_conn()
        ingest.build_std_db(cfg, loaders.pinned_today(cfg).year, conn=conn)
        with self.assertRaises(KeyError):
            db.query_detail(conn, "收入明细", unclassified=True)


class TestRegressionRedline(unittest.TestCase):
    def test_db_summary_equals_file_summary(self):
        cfg = loaders.load_config()
        today = loaders.pinned_today(cfg)
        yr = today.year
        old = regress._strip_ts(regress.summary_from_files(cfg, today, yr))
        new = regress._strip_ts(regress.summary_from_db(cfg, today, yr))
        d = regress.diff(old, new)
        self.assertEqual(d, [], f"回归红线破：{d[:10]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
