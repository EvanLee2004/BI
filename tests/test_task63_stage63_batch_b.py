#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书63 批次B：H-05 密码哈希 / 迁移 / reset_passwd / 接口无密码字段。

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
import server  # noqa: E402


class TestPasswordHashCore(unittest.TestCase):
    def test_hash_roundtrip_and_format(self):
        h = accounts.hash_password("中文口令甲")
        self.assertTrue(h.startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(accounts.verify_password_hash(h, "中文口令甲"))
        self.assertFalse(accounts.verify_password_hash(h, "中文口令乙"))

    def test_random_password_charset(self):
        p = accounts.generate_random_password(10)
        self.assertEqual(len(p), 10)
        self.assertTrue(all(c.isalnum() for c in p))


class TestMigrationAndApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        self._orig = server.recompute
        server.recompute = lambda cfg, root=None: None
        server._state["user_html"] = "<html>U</html>"
        server._state["admin_html"] = "<html>A</html>"
        # 先写明文文件模拟存量
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

    def test_migrate_backup_and_old_password_works(self):
        self.assertIsNotNone(accounts.authenticate(self.cfg, self.tmp, "v1", "plain777"))
        raw = json.loads(accounts.config_path(self.cfg, self.tmp).read_text(encoding="utf-8"))
        row = next(x for x in raw["accounts"] if x["账号"] == "v1")
        self.assertTrue(str(row.get("密码哈希") or "").startswith("pbkdf2_sha256$"))
        self.assertFalse(str(row.get("密码") or "").strip())
        self.assertTrue(list(self.tmp.joinpath("数据").glob("看板账号.json.bak-明文迁移-*")))

    def test_accounts_api_no_password_fields(self):
        r = self.client.get("/api/accounts", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        for row in r.json()["accounts"]:
            self.assertNotIn("密码", row)
            self.assertNotIn("密码哈希", row)
            self.assertIn("初始密码", row)

    def test_reset_passwd_once_and_kicks_old(self):
        # 旧密码登录拿看端 cookie
        r0 = self.client.post("/api/v1/login", json={"account": "v1", "password": "plain777"})
        self.assertEqual(r0.status_code, 200, r0.text)
        old_cookie = r0.cookies.get(server.VCOOKIE) or r0.cookies.get(server.COOKIE)
        # 重置
        r = self.client.post(
            "/api/accounts/v1/reset_passwd",
            headers=self.hdr,
            json={"new": "reset9999"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("password"), "reset9999")
        # 旧密码 401
        r_bad = self.client.post("/api/v1/login", json={"account": "v1", "password": "plain777"})
        self.assertEqual(r_bad.status_code, 401)
        # 新密码 200
        r_ok = self.client.post("/api/v1/login", json={"account": "v1", "password": "reset9999"})
        self.assertEqual(r_ok.status_code, 200)
        # 随机重置
        r2 = self.client.post("/api/accounts/v1/reset_passwd", headers=self.hdr, json={})
        self.assertEqual(r2.status_code, 200)
        plain = r2.json().get("password") or ""
        self.assertEqual(len(plain), 10)
        self.assertIsNotNone(accounts.authenticate(self.cfg, self.tmp, "v1", plain))


if __name__ == "__main__":
    unittest.main()
