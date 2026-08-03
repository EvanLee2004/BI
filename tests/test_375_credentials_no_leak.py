# -*- coding: utf-8 -*-
"""3.7.5 G1 凭据边界 + 3.7.8 看板密码回显（MADR-0020）。

红→绿契约：
- GET settings 无智云密码/可逆等价值，仅 zhiyun_password_set 等状态
- GET/POST accounts：**允许**看板账号明文密码（管理员+manage）；**禁止**智云密码/token
- reset 响应仍不回显新密（列表 GET 可见）
- POST settings 密码空 → 智云存储值不变；显式新密码后新密可登、旧密失效
- 未登录/无权限 401/403
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _walk_secrets(obj, secrets: set[str], path: str = "$") -> list[str]:
    """递归找秘密值或禁止字段名。返回违规路径列表。"""
    bad: list[str] = []
    forbid_keys = {
        "password",
        "zhiyun_password",
        "密码",
        "passwd",
        "secret",
        "token",
    }
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            p = f"{path}.{k}"
            if kl in forbid_keys or k in forbid_keys or k == "密码":
                # 状态布尔允许：*_set / password_set / zhiyun_password_set
                if kl.endswith("_set") or kl in ("password_hashed", "must_change_password"):
                    pass
                else:
                    # 字段本身禁止出现（即使值为空）— 除 password_hashed 等状态
                    if kl not in ("password_hashed",) and not kl.endswith("_set"):
                        bad.append(f"forbidden_key:{p}={v!r}")
            if isinstance(v, str) and v and v in secrets:
                bad.append(f"secret_value:{p}")
            bad.extend(_walk_secrets(v, secrets, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(_walk_secrets(v, secrets, f"{path}[{i}]"))
    elif isinstance(obj, str) and obj and obj in secrets:
        bad.append(f"secret_value:{path}")
    return bad


class TestCredentialsNoLeak375(unittest.TestCase):
    """管理员 settings/accounts/reset 响应不得泄密。"""

    SECRET_ZY = "zy-secret-OLD-9x7"
    SECRET_ACCT = "acct-secret-OLD-3k2"
    SECRET_NEW = "acct-secret-NEW-8m1"
    SECRET_ZY_NEW = "zy-secret-NEW-4p5"

    def setUp(self):
        import server
        from fastapi.testclient import TestClient

        self.tmp = Path(tempfile.mkdtemp(prefix="t375_cred_"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        # 最小数据目录
        data = self.tmp / "数据"
        data.mkdir(parents=True)
        (self.tmp / "config.json").write_text(
            (ROOT / "config.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        # 账号：管理员 + overall
        import accounts

        accts = [
            {
                "账号": accounts.MASTER_ACCOUNT,
                "显示名": "管理员",
                "权限": "管理员",
                "密码": accounts.DEFAULT_ADMIN_PW,
                "密码版本": 1,
            },
            {
                "账号": "overall",
                "显示名": "整体",
                "权限": "整体",
                "密码": self.SECRET_ACCT,
                "密码版本": 1,
            },
        ]
        (data / "看板账号.json").write_text(
            json.dumps({"accounts": accts}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 智云凭据
        (data / "智云配置.json").write_text(
            json.dumps(
                {
                    "username": "zy.user.old",
                    "password": self.SECRET_ZY,
                    "md_pss_id": "TOK",
                    "account_id": "ACC",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (data / "本地配置.json").write_text("{}", encoding="utf-8")

        self.cfg = {
            "data_dir": "数据",
            "db_path": "看板.db",
            "profiles": {"dev": {}},
        }
        # loaders 用 root 相对
        self.app = server.create_app(cfg=self.cfg, root=self.tmp)
        self.client = TestClient(self.app, follow_redirects=False)
        # 管理员登录
        r = self.client.post(
            "/api/v1/login",
            json={"account": accounts.MASTER_ACCOUNT, "password": accounts.DEFAULT_ADMIN_PW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        sid = self.client.cookies.get(server.SID_COOKIE) or self.client.cookies.get(
            getattr(server, "COOKIE", "kanban_sid")
        )
        self.assertTrue(sid)
        self.hdr = {"Cookie": f"{server.SID_COOKIE}={sid}"}
        self.secrets = {
            self.SECRET_ZY,
            self.SECRET_ACCT,
            self.SECRET_NEW,
            self.SECRET_ZY_NEW,
            accounts.DEFAULT_ADMIN_PW,
        }

    def test_get_settings_no_zhiyun_password(self):
        r = self.client.get("/api/v1/admin/settings", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        bad = _walk_secrets(body, self.secrets)
        self.assertEqual(bad, [], f"settings GET 泄密: {bad}; body_keys={list(body)}")
        self.assertNotIn("zhiyun_password", body)
        self.assertIn("zhiyun_password_set", body)
        self.assertTrue(body["zhiyun_password_set"] is True)
        # 用户名可下发（非秘密状态）
        self.assertEqual(body.get("zhiyun_username"), "zy.user.old")

    def test_get_accounts_board_password_ok_zhiyun_not(self):
        """3.7.8：看板明文可见；智云秘密不得出现在 accounts 响应。"""
        r = self.client.get("/api/v1/admin/accounts", headers=self.hdr)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # 允许看板 密码；仍禁智云/token 等
        bad = [
            x
            for x in _walk_secrets(body, {self.SECRET_ZY, self.SECRET_ZY_NEW})
            if "zhiyun" in x or "token" in x.lower() or "secret_value" in x
        ]
        self.assertEqual(bad, [], f"accounts GET 智云/token 泄密: {bad}")
        rows = body.get("accounts") or []
        overall = next(x for x in rows if x.get("账号") == "overall")
        self.assertEqual(overall.get("密码"), self.SECRET_ACCT)
        self.assertNotIn("password", overall)
        self.assertNotIn("zhiyun_password", body)

    def test_post_accounts_roundtrip_board_password(self):
        r0 = self.client.get("/api/v1/admin/accounts", headers=self.hdr)
        rows = r0.json()["accounts"]
        # 原样回写（含明文密码字段）
        r = self.client.post(
            "/api/v1/admin/accounts", headers=self.hdr, json={"accounts": rows}
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        overall = next(x for x in body["accounts"] if x.get("账号") == "overall")
        self.assertEqual(overall.get("密码"), self.SECRET_ACCT)
        # 存储密码仍为旧值
        import accounts

        acc = accounts.find_account(self.cfg, self.tmp, "overall")
        self.assertIsNotNone(acc)
        self.assertEqual(acc["密码"], self.SECRET_ACCT)

    def test_empty_password_keeps_stored_on_accounts_save(self):
        r0 = self.client.get("/api/v1/admin/accounts", headers=self.hdr)
        rows = list(r0.json()["accounts"])
        for row in rows:
            if row.get("账号") == "overall":
                row["密码"] = ""  # 留空不改
                row["显示名"] = "整体改名"
        r = self.client.post(
            "/api/v1/admin/accounts", headers=self.hdr, json={"accounts": rows}
        )
        self.assertEqual(r.status_code, 200, r.text)
        import accounts

        acc = accounts.find_account(self.cfg, self.tmp, "overall")
        self.assertEqual(acc["密码"], self.SECRET_ACCT)
        self.assertEqual(acc["显示名"], "整体改名")

    def test_explicit_new_password_login_and_old_fails(self):
        r = self.client.post(
            "/api/v1/admin/accounts/overall/reset_passwd",
            headers=self.hdr,
            json={"new": self.SECRET_NEW},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        bad = _walk_secrets(body, self.secrets)
        self.assertEqual(bad, [], f"reset 响应泄密: {bad}; {body}")
        self.assertNotIn("password", body)
        self.assertNotIn("密码", body)
        # 新密可登
        r_ok = self.client.post(
            "/api/v1/login", json={"account": "overall", "password": self.SECRET_NEW}
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)
        # 旧密失效
        r_bad = self.client.post(
            "/api/v1/login", json={"account": "overall", "password": self.SECRET_ACCT}
        )
        self.assertEqual(r_bad.status_code, 401)

    def test_reset_requires_explicit_password(self):
        """不得随机生成后由 API 回显。"""
        r = self.client.post(
            "/api/v1/admin/accounts/overall/reset_passwd",
            headers=self.hdr,
            json={},
        )
        self.assertIn(r.status_code, (400, 422), r.text)
        if r.status_code == 200:
            self.fail("空 new 不得成功且回显密码")

    def test_settings_empty_password_keeps_zhiyun(self):
        import json as _json
        from loaders import data_dir

        zp = data_dir(self.cfg, self.tmp) / "智云配置.json"
        before = _json.loads(zp.read_text(encoding="utf-8"))
        r = self.client.post(
            "/api/v1/admin/settings",
            headers=self.hdr,
            json={"zhiyun_username": "zy.user.old", "zhiyun_password": ""},
        )
        self.assertEqual(r.status_code, 200, r.text)
        after = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertEqual(after.get("password"), self.SECRET_ZY)
        self.assertEqual(after.get("username"), before.get("username"))

    def test_settings_explicit_new_zhiyun_password(self):
        import json as _json
        from loaders import data_dir

        r = self.client.post(
            "/api/v1/admin/settings",
            headers=self.hdr,
            json={
                "zhiyun_username": "zy.user.new",
                "zhiyun_password": self.SECRET_ZY_NEW,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        zp = data_dir(self.cfg, self.tmp) / "智云配置.json"
        d = _json.loads(zp.read_text(encoding="utf-8"))
        self.assertEqual(d.get("password"), self.SECRET_ZY_NEW)
        self.assertEqual(d.get("username"), "zy.user.new")
        # GET 仍不回显
        g = self.client.get("/api/v1/admin/settings", headers=self.hdr).json()
        bad = _walk_secrets(g, self.secrets)
        self.assertEqual(bad, [], f"改密后 GET 仍泄密: {bad}")
        self.assertTrue(g.get("zhiyun_password_set") is True)

    def test_unauthorized_401(self):
        bare = self.client.__class__(self.app, follow_redirects=False)
        for path in (
            "/api/v1/admin/settings",
            "/api/v1/admin/accounts",
        ):
            r = bare.get(path)
            self.assertIn(r.status_code, (401, 403), f"{path} → {r.status_code}")
        r2 = bare.post("/api/v1/admin/accounts/overall/reset_passwd", json={"new": "x"})
        self.assertIn(r2.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
