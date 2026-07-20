#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·B：增量 recompute（跳过 std）≡ 强制 rebuild_std 全量路径。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KANBAN_OFFLINE", "1")


def _num_key(summary: dict) -> dict:
    """可比对的关键数字（去掉 meta 时间戳类）。"""
    import api_v1

    n = api_v1.extract_numbers(summary)
    # 去掉易变非金额
    n.pop("built_at", None)
    return n


class TestIncrementalRecompute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import loaders
        import refresh_pipeline as rp
        from app_state import _state

        cls.rp = rp
        cls._state = _state
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cls.cfg = cfg
        cls.root = ROOT
        # 全量一次
        t0 = time.perf_counter()
        rp.do_full(cfg, ROOT, "test-b")
        cls.t_full = time.perf_counter() - t0
        cls.base = _num_key(_state["summary"])

    def test_source_fp_set(self):
        self.assertTrue(self._state.get("source_fp"))

    def test_summary_only_equals_rebuild_std(self):
        """同源未变：默认跳过 std vs rebuild_std=True 数字全等。"""
        rp = self.rp
        st = self._state
        # 强制路径
        t0 = time.perf_counter()
        rp.do_recompute(self.cfg, self.root, rebuild_std=True)
        t_std = time.perf_counter() - t0
        a = _num_key(st["summary"])
        # 增量路径
        t0 = time.perf_counter()
        rp.do_recompute(self.cfg, self.root, rebuild_std=False)
        t_inc = time.perf_counter() - t0
        b = _num_key(st["summary"])
        self.assertEqual(a, b)
        # 记录耗时（门禁非硬）
        path = Path(os.environ.get("KANBAN_SCRATCH") or "/tmp") / "recompute_bench.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"full_s={self.t_full:.4f}\nrebuild_std_s={t_std:.4f}\nsummary_only_s={t_inc:.4f}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        # 增量应不慢于强制（允许抖动）
        self.assertLessEqual(t_inc, t_std * 3 + 1.0)

    def test_manual_then_both_paths(self):
        """手填写入后：增量与强制 rebuild 结果一致（写独立临时库，不污染 golden）。"""
        import db
        import loaders
        import shutil

        tmp = Path(tempfile.mkdtemp(prefix="t66b_"))
        # 最小：复制 golden db 到 tmp
        (tmp / "_golden_data").mkdir()
        shutil.copy2(ROOT / "_golden_data" / "看板.db", tmp / "_golden_data" / "看板.db")
        cfg = dict(self.cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = str((tmp / "_golden_data" / "看板.db").resolve())
        root = tmp
        rp, st = self.rp, self._state
        # 先全量到该库
        rp.do_full(cfg, root, "test-b-manual")
        conn = db.connect(cfg, root)
        try:
            db.set_manual(conn, "2026-06", "其他损益", 100.0, "test66b", 范围="全公司")
        finally:
            conn.close()
        rp.do_recompute(cfg, root, rebuild_std=False)
        inc = _num_key(st["summary"])
        rp.do_recompute(cfg, root, rebuild_std=True)
        full = _num_key(st["summary"])
        self.assertEqual(inc, full)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
