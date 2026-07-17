#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B8：frontend/src/types/vm.ts + vue-tsc 入链。"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"


class TestFrontendTypes(unittest.TestCase):
    def test_vm_ts_exists(self):
        p = FE / "src" / "types" / "vm.ts"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        for key in (
            "CockpitVM",
            "BUPageVM",
            "KpiCardsVM",
            "TrendVM",
            "PLTableVM",
            "ExpenseVM",
            "RankingsVM",
            "ReceiptsVM",
            "LedgerVM",
            "period_months",
            "y_axis_interval",
        ):
            self.assertIn(key, text)

    def test_store_typed_page_vm(self):
        src = (FE / "src" / "stores" / "cockpit.ts").read_text(encoding="utf-8")
        self.assertIn("PageVM", src)
        self.assertNotIn("Record<string, unknown> | null", src)

    def test_package_typecheck_script(self):
        pkg = (FE / "package.json").read_text(encoding="utf-8")
        self.assertIn("vue-tsc --noEmit", pkg)
        self.assertIn('"typecheck"', pkg)

    def test_verify_runs_vue_tsc(self):
        sh = (ROOT / "tests" / "run_verify.sh").read_text(encoding="utf-8")
        self.assertIn("vue-tsc", sh)
        self.assertIn("typecheck", sh)

    def test_vue_tsc_no_emit_green(self):
        if not (FE / "node_modules").is_dir():
            self.skipTest("无 node_modules")
        r = subprocess.run(
            ["npm", "run", "typecheck"],
            cwd=str(FE),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stdout + "\n" + r.stderr)


if __name__ == "__main__":
    unittest.main()
