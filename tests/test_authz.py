#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·1：RBAC 雏形能力矩阵。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import authz  # noqa: E402


class TestAuthzMatrix(unittest.TestCase):
    def test_three_roles(self):
        m = authz.role_matrix_for_tests()
        # 管理员：全能力
        self.assertTrue(m["管理员"][authz.CAN_ADMIN])
        self.assertTrue(m["管理员"][authz.CAN_EXPORT])
        self.assertTrue(m["管理员"][authz.CAN_VIEW_SALARY])
        # 整体：默认可导出、不可管、不可见工资（overall_see_salary=False）
        self.assertFalse(m["整体"][authz.CAN_ADMIN])
        self.assertTrue(m["整体"][authz.CAN_EXPORT])
        self.assertFalse(m["整体"][authz.CAN_VIEW_SALARY])
        # BU：可导出+本 BU 工资，不可管
        self.assertFalse(m["BU"][authz.CAN_ADMIN])
        self.assertTrue(m["BU"][authz.CAN_EXPORT])
        self.assertTrue(m["BU"][authz.CAN_VIEW_SALARY])

    def test_overall_salary_config(self):
        acc = {"账号": "m", "权限": "整体"}
        self.assertFalse(authz.can_view_salary(acc, cfg={}))
        self.assertTrue(authz.can_view_salary(acc, cfg={"overall_see_salary": True}))

    def test_sso_disabled_by_default(self):
        import sso_feishu

        self.assertFalse(sso_feishu.is_enabled({}))
        self.assertIsNone(sso_feishu.authorize_url({}))


if __name__ == "__main__":
    unittest.main()
