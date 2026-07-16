#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·5：备份恢复演练——从 数据/备份/ 或 _golden_data 恢复到临时目录并 smoke。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestBackupRestore(unittest.TestCase):
    def test_restore_golden_db_smoke(self):
        src = ROOT / "_golden_data" / "看板.db"
        if not src.is_file():
            # 尝试备份目录
            bak = list((ROOT / "数据" / "备份").glob("*.db")) if (ROOT / "数据" / "备份").is_dir() else []
            if not bak:
                self.skipTest("无备份/golden db")
            src = bak[0]
        tmp = Path(tempfile.mkdtemp())
        try:
            dest = tmp / "看板.db"
            shutil.copy2(src, dest)
            self.assertTrue(dest.is_file())
            import sqlite3

            conn = sqlite3.connect(str(dest))
            n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            conn.close()
            self.assertGreater(n, 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
