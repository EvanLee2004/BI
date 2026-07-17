#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B3：_assemble_vm 单一组装 + 薄包装。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import core  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import viewmodels  # noqa: E402

FAKE = ROOT / "_golden_data"


class TestAssembleVm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FAKE.exists():
            raise unittest.SkipTest("缺 _golden_data")
        cfg = loaders.load_config(ROOT)
        cfg = dict(cfg)
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "_golden_data/看板.db"
        cfg["zhiyun_auto_fetch"] = False
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            cls.summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        cls.cfg = cfg

    def test_cockpit_has_structured_fields(self):
        import os

        old = os.environ.get("KANBAN_FRONTEND")
        os.environ["KANBAN_FRONTEND"] = "vue"
        try:
            vm = viewmodels.build_cockpit_vm(self.summary, self.cfg)
            self.assertEqual(vm.scope, "整体")
            self.assertTrue(vm.period_keys)
            self.assertTrue(vm.kpi.cards_by_period)
            self.assertTrue(vm.pl.table_by_period)
            self.assertTrue(vm.trend.y_axis_ticks)
            # vue 路径：HTML 字段空
            self.assertEqual(vm.kpi.body_by_period, {})
            self.assertEqual(vm.pl.body_by_period, {})
        finally:
            if old is None:
                os.environ.pop("KANBAN_FRONTEND", None)
            else:
                os.environ["KANBAN_FRONTEND"] = old

    def test_wrappers_call_assemble(self):
        src = (ROOT / "src" / "viewmodels" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("def _assemble_vm(", src)
        self.assertIn('_assemble_vm(summary, views, scope="整体"', src)
        self.assertIn('_assemble_vm(summary, views, scope="BU"', src)


if __name__ == "__main__":
    unittest.main()
