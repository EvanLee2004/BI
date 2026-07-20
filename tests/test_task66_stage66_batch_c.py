#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书66·C：VM 字段清单生成闸 + 缺字段空态不抛。"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestVmGenGate(unittest.TestCase):
    def test_gen_vm_ts_check_clean(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_vm_ts.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_cockpit_fields_listed(self):
        sys.path.insert(0, str(ROOT / "src"))
        from viewmodels import CockpitVM

        text = (ROOT / "frontend" / "src" / "types" / "vm.ts").read_text(encoding="utf-8")
        for k in CockpitVM.model_fields:
            self.assertIn(f'"{k}"', text, f"missing in GEN: {k}")


class TestVmMissingFieldEmpty(unittest.TestCase):
    """关键组件对缺字段：读可选链/默认，不假设全字段必有。"""

    def test_kpi_and_pl_vue_optional(self):
        for rel in (
            "frontend/src/components/KpiCards.vue",
            "frontend/src/components/PLTable.vue",
            "frontend/src/components/ExpenseSection.vue",
            "frontend/src/components/LedgerTable.vue",
            "frontend/src/cockpit/useCockpitVm.ts",
        ):
            p = ROOT / rel
            if not p.is_file():
                continue
            t = p.read_text(encoding="utf-8")
            # 不得对 vm 根做无防护的强制非空断言后立即深层点取（粗闸）
            self.assertNotIn("vm!.kpi!", t)
            self.assertNotIn("as CockpitVM)", t.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
