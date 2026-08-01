#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准门禁的测试文件登记守卫。"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "verify_test_inventory.py"
PROBE = ROOT / "tests" / "test_inventory_guard_probe.py"


class TestVerifyTestInventory(unittest.TestCase):
    def _run_guard(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_current_non_optional_tests_are_registered(self):
        result = self._run_guard()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unregistered_test_file_fails_with_its_path(self):
        PROBE.write_text("import unittest\\n", encoding="utf-8")
        try:
            result = self._run_guard()
        finally:
            PROBE.unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests/test_inventory_guard_probe.py", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
