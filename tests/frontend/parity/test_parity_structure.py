#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·3：DOM 结构闸（静态/结构断言）。

Playwright 像素闸在沙箱可能不可用：以 VM 显示串与组件文件存在性 + 无前端金额四则 为门禁。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "frontend" / "src"
sys.path.insert(0, str(ROOT / "src"))

REQUIRED = [
    "api/client.ts",
    "stores/cockpit.ts",
    "components/KpiCards.vue",
    "components/TrendChart.vue",
    "components/PLTable.vue",
    "components/ExpenseSection.vue",
    "components/RankingsDual.vue",
    "components/ReceiptsCard.vue",
    "components/DailyQuery.vue",
    "components/LedgerTable.vue",
    "components/ExpenseTrend.vue",
    "components/PeriodPicker.vue",
    "components/ThemeToggle.vue",
    "components/LoginView.vue",
    "components/BUPage.vue",
    "echarts-theme.ts",
]


class TestFrontendScaffold(unittest.TestCase):
    def test_required_components_exist(self):
        for rel in REQUIRED:
            self.assertTrue((FE / rel).is_file(), f"缺组件 {rel}")

    def test_dist_built(self):
        self.assertTrue((ROOT / "frontend" / "dist" / "index.html").is_file(), "frontend/dist 须进 git")

    def test_no_amount_math_in_vue(self):
        """铁律2：Vue 源中不得对金额做四则（宽松：禁止 /100 /10000 *0. 等模式）。"""
        bad = re.compile(r"(/\s*10000|/\s*100\b|\*\s*0\.0|\.toFixed\s*\()")
        for p in FE.rglob("*.{vue,ts}"):
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            # 允许注释
            for i, line in enumerate(text.splitlines(), 1):
                if line.strip().startswith("//") or line.strip().startswith("*"):
                    continue
                if bad.search(line):
                    self.fail(f"疑似金额运算 {p}:{i}: {line.strip()}")

    def test_client_uses_vm_api(self):
        client = (FE / "api" / "client.ts").read_text(encoding="utf-8")
        self.assertIn("/api/v1/vm/cockpit", client)
        self.assertIn("/api/v1/vm/bu/", client)


if __name__ == "__main__":
    unittest.main()
