# -*- coding: utf-8 -*-
"""2.6.9 S5：智云 0 行禁止 unlink 本地 xlsx，改为 stale 重命名。"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestZeroRowNoUnlink(unittest.TestCase):
    def test_fetch_zhiyun_no_unlink_on_empty(self):
        src = (ROOT / "src" / "ingest" / "fetch_zhiyun.py").read_text(encoding="utf-8")
        # 0 行分支不得 local.unlink()
        self.assertIn("stale-", src)
        self.assertIn("local.rename", src)
        # 硬删调用不得出现在 0 行路径说明附近；允许其它处
        # 守卫：空抓取说明文案含 stale
        self.assertIn("stale", src)
        self.assertNotIn("local.unlink()", src)


if __name__ == "__main__":
    unittest.main()
