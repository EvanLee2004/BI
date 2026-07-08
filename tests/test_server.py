#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刀3 测试：FastAPI 双端只读 + 会话鉴权。跑：.venv/bin/python tests/test_server.py
需 fastapi/httpx（venv 里已装）。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import loaders, server  # noqa: E402


class TestServerAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.tmp = tempfile.mkdtemp()
        cls.cfg = loaders.load_config()
        # 用假页面，避免测试里跑整条重管道；用临时 root 让密钥/库落到临时目录
        server._state["user_html"] = "<html><body>USER-DASH 基本情况 kpi-grid</body></html>"
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        cls.app = server.create_app(cls.cfg, root=Path(cls.tmp))
        cls.client = TestClient(cls.app, follow_redirects=False)

    def test_user_page_public_no_detail(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("USER-DASH", r.text)
        self.assertNotIn("管理员控制台", r.text)       # 用户页不含管理员控制台
        self.assertNotIn("/api/detail", r.text)        # 用户页不引用明细接口

    def test_admin_requires_login(self):
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("管理员端登录", r.text)           # 无会话 → 密码页

    def test_detail_401_without_session(self):
        r = self.client.get("/api/detail?table=收入明细")
        self.assertEqual(r.status_code, 401)            # ★验收：未登录 curl /api/detail 得 401

    def test_login_wrong_password(self):
        r = self.client.post("/admin/login", data={"identity": "明昊", "password": "错的"})
        self.assertEqual(r.status_code, 401)

    def test_login_then_detail_ok(self):
        r = self.client.post("/admin/login",
                             data={"identity": "明昊", "password": server.DEFAULT_PW})
        self.assertEqual(r.status_code, 303)            # 登录成功重定向
        cookie = r.cookies.get(server.COOKIE)
        self.assertTrue(cookie)
        hdr = {"Cookie": f"{server.COOKIE}={cookie}"}
        # 带会话 → /api/detail 200；/admin 出管理员页
        r2 = self.client.get("/api/detail?table=收入明细", headers=hdr)
        self.assertEqual(r2.status_code, 200)
        self.assertIn("columns", r2.json())
        r3 = self.client.get("/admin", headers=hdr)
        self.assertIn("管理员控制台", r3.text)

    def test_tampered_cookie_rejected(self):
        # 伪造 token（合法 base64 载荷 + 错签名）——ASCII，模拟改签名攻击
        import base64
        payload = base64.urlsafe_b64encode(b"\xe6\x98\x8e\xe6\x98\x8a|9999999999").decode()
        r = self.client.get("/api/detail?table=收入明细",
                            headers={"Cookie": f"{server.COOKIE}={payload}.deadbeefbadsig"})
        self.assertEqual(r.status_code, 401)

    def test_health_public_no_amounts(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn("result", r.json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
