#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书51·B4：resolve_expense_view_access 行为与 force_whitelist 分叉。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import authz  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class TestResolveExpenseViewAccess(unittest.TestCase):
    def test_admin_detail_full_columns(self):
        fb, hs, aud = authz.resolve_expense_view_access(
            "admin", None, None, cfg={}, force_whitelist=False, table="费用明细"
        )
        self.assertIsNone(fb)
        self.assertTrue(hs)  # 54.12 R-01 全端隐工资
        self.assertEqual(aud, "admin")

    def test_admin_ledger_whitelist(self):
        fb, hs, aud = authz.resolve_expense_view_access(
            "admin", None, None, cfg={}, force_whitelist=True
        )
        self.assertIsNone(fb)
        self.assertTrue(hs)  # R-01
        self.assertEqual(aud, "view")
        fb2, _, aud2 = authz.resolve_expense_view_access(
            "admin", None, "甲BU", cfg={}, force_whitelist=True
        )
        self.assertEqual(fb2, "甲BU")
        self.assertEqual(aud2, "view_bu")

    def test_main_hide_salary_default(self):
        vacc = {"账号": "m", "权限": "整体"}
        fb, hs, aud = authz.resolve_expense_view_access(
            None, vacc, None, cfg={}, force_whitelist=True
        )
        self.assertTrue(hs)
        self.assertEqual(aud, "view")
        # R-01：配置开关已废止，即使传 overall_see_salary=True 仍隐
        _, hs2, _ = authz.resolve_expense_view_access(
            None, vacc, None, cfg={"overall_see_salary": True}, force_whitelist=False, table="费用明细"
        )
        self.assertTrue(hs2)

    def test_bu_force_own(self):
        vacc = {"账号": "b", "权限": "BU", "可见BU": ["甲BU"]}
        fb, hs, aud = authz.resolve_expense_view_access(
            None, vacc, None, cfg={}, force_whitelist=True
        )
        self.assertEqual(fb, "甲BU")
        self.assertTrue(hs)  # R-01 BU 亦隐工资
        self.assertEqual(aud, "view_bu")

    def test_anon_401(self):
        with self.assertRaises(HTTPException) as cm:
            authz.resolve_expense_view_access(None, None, None, cfg={}, force_whitelist=True)
        self.assertEqual(cm.exception.status_code, 401)

    def test_routes_use_shared(self):
        c = (ROOT / "src" / "routes" / "cockpit.py").read_text(encoding="utf-8")
        d = (ROOT / "src" / "routes" / "data_api.py").read_text(encoding="utf-8")
        self.assertIn("resolve_expense_view_access", c)
        self.assertIn("force_whitelist=True", c)
        self.assertIn("resolve_expense_view_access", d)
        self.assertIn("force_whitelist=False", d)


if __name__ == "__main__":
    unittest.main()
