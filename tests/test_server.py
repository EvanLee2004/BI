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

    def test_user_page_requires_viewer_login(self):
        """v7.8 全看板密码制：整体页未登录 → 登录页；密码(初始 8888)登录后才见内容。"""
        from fastapi.testclient import TestClient
        anon = TestClient(self.app, follow_redirects=False)   # 独立匿名客户端（不吃别的测试留下的 cookie）
        r = anon.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("看板登录", r.text)
        self.assertNotIn("USER-DASH", r.text)
        r = anon.post("/login", data={"account": "整体", "password": "错的"})
        self.assertEqual(r.status_code, 401)
        r = anon.post("/login", data={"account": "整体", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r.status_code, 303)
        vcookie = r.cookies.get(server.VCOOKIE)
        r = anon.get("/", headers={"Cookie": f"{server.VCOOKIE}={vcookie}"})
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
        j = r.json()
        self.assertIn("result", j)
        self.assertIn("run_reasons", j)      # C2：新增「黄的原因」字段
        self.assertIsInstance(j["run_reasons"], list)


class TestRunReasons(unittest.TestCase):
    """C2：_run_reasons 从运行日志(体检JSON)推导"为啥黄/红"，与 ingest._log_run 判定口径一致。"""
    def test_empty(self):
        self.assertEqual(server._run_reasons({}), [])
        self.assertEqual(server._run_reasons(None), [])

    def test_fetch_local_fallback(self):
        rs = server._run_reasons({"fetch": {"status": "local_fallback"}})
        self.assertTrue(any("本地副本" in r for r in rs))

    def test_no_source_red(self):
        rs = server._run_reasons({"fetch": {"status": "no_source"}})
        self.assertTrue(any("无可用数据源" in r for r in rs))

    def test_expired_adjustments(self):
        rs = server._run_reasons({"fetch": {"status": "fetched"},
                                  "adjust": {"expired": 2}})
        joined = " ".join(rs)
        self.assertIn("2 条调整", joined)      # 过期疑似

    def test_all_clean_no_reasons(self):
        rs = server._run_reasons({"fetch": {"status": "fetched"},
                                  "adjust": {"expired": 0}})
        self.assertEqual(rs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
