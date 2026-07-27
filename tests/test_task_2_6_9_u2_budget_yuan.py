# -*- coding: utf-8 -*-
"""2.6.9 U-2：业绩目标 万↔元↔分 换算与展示口径（库内分不动）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from money import fen_to_yuan, yuan_to_fen  # noqa: E402


class TestBudgetUnitYuan(unittest.TestCase):
    def test_20189_wan_yuan_fen(self):
        """任务书例：20189 万 ↔ 201_890_000 元 ↔ 20_189_000_000 分。"""
        wan = 20189
        yuan = wan * 10_000
        fen = yuan_to_fen(yuan)
        self.assertEqual(yuan, 201_890_000)
        self.assertEqual(int(fen), 20_189_000_000)
        self.assertEqual(fen_to_yuan(fen), yuan)
        # 元→万（展示旧口径）
        self.assertEqual(yuan / 10_000, wan)

    def test_local_db_year_budget_display_forms(self):
        """本地 sample：下单年预算 全公司 9000000000 分 → 9000 万 = 90_000_000 元。"""
        fen = 9_000_000_000
        yuan = fen_to_yuan(fen)
        wan = yuan / 10_000
        self.assertEqual(yuan, 90_000_000)
        self.assertEqual(wan, 9000)


if __name__ == "__main__":
    unittest.main()
