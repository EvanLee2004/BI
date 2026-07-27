# -*- coding: utf-8 -*-
"""2.6.6·T1：health business_gaps 结构化 + 黄条收起逻辑源码守卫。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class TestBusinessGapsOnHealth(unittest.TestCase):
    def test_health_includes_business_gaps_when_authed(self):
        """登录会话下 /api/health 应带 business_gaps（缺月列表/未归属计数）。"""
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        # 不强制全量 refresh：create_app 可读空 summary；business_gaps 仍应给出结构
        app = server.create_app(cfg, root=ROOT)
        c = TestClient(app)
        # 匿名：business_gaps 仅登录后（2.6.6·T1 authed-only）
        r0 = c.get("/api/health")
        self.assertEqual(r0.status_code, 200)
        body0 = r0.json()
        self.assertNotIn(
            "business_gaps",
            body0,
            "匿名 /api/health 不得暴露 business_gaps",
        )

        import json

        rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("accounts") or []
        admin = next(a for a in rows if a.get("权限") == "管理员")
        lr = c.post("/api/v1/login", json={"account": admin["账号"], "password": admin["密码"]})
        self.assertIn(lr.status_code, (200, 303), lr.text[:200])
        r = c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("business_gaps", body, body.keys())
        g = body["business_gaps"]
        self.assertIn("manual_missing_months", g)
        self.assertIn("manual_missing_count", g)
        self.assertIn("manual_impact", g)
        self.assertIn("manual_owner", g)
        self.assertIn("unassigned_count", g)
        self.assertIsInstance(g["manual_missing_months"], list)
        self.assertIsInstance(g["manual_missing_count"], int)
        self.assertIsInstance(g["unassigned_count"], int)

    def test_manual_missing_months_reflected(self):
        """故意空 manual → missing_count 与列表非空（不依赖生产数据）。"""
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from profit.budget_manual import manual_missing_months
        import loaders

        cfg = loaders.load_config(ROOT)
        miss = manual_missing_months(cfg, {}, 2026, 7)
        self.assertEqual(len(miss), 7)
        self.assertEqual(miss[0], "2026-01")


class TestAdminHealthCollapseSource(unittest.TestCase):
    def test_admin_layout_has_scroll_esc_outside(self):
        src = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        # scroll 不冒泡：须 wheel/touchmove + 可滚容器挂接
        self.assertIn("onHealthWheelOrTouch", src)
        self.assertIn("attachHealthScrollTargets", src)
        self.assertIn("onHealthKey", src)
        self.assertIn("onHealthPointerDown", src)
        self.assertIn("admin-health-pop", src)
        self.assertIn("health-gaps", src)
        self.assertIn("businessGaps", src)
        self.assertIn("Escape", src)

    def test_bunav_unassigned_gap_testid(self):
        """2.6.10 V-1：看端不再渲染未归属橙色提示；管理端体检块仍保留。"""
        src = (ROOT / "frontend/src/components/BuNav.vue").read_text(encoding="utf-8")
        self.assertNotIn("bu-nav-unassigned-gap", src)
        self.assertNotIn("unassignedNote", src)
        self.assertNotIn("不进各 BU", src)
        admin = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn("未归属", admin)


if __name__ == "__main__":
    unittest.main()
