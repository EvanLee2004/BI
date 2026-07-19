#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书57·B-5：前端错误只写日志 + 限流/去重/轮转。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import frontend_errors  # noqa: E402


class TestFrontendErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "数据").mkdir()
        self.cfg = {"data_dir": "数据"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_and_stats(self):
        r = frontend_errors.record_frontend_error(
            {"message": "boom_test_xyz", "stack": "at x:1\nat y:2", "page": "/"},
            cfg=self.cfg,
            root=self.root,
        )
        self.assertTrue(r.get("ok"))
        path = self.root / "数据" / "前端错误.log"
        self.assertTrue(path.is_file())
        line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        o = json.loads(line)
        self.assertEqual(o["message"], "boom_test_xyz")
        self.assertNotIn("password", o)
        st = frontend_errors.frontend_error_stats(cfg=self.cfg, root=self.root)
        self.assertGreaterEqual(st["count_24h"], 1)
        self.assertTrue(st["yellow"])

    def test_dedup_counts(self):
        for _ in range(3):
            frontend_errors.record_frontend_error(
                {"message": "same_err", "page": "/p"},
                cfg=self.cfg,
                root=self.root,
            )
        path = self.root / "数据" / "前端错误.log"
        lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        last = lines[-1]
        self.assertGreaterEqual(last.get("dedup_count", 1), 2)


if __name__ == "__main__":
    unittest.main()
