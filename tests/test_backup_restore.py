#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·5：备份恢复演练——恢复到临时目录后跑只读连接 + extract_numbers smoke。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestBackupRestore(unittest.TestCase):
    def test_restore_then_readonly_query(self):
        src_db = ROOT / "_golden_data" / "看板.db"
        if not src_db.is_file():
            bak_dir = ROOT / "数据" / "备份"
            cands = list(bak_dir.glob("*.db")) if bak_dir.is_dir() else []
            if not cands:
                self.skipTest("无备份/golden db")
            src_db = cands[0]

        tmp = Path(tempfile.mkdtemp())
        try:
            # 恢复：复制库到临时 data_dir
            data = tmp / "数据"
            data.mkdir()
            dest = data / "看板.db"
            shutil.copy2(src_db, dest)
            # 拷贝最小 xlsx 若有（供 generate 可选）
            gd = ROOT / "_golden_data"
            if gd.is_dir():
                for x in gd.glob("*.xlsx"):
                    shutil.copy2(x, data / x.name)

            import api_v1
            import db
            import loaders

            cfg = dict(loaders.load_config(ROOT))
            cfg["data_dir"] = "数据"
            cfg["db_path"] = "看板.db"  # 相对 data_dir，勿再嵌 数据/
            cfg["zhiyun_auto_fetch"] = False

            # 只读连接
            conn = db.connect_readonly(cfg, tmp)
            try:
                n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                self.assertGreater(n, 3)
                # 写操作应失败（只读）
                with self.assertRaises(Exception):
                    conn.execute("CREATE TABLE __should_fail (id INTEGER)")
                    conn.commit()
            finally:
                conn.close()

            # 恢复后 smoke：从库读 summary 数字（非完整 run_verify，但真实路径）
            import core
            import datetime

            conn2 = db.connect(cfg, tmp)  # 写连接可 schema
            try:
                today = datetime.date(2026, 6, 30)
                summary = core.summary_from_conn(cfg, conn2, today)
                nums = api_v1.extract_numbers(summary)
                self.assertIn("period_keys", nums)
                self.assertTrue(nums.get("period_keys") or nums.get("meta_year_key") is not None)
            finally:
                conn2.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_connect_readonly_flag(self):
        import db
        import loaders

        src = ROOT / "_golden_data" / "看板.db"
        if not src.is_file():
            self.skipTest("无 golden db")
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        conn = db.connect(cfg, ROOT, readonly=True)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
