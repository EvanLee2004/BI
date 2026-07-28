# -*- coding: utf-8 -*-
"""2.7.0：架构双源 / 文档守卫 / 旁路 int 分 / 前端 v1 路径。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestProfitRankingV1Path(unittest.TestCase):
    def test_profit_structure_uses_v1(self):
        src = (ROOT / "frontend/src/components/ProfitStructure.vue").read_text(encoding="utf-8")
        self.assertIn("/api/v1/rankings/profit", src)
        # 主路径不再硬编码旧 URL 为唯一请求（旧路径可出现在注释）
        self.assertNotRegex(
            src,
            r"fetch\(\s*[`'\"]/api/profit_ranking",
        )

    def test_rankings_dual_still_full(self):
        src = (ROOT / "frontend/src/components/RankingsDual.vue").read_text(encoding="utf-8")
        self.assertIn("/api/v1/rankings/full", src)

    def test_data_api_shared_impl(self):
        src = (ROOT / "src/routes/data_api.py").read_text(encoding="utf-8")
        self.assertIn("def _profit_ranking_impl", src)
        self.assertIn('/api/v1/rankings/profit"', src)
        self.assertIn('/api/profit_ranking"', src)
        self.assertIn('/api/v1/admin/detail"', src)


class TestMoneyTailNoRoundFloat(unittest.TestCase):
    def test_core_no_amount_round_float(self):
        src = (ROOT / "src/core.py").read_text(encoding="utf-8")
        self.assertNotIn("round(float(out[name][\"amount\"])", src)
        self.assertNotIn("round(float(led2.get", src)

    def test_structure_int_direct(self):
        src = (ROOT / "src/domain/pl/structure.py").read_text(encoding="utf-8")
        self.assertNotIn("round(float(led.get(led_cat)", src)
        self.assertIn("2.7.0 C2", src)

    def test_profit_no_amount_round_float(self):
        for p in (ROOT / "src/profit").rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            # 允许注释；禁止金额链 round(float(exp 或 round(float(led
            if re.search(r"round\(\s*float\(\s*exp\[", text):
                self.fail(f"{p.name} still has round(float(exp[")
            if re.search(r"round\(\s*float\(\s*led\.get", text):
                self.fail(f"{p.name} still has round(float(led.get")


class TestZIndexTokens(unittest.TestCase):
    def test_toast_and_bu_use_tokens(self):
        toast = (ROOT / "frontend/src/styles/components/Toast.css").read_text(encoding="utf-8")
        bu = (ROOT / "frontend/src/styles/components/BUPage.css").read_text(encoding="utf-8")
        tokens = (ROOT / "frontend/src/styles/tokens.css").read_text(encoding="utf-8")
        self.assertIn("--z-toast-top", tokens)
        self.assertIn("--z-bu-transition", tokens)
        self.assertIn("var(--z-toast-top", toast)
        self.assertIn("var(--z-bu-transition", bu)


class TestVersion270(unittest.TestCase):
    def test_version_file(self):
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(ver, "2.7.0")


if __name__ == "__main__":
    unittest.main()
