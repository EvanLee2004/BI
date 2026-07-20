#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书64·P 反向适配：明文密码为真相源 / 管理员可见 / 0600 / reset 踢会话。

原任务书63·B 哈希/迁移/不下发明文 断言已按产品拍板改回明文口径。
跑：.venv/bin/python tests/run_test.py tests/test_task63_stage63_batch_b.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import loaders  # noqa: E402
import secure_io  # noqa: E402
import server  # noqa: E402


class TestPasswordPlainCore(unittest.TestCase):
    def test_compare_digest_plaintext(self):
        self.assertTrue(accounts.verify_password("中文口令甲", "中文口令甲"))
        self.assertFalse(accounts.verify_password("中文口令甲", "中文口令乙"))

    def test_random_password_charset(self):
        p = accounts.generate_random_password(10)
        self.assertEqual(len(p), 10)
        self.assertTrue(all(c.isalnum() for c in p))


class TestPlaintextApiAndPerms(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        self._orig = server.recompute
        server.recompute = lambda cfg, root=None: None
        server._state["user_html"] = "<html>U</html>"
        server._state["admin_html"] = "<html>A</html>"
        p = accounts.config_path(self.cfg, self.tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "accounts": [
                        {
                            "账号": accounts.MASTER_ACCOUNT,
                            "显示名": "管",
                            "权限": "管理员",
                            "密码": accounts.DEFAULT_ADMIN_PW,
                        },
                        {"账号": "v1", "显示名": "看", "权限": "整体", "密码": "plain777"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.client = TestClient(self.app, follow_redirects=False)
        r = self.client.post(
            "/admin/login",
            data={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}

    def tearDown(self):
        server.recompute = self._orig

    def test_seed_chmod_600_and_plaintext_on_disk(self):
        """seed / 保存后盘上明文 + 权限 0o600（非 Windows）。"""
        # 触发一次保存以走 write_private_text
        rows = accounts.load_accounts(self.cfg, self.tmp)
        accounts.save_accounts(self.cfg, self.tmp, rows)
        path = accounts.config_path(self.cfg, self.tmp)
        raw = json.loads(path.read_text(encoding="utf-8"))
        row = next(x for x in raw["accounts"] if x["账号"] == "v1")
        self.assertEqual(row.get("密码"), "plain777")
        self.assertNotIn("密码哈希", row)
        mode = secure_io.is_private_mode(path)
        if mode is not None:
            self.assertTrue(mode, f"期望 0o600，path={path}")

    def test_accounts_api_returns_plaintext_password(self):
        """任务书64·P：管理员 /api/accounts 下发明文密码。"""
        r = self.client.get("/api/accounts", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json()["accounts"]:
            self.assertIn("密码", row)
            self.assertNotIn("密码哈希", row)
            self.assertIn("初始密码", row)
        v1 = next(x for x in r.json()["accounts"] if x["账号"] == "v1")
        self.assertEqual(v1["密码"], "plain777")

    def test_full_chain_seed_login_see_change_kick(self):
        """全新 seed→登录→管理端见明文→改密→旧会话失效。"""
        from fastapi.testclient import TestClient

        tmp2 = Path(tempfile.mkdtemp())
        # 无账号文件 → seed
        app2 = server.create_app(self.cfg, root=tmp2)
        c = TestClient(app2, follow_redirects=False)
        r = c.post(
            "/admin/login",
            data={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertIn(r.status_code, (200, 303), r.text)
        hdr = {"Cookie": f"{server.COOKIE}={r.cookies.get(server.COOKIE)}"}
        rows = c.get("/api/accounts", headers=hdr).json()["accounts"]
        overall = next(x for x in rows if x["账号"] == "overall")
        self.assertEqual(overall["密码"], accounts.DEFAULT_VIEW_PW)
        # 看端登录
        viewer = TestClient(app2, follow_redirects=False)
        r0 = viewer.post("/api/v1/login", json={"account": "overall", "password": accounts.DEFAULT_VIEW_PW})
        self.assertEqual(r0.status_code, 200, r0.text)
        self.assertEqual(viewer.get("/api/v1/session").status_code, 200)
        # 管理员改密
        overall["密码"] = "newplain99"
        r_save = c.post("/api/accounts", headers=hdr, json={"accounts": rows})
        self.assertEqual(r_save.status_code, 200, r_save.text)
        # 旧会话踢
        self.assertEqual(viewer.get("/api/v1/session").status_code, 401)
        r_ok = c.post("/api/v1/login", json={"account": "overall", "password": "newplain99"})
        self.assertEqual(r_ok.status_code, 200)
        # 权限位
        path = accounts.config_path(self.cfg, tmp2)
        mode = secure_io.is_private_mode(path)
        if mode is not None:
            self.assertTrue(mode)

    def test_reset_passwd_once_and_kicks_old(self):
        from fastapi.testclient import TestClient

        viewer = TestClient(self.app, follow_redirects=False)
        r0 = viewer.post("/api/v1/login", json={"account": "v1", "password": "plain777"})
        self.assertEqual(r0.status_code, 200, r0.text)
        self.assertEqual(viewer.get("/api/v1/session").status_code, 200)
        old_vcookie = viewer.cookies.get(server.VCOOKIE)
        self.assertTrue(old_vcookie, "应拿到看端 cookie")
        r = self.client.post(
            "/api/accounts/v1/reset_passwd",
            headers=self.hdr,
            json={"new": "reset9999"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("password"), "reset9999")
        r_sess = viewer.get("/api/v1/session")
        self.assertEqual(r_sess.status_code, 401, r_sess.text)
        r_sess2 = TestClient(self.app, follow_redirects=False).get(
            "/api/v1/session",
            headers={"Cookie": f"{server.VCOOKIE}={old_vcookie}"},
        )
        self.assertEqual(r_sess2.status_code, 401, r_sess2.text)
        r_bad = self.client.post("/api/v1/login", json={"account": "v1", "password": "plain777"})
        self.assertEqual(r_bad.status_code, 401)
        r_ok = self.client.post("/api/v1/login", json={"account": "v1", "password": "reset9999"})
        self.assertEqual(r_ok.status_code, 200)
        # 管理端列表可见新明文
        rows = self.client.get("/api/accounts", headers=self.hdr).json()["accounts"]
        self.assertEqual(next(x for x in rows if x["账号"] == "v1")["密码"], "reset9999")
        r2 = self.client.post("/api/accounts/v1/reset_passwd", headers=self.hdr, json={})
        self.assertEqual(r2.status_code, 200)
        plain = r2.json().get("password") or ""
        self.assertEqual(len(plain), 10)
        self.assertIsNotNone(accounts.authenticate(self.cfg, self.tmp, "v1", plain))


if __name__ == "__main__":
    unittest.main()
