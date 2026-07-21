#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""期间费用：按类别 / 按利润中心 / 按部门 点击行 → 右侧抽屉展开明细。

门禁：
1. 三态走抽屉（Teleport body + exp-drawer-panel/mask + openDrawer）
2. 进度条列表仍在（exp-list / exp-bar-row / bar_w）
3. 无 master-detail、无 openFine / 行内 ev-fine
4. 仍绑定 by_category / by_pc / by_dept 与 openRow.fine（无前端金额四则）
5. 环形 donut 不动
6. dist 构建后含 exp-drawer-panel、不含 exp-md-detail
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"
EXP = FE / "components" / "ExpenseSection.vue"
DIST = ROOT / "frontend" / "dist"


def _strip_comments(src: str) -> str:
    src = re.sub(r"<!--[\s\S]*?-->", "", src)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//.*?$", "", src, flags=re.M)
    return src


class TestExpenseDrawer(unittest.TestCase):
    def setUp(self):
        self.src = EXP.read_text(encoding="utf-8")
        self.code = _strip_comments(self.src)

    def test_drawer_structure_and_open_close(self):
        for token in (
            "exp-drawer-panel",
            "exp-drawer-mask",
            'Teleport to="body"',
            "openDrawer",
            "closeDrawer",
            "drawerOpen",
        ):
            self.assertIn(token, self.src, f"须含抽屉结构/开合: {token}")

    def test_hbar_list_still_present(self):
        for token in ("exp-list", "exp-bar-row", "ev-track", "bar_w"):
            self.assertIn(token, self.src, f"进度条列表须保留: {token}")

    def test_no_master_detail_or_inline_expand(self):
        for banned in ("exp-md-list", "exp-md-detail", "master-detail", "openFine"):
            self.assertNotIn(banned, self.code, f"不得再有: {banned}")
        self.assertNotRegex(
            self.code,
            r'class="[^"]*\bev-fine\b',
            "不得再有行内嵌 fine 列表 class=ev-fine",
        )

    def test_binds_vm_views_not_frontend_math(self):
        for key in ("by_category", "by_pc", "by_dept"):
            self.assertIn(key, self.code, f"须绑定 views.{key}")
        self.assertIn("openRow.fine", self.code)
        money_ops = re.findall(
            r"\b(amt|value|amount|金额)\s*[\+\-\*/]",
            self.code,
            flags=re.I,
        )
        self.assertEqual(money_ops, [], f"费用构成组件不得前端运算金额: {money_ops}")

    def test_donut_mode_unchanged(self):
        self.assertTrue(
            "mode === 'donut'" in self.code or 'mode === "donut"' in self.code,
            "按大类 donut 分支须保留",
        )
        self.assertIn("EchartsHost", self.code)
        self.assertIn("exp-tab-donut", self.src)

    def test_dist_if_present_has_drawer(self):
        assets = DIST / "assets"
        if not assets.is_dir():
            self.skipTest("dist 未构建")
        boot = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in assets.glob("boot-cockpit-*.js")
        )
        self.assertTrue(boot.strip(), "须有 boot-cockpit chunk")
        self.assertIn("exp-drawer-panel", boot, "dist 须含 exp-drawer-panel")
        self.assertNotIn("exp-md-detail", boot, "dist 不得含 exp-md-detail")


if __name__ == "__main__":
    unittest.main()
