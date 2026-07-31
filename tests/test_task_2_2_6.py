#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.7.2：下单未填部门整线下线门禁（原 2.2.6 批量归类 UX 产品面已退役）。

断言：OrderDept 视图/路由活入口消失；API order_depts 404；
费用未分类与通用 adjust/batch 仍在；排名无「待归类」诱导。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db
import loaders
import server  # noqa: E402

FE_ADMIN = ROOT / "frontend" / "src" / "admin"


class TestOrderDeptProductRetired372(unittest.TestCase):
    """产品面：页/导航/总览卡不可达。"""

    def test_orderdept_view_removed(self):
        self.assertFalse(
            (FE_ADMIN / "views" / "OrderDeptView.vue").is_file(),
            "OrderDeptView.vue 须删除",
        )

    def test_router_redirects_deep_link(self):
        src = (FE_ADMIN / "router.ts").read_text(encoding="utf-8")
        self.assertIn("review/orderdept", src)
        self.assertIn("redirect", src)
        self.assertNotIn("OrderDeptView", src)
        self.assertIn("admin-overview", src)

    def test_nav_and_overview_no_orderdept(self):
        layout = (FE_ADMIN / "layout" / "AdminLayout.vue").read_text(encoding="utf-8")
        overview = (FE_ADMIN / "views" / "ExceptionOverview.vue").read_text(encoding="utf-8")
        # 活入口（非注释）：导航 label / 总览卡 key / 可点 path
        self.assertNotIn("label: '下单未填部门'", layout)
        self.assertNotIn('label: "下单未填部门"', layout)
        self.assertNotIn("order_unfilled_dept", layout)
        self.assertNotIn("path: '/admin/review/orderdept'", layout)
        self.assertNotIn("order_unfilled_dept", overview)
        self.assertNotIn("path: '/admin/review/orderdept'", overview)
        self.assertNotIn("待归类", overview)
        # 费用未分类仍在
        self.assertIn("费用未分类", layout)
        self.assertIn("expense_unclassified", layout)
        self.assertIn("UnclassifiedView", (FE_ADMIN / "router.ts").read_text(encoding="utf-8"))


class TestUnfilledDeptWhereUnchanged(unittest.TestCase):
    """守恒：后端 unfilled 条件仍可用（排名置底），只是无产品入口。"""

    def test_constant_still_requires_nonzero_amount(self):
        from db.constants import UNFILLED_DEPT_WHERE

        w = UNFILLED_DEPT_WHERE
        self.assertIn("部门", w)
        self.assertIn("下单预估额", w)
        self.assertIn("<>0", w.replace(" ", ""))
        self.assertIn("IS NULL", w)


class TestOrderDeptsApiOffline372(unittest.TestCase):
    """专用 API 下线：404；通用 adjust/batch 仍在。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.tmp = tempfile.mkdtemp()
        cls.root = Path(cls.tmp)
        cls.cfg = loaders.load_config()
        conn = db.connect(cls.cfg, cls.root)
        conn.close()
        cls._orig_recompute = server.recompute
        server.recompute = lambda cfg, root=None, **k: server._state.__setitem__(
            "built_at", "RECOMPUTED"
        )
        server._state["admin_html"] = "ready"
        cls.app = server.create_app(cls.cfg, root=cls.root)
        cls.client = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post(
            "/admin/login",
            data={"account": "lushasha", "password": server.DEFAULT_PW},
        )
        # 登录可能 303/200，cookie 由 TestClient 持有
        assert r.status_code in (200, 303, 302), r.status_code

    @classmethod
    def tearDownClass(cls):
        server.recompute = cls._orig_recompute

    def test_order_depts_endpoint_offline(self):
        r = self.client.get("/api/v1/admin/order_depts")
        self.assertEqual(r.status_code, 404, r.text[:200])

    def test_exceptions_no_order_unfilled_key(self):
        r = self.client.get("/api/v1/admin/exceptions")
        self.assertEqual(r.status_code, 200, r.text[:200])
        data = r.json()
        self.assertNotIn("order_unfilled_dept", data)
        self.assertIn("expense_unclassified", data)

    def test_adjust_batch_still_exists(self):
        """通用批量调整机制保留（非 orderdept 专页）。"""
        # 空列表应被拒绝或返回业务错误，但路由须存在（非 404）
        r = self.client.post(
            "/api/v1/admin/adjust/batch",
            json={
                "目标表": "std_下单",
                "字段": "部门",
                "新值": "测试",
                "原因": "3.7.2 路由存在性",
                "类型": "改值",
                "定位键列表": [],
            },
        )
        self.assertNotEqual(r.status_code, 404)


class TestRankNoPendingClassifyInducement(unittest.TestCase):
    def test_no_pending_classify_copy_in_live_frontend(self):
        blob = ""
        for p in (ROOT / "frontend" / "src").rglob("*"):
            if p.suffix in (".vue", ".ts", ".css"):
                blob += p.read_text(encoding="utf-8", errors="replace") + "\n"
        self.assertNotIn("待归类", blob)
        self.assertNotIn("去异常处理归类", blob)


if __name__ == "__main__":
    unittest.main()
