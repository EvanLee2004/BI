# -*- coding: utf-8 -*-
"""2.6.8 T4：共享盘探测短重试 + 降级信息完整（不动 fstab）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import fetch as fetch_mod  # noqa: E402


class TestShareRetry(unittest.TestCase):
    def test_unreachable_retries_and_fallback_meta(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        (data / "收单台账.xlsx").write_bytes(b"PK\x03\x04local")
        cfg = {
            "data_dir": "数据",
            "files": {"ledger": "收单台账.xlsx"},
            "ledger_share_path": str(tmp / "no_such" / "台账.xlsx"),
            "ledger_share_retries": 3,
            "ledger_share_retry_delay_sec": 0,  # 单测不 sleep
        }
        calls = {"n": 0}
        real_exists = Path.exists

        def counting_exists(self):
            # 只统计 share 路径
            if "no_such" in str(self):
                calls["n"] += 1
                return False
            return real_exists(self)

        with patch.object(Path, "exists", counting_exists):
            r = fetch_mod.fetch_ledger(cfg, root=tmp)
        self.assertEqual(r["status"], "local_fallback")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(r.get("share_attempts"), 3)
        self.assertIn("source", r)
        self.assertTrue(r.get("local_as_of_cn") or r.get("local_as_of"))
        self.assertIn("本地副本", r.get("detail") or "")

    def test_reachable_no_retry_loop(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "数据"
        data.mkdir()
        share = tmp / "share"
        share.mkdir()
        (share / "台账.xlsx").write_bytes(b"PK\x03\x04share")
        cfg = {
            "data_dir": "数据",
            "files": {"ledger": "收单台账.xlsx"},
            "ledger_share_path": str(share / "台账.xlsx"),
            "ledger_share_retries": 5,
            "ledger_share_retry_delay_sec": 0,
        }
        r = fetch_mod.fetch_ledger(cfg, root=tmp)
        self.assertEqual(r["status"], "fetched")
        self.assertEqual(r.get("share_attempts"), 1)


if __name__ == "__main__":
    unittest.main()
