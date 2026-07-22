#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S4.B KPI count-up 铁律守卫：不解析 value_disp、终帧直赋。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


class TestCountUp230(unittest.TestCase):
    def test_no_value_disp_parse(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        # 禁止从 disp 反解数字
        forbidden = [
            r"parseFloat\s*\([^)]*disp",
            r"Number\s*\([^)]*disp",
            r"parseInt\s*\([^)]*disp",
            r"replace\s*\(\s*/,/g[^)]*\)[^;]*disp",
            r"disp[^;\n]*replace\s*\(\s*/,/g",
        ]
        for pat in forbidden:
            self.assertIsNone(re.search(pat, src, re.I), f"forbidden pattern: {pat}")

    def test_final_assigns_value_disp(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        self.assertIn("onDone(disp)", src)
        self.assertIn("isAnimatableDisp", src)

    def test_non_numeric_no_anim(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        self.assertIn("isAnimatableDisp", src)
        # 2.3.1：播放闸改为 reduced-motion（仍须终帧/非数字守卫）
        self.assertIn("prefersReducedMotion", src)

    def test_motion_gate_not_theme_only(self):
        src = (FE / "utils" / "countUp.ts").read_text(encoding="utf-8")
        self.assertIn("prefersReducedMotion", src)
        self.assertNotIn("fxLevel() !== 1", src)
        self.assertNotIn("fxLevel()===1", src)

    def test_kpi_uses_countup(self):
        kpi = (FE / "components" / "KpiCards.vue").read_text(encoding="utf-8")
        self.assertIn("CountUpNumber", kpi)


if __name__ == "__main__":
    unittest.main()
