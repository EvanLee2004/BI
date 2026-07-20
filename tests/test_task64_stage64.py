#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书64：D1 备份 VACUUM INTO / D2 索引 / D3 原子 publish / D4 normalize / E 跨年归档。"""

from __future__ import annotations

import datetime
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders  # noqa: E402
import schema  # noqa: E402
from ingest import archive, normalize  # noqa: E402
from refresh_pipeline import publish  # noqa: E402
from app_state import _state  # noqa: E402


class TestD1BackupVacuumInto(unittest.TestCase):
    def test_backup_integrity_ok(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        dbp = data / "看板.db"
        conn = sqlite3.connect(str(dbp))
        conn.execute("CREATE TABLE t(x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1),(2)")
        conn.commit()
        conn.close()
        cfg = {"data_dir": "数据", "db_path": "看板.db", "backup_keep_days": 5}
        r = archive.backup_db(cfg, datetime.date(2026, 7, 20), tmp)
        self.assertTrue(r.get("ok"), r)
        self.assertIn(r.get("method"), ("vacuum_into", "copy2_fallback"))
        bak = Path(r["path"])
        self.assertTrue(bak.is_file())
        c2 = sqlite3.connect(str(bak))
        try:
            ok = c2.execute("PRAGMA integrity_check").fetchone()[0]
            self.assertEqual(ok, "ok")
            n = c2.execute("SELECT count(*) FROM t").fetchone()[0]
            self.assertEqual(n, 2)
        finally:
            c2.close()


class TestD2StdIndexes(unittest.TestCase):
    def test_create_all_has_indexes(self):
        conn = sqlite3.connect(":memory:")
        schema.create_all(conn)
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_std_%'"
            )
        }
        self.assertIn("idx_std_下单_定位键", names)
        self.assertIn("idx_std_收入明细_删月", names)
        self.assertGreaterEqual(len(names), 10)
        conn.close()


class TestD3PublishAtomic(unittest.TestCase):
    def test_no_mixed_keys_during_publish(self):
        # 预置（65·L2：publish 不再写 user_html；看 summary/fragments/built_at 一致性）
        _state["summary"] = {"old": 1}
        _state["fragments"] = {"a": 1}
        _state["views"] = {"v": 1}
        _state["built_at"] = "old"
        _state["has_data"] = False
        mixed = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                s = _state.get("summary")
                f = _state.get("fragments")
                # summary 已是新且 fragments 仍是旧 a→撕裂
                if isinstance(s, dict) and s.get("new") and isinstance(f, dict) and f.get("a") == 1:
                    mixed.append((s, f))
                time.sleep(0)

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        for i in range(50):
            publish(None, {"new": True, "i": i}, None, fragments={"f": i}, views={"v": i})
        stop.set()
        th.join(timeout=1)
        self.assertEqual(mixed, [], f"检测到新旧混合: {mixed[:3]}")
        self.assertTrue(_state.get("has_data"))
        self.assertEqual(_state.get("user_html"), "")


class TestD4NormalizeProjectLine(unittest.TestCase):
    def test_project_line_from_cfg(self):
        c = {
            "project_delivery_date": "整单交付日期",
            "project_revenue": "交付额/本币",
            "project_cost": "项目成本/本币",
            "project_line": "产品线",
        }
        rows = [
            {
                "订单号": "SO1",
                "SOD": "SOD1",
                "客户": "甲",
                "产品线": "游戏",
                "业务线": "应被忽略",
                "销售": "张三",
                "整单交付日期": "2026-01-15",
                "交付额/本币": "100",
                "项目成本/本币": "10",
            }
        ]
        out = normalize.norm_project_detail(rows, c)
        self.assertEqual(out[0]["业务线"], "游戏")

    def test_project_line_required_in_validate(self):
        cfg = loaders.load_config(ROOT)
        cols = dict(cfg["columns"])
        cols.pop("project_line", None)
        bad = dict(cfg)
        bad["columns"] = cols
        with self.assertRaises(ValueError) as cm:
            loaders.validate_config(bad)
        self.assertIn("project_line", str(cm.exception))


class TestEYearArchive(unittest.TestCase):
    def test_year_archive_once(self):
        from openpyxl import Workbook

        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        # 四源假 xlsx
        for name in ("下单.xlsx", "回款记录.xlsx", "内部译员.xlsx", "项目明细.xlsx"):
            wb = Workbook()
            ws = wb.active
            ws.append(["a"])
            ws.append([2026])
            wb.save(data / name)
        # 空库
        dbp = data / "看板.db"
        sqlite3.connect(str(dbp)).close()

        cfg = {
            "data_dir": "数据",
            "db_path": "看板.db",
            "zhiyun_since": "auto",
            "files": {
                "orders": "下单.xlsx",
                "receipts": "回款记录.xlsx",
                "inhouse": "内部译员.xlsx",
                "project_detail_stem": "项目明细",
            },
        }
        today = datetime.date(2027, 1, 2)
        r1 = archive.maybe_year_archive_zhiyun(cfg, tmp, today=today)
        self.assertEqual(r1.get("status"), "archived", r1)
        arch = Path(r1["path"])
        self.assertTrue((arch / "下单.xlsx").is_file())
        self.assertTrue((arch / "回款记录.xlsx").is_file())
        self.assertTrue((arch / "内部译员.xlsx").is_file())
        self.assertTrue((arch / "项目明细.xlsx").is_file())
        # 二次不重复
        r2 = archive.maybe_year_archive_zhiyun(cfg, tmp, today=today)
        self.assertEqual(r2.get("status"), "exists", r2)

    def test_backup_prune_does_not_touch_year_archive(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        arch = data / "年度归档" / "2026"
        arch.mkdir(parents=True)
        keep = arch / "keep.xlsx"
        keep.write_text("x", encoding="utf-8")
        dbp = data / "看板.db"
        conn = sqlite3.connect(str(dbp))
        conn.execute("CREATE TABLE t(x)")
        conn.commit()
        conn.close()
        cfg = {"data_dir": "数据", "db_path": "看板.db", "backup_keep_days": 1}
        archive.backup_db(cfg, datetime.date(2026, 7, 1), tmp)
        archive.backup_db(cfg, datetime.date(2026, 7, 2), tmp)
        self.assertTrue(keep.is_file(), "年度归档不得被备份滚动清理删除")


if __name__ == "__main__":
    unittest.main()
