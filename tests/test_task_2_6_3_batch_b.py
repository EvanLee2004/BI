#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.6.3 批次 B 守卫：漏跑补跑 / 漏月快照 / 坏归档 partial / 缺台账页降级 / health 新鲜度不看 mtime。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
from ingest import archive  # noqa: E402
from schedule_loop import ScheduleLoop  # noqa: E402


class TestB2CatchUpSchedule(unittest.TestCase):
    """漏跑：过点且今日未成功 → 补跑；busy 时排队不丢。"""

    def test_past_slot_fires_catchup(self):
        calls = []

        def start(cfg, root, trigger="schedule"):
            calls.append(trigger)
            return True

        # 假时钟 09:35，计划 09:30
        def clock():
            return time.struct_time((2026, 7, 25, 9, 35, 0, 0, 0, -1))

        loop = ScheduleLoop({}, None, start, clock=clock, load_times_fn=lambda: ["09:30", "17:30"])
        self.assertTrue(loop.tick())
        self.assertEqual(len(calls), 1)
        # 再 tick 不应重复 09:30
        self.assertFalse(loop.tick())
        self.assertEqual(len(calls), 1)

    def test_busy_queues_retry(self):
        n = {"i": 0}

        def start(cfg, root, trigger="schedule"):
            n["i"] += 1
            return n["i"] >= 2  # 第一次忙，第二次成功

        def clock():
            return time.struct_time((2026, 7, 25, 9, 31, 0, 0, 0, -1))

        loop = ScheduleLoop({}, None, start, clock=clock, load_times_fn=lambda: ["09:30"])
        self.assertFalse(loop.tick())
        self.assertIn("09:30", loop._queue)
        self.assertTrue(loop.tick())
        self.assertEqual(loop._queue, [])


class TestB3MissingMonthSnapshot(unittest.TestCase):
    def test_ensure_prev_month_snapshot_backfills(self):
        tmp = Path(tempfile.mkdtemp(prefix="t263b3_"))
        try:
            cfg = loaders.load_config()
            cfg = dict(cfg)
            cfg["data_dir"] = str(tmp)
            cfg["db_path"] = "看板.db"
            # 造一个假源文件
            (tmp / "下单.xlsx").write_bytes(b"x" * 20)
            # 今天 2026-07-15 → 应补 2026-06
            r = archive.ensure_prev_month_snapshot(cfg, date(2026, 7, 15), None)
            self.assertTrue(r.get("done") or r.get("status") in ("snapshot", "exists", "empty"))
            self.assertEqual(r.get("missing_month"), "2026-06")
            snap = tmp / "快照存档" / "2026-06"
            self.assertTrue(snap.is_dir())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_if_month_end_done_bool(self):
        r = archive.snapshot_if_month_end({"files": {}}, date(2026, 7, 15), None)
        self.assertEqual(r.get("done"), False)
        self.assertEqual(r.get("status"), "skip")


class TestB4PartialArchiveNotExists(unittest.TestCase):
    def test_partial_dir_not_treated_as_complete(self):
        tmp = Path(tempfile.mkdtemp(prefix="t263b4_"))
        try:
            cfg = loaders.load_config()
            cfg = dict(cfg)
            cfg["data_dir"] = str(tmp)
            cfg["db_path"] = "看板.db"
            cfg["zhiyun_since"] = "auto"
            for n in ("下单.xlsx", "回款记录.xlsx", "内部译员.xlsx", "项目明细.xlsx"):
                (tmp / n).write_bytes(b"x" * 100)
            # 半截最终目录（无 _ARCHIVE_OK）——旧 bug 会 exists
            arch = tmp / "年度归档" / "2026"
            arch.mkdir(parents=True)
            (arch / "下单.xlsx").write_bytes(b"x" * 100)
            r = archive.maybe_year_archive_zhiyun(cfg, None, today=date(2027, 1, 2))
            # 应重做完成，不得返回 exists 且只含 1 文件
            self.assertNotEqual(r.get("status"), "exists")
            final = tmp / "年度归档" / "2026"
            self.assertTrue((final / "_ARCHIVE_OK").is_file(), f"r={r}")
            names = sorted(x.name for x in final.iterdir())
            self.assertIn("_ARCHIVE_OK", names)
            self.assertGreaterEqual(len([n for n in names if n != "_ARCHIVE_OK"]), 2)
            # 再跑 → exists
            r2 = archive.maybe_year_archive_zhiyun(cfg, None, today=date(2027, 1, 2))
            self.assertEqual(r2.get("status"), "exists")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestB6MissingLedgerSheet(unittest.TestCase):
    def test_missing_year_sheet_returns_empty_not_raise(self):
        import openpyxl

        tmp = Path(tempfile.mkdtemp(prefix="t263b6_"))
        try:
            loaders.clear_ledger_sheet_missing_status()
            cfg = loaders.load_config()
            cfg = dict(cfg)
            cfg["data_dir"] = str(tmp)
            # 只有 2026 页，无 2027
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "2026"
            ws.append(["日期", "金额"])
            path = tmp / cfg["files"]["ledger"]
            wb.save(path)
            header, rows = loaders.load_ledger(cfg, "2027", None)
            self.assertEqual(header, [])
            self.assertEqual(rows, [])
            st = loaders.ledger_sheet_missing_status()
            self.assertIsNotNone(st)
            self.assertEqual(st.get("year"), "2027")
            self.assertIn("亮晶", st.get("banner") or "")
        finally:
            loaders.clear_ledger_sheet_missing_status()
            shutil.rmtree(tmp, ignore_errors=True)


class TestB1HealthUsesBuiltAtNotMtime(unittest.TestCase):
    def test_healthcheck_script_mentions_built_at_not_db_mtime(self):
        sh = (ROOT / "deploy" / "healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn("built_at", sh)
        self.assertIn("/api/v1/health", sh)
        # 不得再用 看板.db mtime 作 stale 主判据
        self.assertNotIn('mtime_of "$DATA_DIR/看板.db"', sh)
        self.assertIn("2.6.3", sh)


if __name__ == "__main__":
    unittest.main()
