#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09计划（费用双视角+部门预算执行）：分组守恒/软列降级/部门预算块/渲染开关。"""
from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import columns  # noqa: E402
import loaders  # noqa: E402
import periods  # noqa: E402
import render  # noqa: E402
from profit import (build_dept_budget_block, compute_expenses_by_group,  # noqa: E402
                    compute_ledger_expenses)

CFG = loaders.load_config()
START, END = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)

# 台账合成行：表头带新列（预算归属部门）
HDR = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]
ROWS = [
    ("2026年3月", "2026-03-05", 100.0, "语言", "管理费用", "办公用品", "运保"),
    ("2026年3月", "2026-03-08", 50.0, "数据", "管理费用", "差旅费", "项目中心"),
    ("2026年4月", "2026-04-02", 30.0, "",    "市场费用", "",       ""),        # BU/部门/细类均未填
    ("2026年4月", "2026-04-03", 999.0, "语言", "生产成本-译费", "译费", "运保"),  # 白名单外→两个视角都不算
    ("2026年5月", None, None, None, None, None, None),                          # 全空行
]


class TestGroupAggregation(unittest.TestCase):
    def _l(self):
        return columns.resolve_ledger_columns(HDR)

    def test_conservation_both_views(self):
        """守恒红线：各组合计（含未分类）== 台账白名单费用合计，两个视角同验。"""
        lcols = self._l()
        led, _ = compute_ledger_expenses(ROWS, 2026, START, END, CFG, lcols)
        total = sum(led.values())
        for field in ("预算归属部门", "业务BU"):
            rows = compute_expenses_by_group(ROWS, 2026, START, END, CFG, lcols, field)
            self.assertAlmostEqual(sum(v for _, v, _ in rows), total, places=2, msg=field)

    def test_groups_and_unfilled(self):
        rows = compute_expenses_by_group(ROWS, 2026, START, END, CFG, self._l(), "预算归属部门")
        d = {g: v for g, v, _ in rows}
        self.assertEqual(d, {"运保": 100.0, "项目中心": 50.0, "未分类": 30.0})
        fine = dict(rows[0][2])  # 运保 的细类
        self.assertEqual(fine, {"办公用品": 100.0})

    def test_whitelist_excluded(self):
        rows = compute_expenses_by_group(ROWS, 2026, START, END, CFG, self._l(), "预算归属部门")
        self.assertNotIn(999.0, [v for _, v, _ in rows])  # 白名单外的生产成本不进视角

    def test_soft_column_missing_returns_none(self):
        """老台账没「预算归属部门」列：resolve 不报错、分组返回 None（前端降级）。"""
        old_hdr = HDR[:-1]
        lcols = columns.resolve_ledger_columns(old_hdr)  # 不抛异常
        self.assertNotIn("预算归属部门", lcols)
        old_rows = [r[:-1] for r in ROWS]
        self.assertIsNone(compute_expenses_by_group(old_rows, 2026, START, END, CFG, lcols, "预算归属部门"))


class TestDeptBudgetBlock(unittest.TestCase):
    DEPT_ROWS = [("运保", 80.0, []), ("项目中心", 120.0, [])]

    def test_empty_shell_when_not_filled(self):
        """迭代18：没填也返回空壳（year + rows=[]），供空态卡渲染对称布局。"""
        b = build_dept_budget_block(None, self.DEPT_ROWS, 2026)
        self.assertEqual(b["year"], 2026)
        self.assertEqual(b["rows"], [])
        b2 = build_dept_budget_block({"2025": {"运保": 1}}, self.DEPT_ROWS, 2026)
        self.assertEqual(b2["rows"], [])

    def test_rows_sorted_by_pct_desc(self):
        b = build_dept_budget_block({"2026": {"运保": 100.0, "项目中心": 600.0, "人力中心": 50.0}},
                                    self.DEPT_ROWS, 2026)
        self.assertEqual([r["dept"] for r in b["rows"]], ["运保", "项目中心", "人力中心"])  # 80%>20%>0%
        self.assertAlmostEqual(b["rows"][0]["pct"], 80.0)
        self.assertEqual(b["rows"][2]["used"], 0.0)  # 有预算无支出也列出

    def test_zero_target(self):
        b = build_dept_budget_block({"2026": {"运保": 0.0}}, self.DEPT_ROWS, 2026)
        self.assertIsNone(b["rows"][0]["pct"])  # 不除零

    def test_none_dept_rows(self):
        b = build_dept_budget_block({"2026": {"运保": 100.0}}, None, 2026)  # 老台账无列
        self.assertEqual(b["rows"][0]["used"], 0.0)


class TestRenderSwitches(unittest.TestCase):
    def test_dept_budget_card_retired(self):
        """迭代19：部门费用预算卡界面下线，render 恒空。"""
        for arg in (None, {"year": 2026, "rows": []},
                    {"year": 2026, "rows": [{"dept": "运保", "target": 100.0, "used": 130.0, "pct": 130.0}]}):
            self.assertEqual(render.render_dept_budget(arg), "")

    def test_hbar_degrade_paths(self):
        self.assertIn("无「预算归属部门」列", render._hbar_rows(None, "dept"))
        self.assertIn("本期无台账费用", render._hbar_rows([], "dept"))

    def test_hbar_unfilled_sinks_to_bottom(self):
        rows = [("未分类", 500.0, []), ("运保", 100.0, [])]
        html = render._hbar_rows(rows, "dept")
        self.assertLess(html.find("运保"), html.find("未分类"))
        self.assertIn("unfilled", html)


class TestLedgerRowDateMonthGuard(unittest.TestCase):
    """收单月份越界（收单日期空、退回月份）→ ledger_row_date 返 None + 体检计 date_bad，
    不再造出 (year,13,1) 这种无效日期被 date_in_range 静默剔除却不报警（code review #1）。"""

    def _l(self):
        return columns.resolve_ledger_columns(HDR)

    def _row(self, 月份):  # 收单日期留空→退回收单月份分支
        return (月份, "", 100.0, "语言", "管理费用", "办公用品", "运保")

    def test_valid_month_ok(self):
        for m in ("3", "12", "1"):
            self.assertEqual(periods.ledger_row_date(self._row(m), 2026, self._l())[:2], (2026, int(m)))

    def test_out_of_range_month_is_none(self):
        for bad in ("13", "0", "99", "-1"):
            self.assertIsNone(periods.ledger_row_date(self._row(bad), 2026, self._l()),
                              msg=f"收单月份={bad} 应判无效")

    def test_nonnumeric_month_is_none(self):
        self.assertIsNone(periods.ledger_row_date(self._row("三月"), 2026, self._l()))

    def test_health_counts_bad_month_as_date_bad(self):
        from profit import _scan_ledger_issues
        rows = [self._row("13"), self._row("3")]   # 一坏一好
        date_bad, _ = _scan_ledger_issues(rows, 2026, self._l())
        self.assertEqual(date_bad, 1)   # 越界月被计为"日期解析不出"→体检判黄，不再静默丢


if __name__ == "__main__":
    unittest.main(verbosity=2)
