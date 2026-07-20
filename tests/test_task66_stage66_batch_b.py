#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·B：增量 recompute ≡ 强制全量；含随机手填/调整/撤销序列。"""

from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("KANBAN_OFFLINE", "1")


def _num_key(summary: dict) -> dict:
    import api_v1

    n = api_v1.extract_numbers(summary)
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
        t0 = time.perf_counter()
        rp.do_full(cfg, ROOT, "test-b")
        cls.t_full = time.perf_counter() - t0
        cls.base = _num_key(_state["summary"])

    def test_source_fp_set(self):
        self.assertTrue(self._state.get("source_fp"))

    def test_summary_only_equals_rebuild_std(self):
        """同源未变：默认跳过 std vs rebuild_std=True 数字全等。"""
        rp, st = self.rp, self._state
        t0 = time.perf_counter()
        rp.do_recompute(self.cfg, self.root, rebuild_std=True)
        t_std = time.perf_counter() - t0
        a = _num_key(st["summary"])
        t0 = time.perf_counter()
        rp.do_recompute(self.cfg, self.root, rebuild_std=False)
        t_inc = time.perf_counter() - t0
        b = _num_key(st["summary"])
        self.assertEqual(a, b)
        path = Path(os.environ.get("KANBAN_SCRATCH") or "/tmp") / "recompute_bench.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"full_s={self.t_full:.4f}\nrebuild_std_s={t_std:.4f}\nsummary_only_s={t_inc:.4f}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        self.assertLessEqual(t_inc, t_std * 3 + 1.0)

    def test_manual_then_both_paths(self):
        """手填写入后：增量与强制 rebuild 结果一致（临时库）。"""
        import db

        tmp = Path(tempfile.mkdtemp(prefix="t66b_"))
        (tmp / "_golden_data").mkdir()
        shutil.copy2(ROOT / "_golden_data" / "看板.db", tmp / "_golden_data" / "看板.db")
        cfg = dict(self.cfg)
        cfg["db_path"] = str((tmp / "_golden_data" / "看板.db").resolve())
        root = tmp
        rp, st = self.rp, self._state
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

    def test_random_ops_incremental_equals_force_full(self):
        """随机手填/调整/撤销 × N：生产路径结果 == do_full 强制全量（逐字段 numbers）。"""
        import db

        tmp = Path(tempfile.mkdtemp(prefix="t66b_rand_"))
        (tmp / "_golden_data").mkdir()
        shutil.copy2(ROOT / "_golden_data" / "看板.db", tmp / "_golden_data" / "看板.db")
        # 复制 xlsx 以便 do_full 指纹/读源
        for name in ("下单.xlsx", "回款记录.xlsx", "项目明细.xlsx", "内部译员.xlsx", "收单台账.xlsx"):
            src = ROOT / "_golden_data" / name
            if src.is_file():
                shutil.copy2(src, tmp / "_golden_data" / name)
        cfg = dict(self.cfg)
        cfg["db_path"] = str((tmp / "_golden_data" / "看板.db").resolve())
        root = tmp
        rp, st = self.rp, self._state
        rp.do_full(cfg, root, "test-b-rand0")

        conn = db.connect(cfg, root)
        try:
            row = conn.execute(
                "SELECT 定位键, 销售 FROM std_下单 WHERE 已删除=0 AND 定位键 IS NOT NULL LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertTrue(row, "need a std_下单 row")
        loc, sales0 = str(row[0]), str(row[1] or "员工001")

        rng = random.Random(66)
        N = 8
        for i in range(N):
            kind = rng.choice(["manual", "manual", "adjust", "revoke"])
            conn = db.connect(cfg, root)
            try:
                if kind == "manual":
                    amt = float(rng.randint(0, 50000)) / 100.0
                    db.set_manual(
                        conn, "2026-06", "其他损益", amt, f"t66b-{i}", 范围="全公司"
                    )
                    prod_rebuild = False
                elif kind == "adjust":
                    new_sales = "员工028" if sales0 != "员工028" else "员工001"
                    try:
                        db.add_adjustment(
                            conn,
                            f"t66b-{i}",
                            "std_下单",
                            loc,
                            "销售",
                            new_sales,
                            "task66 random",
                            "改值",
                        )
                    except ValueError:
                        # 定位冲突等 → 改手填
                        db.set_manual(
                            conn, "2026-06", "其他损益", float(i), f"t66b-{i}", 范围="全公司"
                        )
                        prod_rebuild = False
                    else:
                        prod_rebuild = True
                else:  # revoke latest
                    rows = db.list_adjustments(conn) or []
                    active = [r for r in rows if not r.get("已撤销") and r.get("id")]
                    if active:
                        aid = int(active[-1]["id"])
                        db.revoke_adjustment(conn, aid)
                        prod_rebuild = True
                    else:
                        db.set_manual(
                            conn, "2026-06", "其他损益", float(i + 1), f"t66b-{i}", 范围="全公司"
                        )
                        prod_rebuild = False
            finally:
                conn.close()

            # 生产路径
            rp.do_recompute(cfg, root, rebuild_std=prod_rebuild)
            inc = _num_key(st["summary"])
            # 强制全量（同源文件）
            rp.do_full(cfg, root, f"test-b-rand-full-{i}")
            full = _num_key(st["summary"])
            self.assertEqual(inc, full, f"step {i} kind={kind} numbers diverge")

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
