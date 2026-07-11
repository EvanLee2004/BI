#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.8 全看板账号密码制测试。跑：.venv/bin/python tests/test_auth.py

守卫点（明昊 2026-07-11 定：所有看板都要密码，初始简单密码，登录后自己改）：
- 整体页 `/`：未登录=登录页；初始密码 8888 登录后见内容；错密码 401
- BU 页：链接+密码双要素；BU 会话只开本 BU；整体页会话/管理员会话可看任意 BU
- 全公司口径出口（/api/daily、/export.png）：BU 会话与未登录一律 401（防绕过页面隔离）
- 改密码：验旧设新、立即生效并持久化（整体页/BU/管理员三处各自独立）
- 管理端保存 BU 配置不丢已改的 BU 密码；/api/bu_config 不下发密码 hash
- 会话 cookie 防篡改
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bu, loaders, server  # noqa: E402

TOK_A = "a" * 32
TOK_B = "b" * 32


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestViewerAuth(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [
            {"name": "BU甲", "销售": ["销售A"], "token": TOK_A},
            {"name": "BU乙", "销售": ["销售B"], "token": TOK_B},
        ])
        server._state["user_html"] = "<html>USER-MAIN</html>"
        server._state["bu_pages"] = {TOK_A: {"name": "BU甲", "html": "<html>PAGE-A</html>"},
                                     TOK_B: {"name": "BU乙", "html": "<html>PAGE-B</html>"}}
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.raw = self._client()

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def _login_main(self, pw=server.DEFAULT_VIEW_PW):
        c = self._client()
        r = c.post("/login", data={"password": pw})
        return c, r

    def _login_bu(self, token, pw=bu.DEFAULT_PW):
        c = self._client()
        r = c.post(f"/bu/{token}/login", data={"password": pw})
        return c, r

    def _admin(self):
        c = self._client()
        r = c.post("/admin/login", data={"identity": "明昊", "password": server.DEFAULT_PW})
        assert r.status_code == 303
        return c

    # ---- 整体页 ----
    def test_main_login_flow(self):
        r = self.raw.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("看板登录", r.text)
        self.assertNotIn("USER-MAIN", r.text)
        _, bad = self._login_main("wrong")
        self.assertEqual(bad.status_code, 401)
        _, zh = self._login_main("错的中文密码")   # compare_digest 不吃非 ASCII str——曾 500，锁死
        self.assertEqual(zh.status_code, 401)
        c, ok = self._login_main()
        self.assertEqual(ok.status_code, 303)
        self.assertIn("USER-MAIN", c.get("/").text)

    def test_tampered_cookie_rejected(self):
        c, _ = self._login_main()
        cookie = c.cookies.get(server.VCOOKIE)
        r = self.raw.get("/", headers={"Cookie": f"{server.VCOOKIE}={cookie[:-4]}beef"})
        self.assertIn("看板登录", r.text)

    # ---- BU 页 ----
    def test_bu_login_flow_and_isolation(self):
        r = self.raw.get(f"/bu/{TOK_A}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("BU 看板登录", r.text)
        self.assertNotIn("PAGE-A", r.text)
        _, bad = self._login_bu(TOK_A, "wrong")
        self.assertEqual(bad.status_code, 401)
        c, ok = self._login_bu(TOK_A)
        self.assertEqual(ok.status_code, 303)
        self.assertIn("PAGE-A", c.get(f"/bu/{TOK_A}").text)
        # BU甲 会话看不了 BU乙（出登录框不出内容）、也看不了整体页
        self.assertNotIn("PAGE-B", c.get(f"/bu/{TOK_B}").text)
        self.assertNotIn("USER-MAIN", c.get("/").text)

    def test_main_and_admin_can_view_any_bu(self):
        c, _ = self._login_main()
        self.assertIn("PAGE-A", c.get(f"/bu/{TOK_A}").text)
        a = self._admin()
        self.assertIn("PAGE-B", a.get(f"/bu/{TOK_B}").text)

    def test_wrong_token_still_404(self):
        self.assertEqual(self.raw.get("/bu/" + "c" * 32).status_code, 404)
        self.assertEqual(self.raw.post("/bu/" + "c" * 32 + "/login",
                                       data={"password": bu.DEFAULT_PW}).status_code, 404)

    # ---- 全公司口径出口 ----
    def test_company_endpoints_gated(self):
        q = {"start": "2026-03-01", "end": "2026-03-31"}
        self.assertEqual(self.raw.get("/api/daily", params=q).status_code, 401)
        self.assertEqual(self.raw.get("/export.png").status_code, 401)
        cbu, _ = self._login_bu(TOK_A)
        self.assertEqual(cbu.get("/api/daily", params=q).status_code, 401)   # BU 会话不给全公司口径
        cmain, _ = self._login_main()
        self.assertEqual(cmain.get("/api/daily", params=q).status_code, 200)

    # ---- 改密码 ----
    def test_main_passwd_change_persists(self):
        c, _ = self._login_main()
        r = c.post("/api/passwd", json={"old": "wrong", "new": "newpw1"})
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "123"})
        self.assertEqual(r.status_code, 400)   # 少于4位
        r = c.post("/api/passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "newpw1"})
        self.assertEqual(r.status_code, 200)
        _, old = self._login_main(server.DEFAULT_VIEW_PW)
        self.assertEqual(old.status_code, 401)   # 旧密码作废
        _, new = self._login_main("newpw1")
        self.assertEqual(new.status_code, 303)   # 新密码生效
        sec = json.loads((self.tmp / "数据" / "管理员密钥.json").read_text(encoding="utf-8"))
        self.assertIn("viewer_pw_hash", sec)     # 已持久化

    def test_bu_passwd_change_and_save_keeps_it(self):
        c, _ = self._login_bu(TOK_A)
        r = c.post("/api/passwd", json={"old": bu.DEFAULT_PW, "new": "bunew1"})
        self.assertEqual(r.status_code, 200)
        _, old = self._login_bu(TOK_A, bu.DEFAULT_PW)
        self.assertEqual(old.status_code, 401)
        _, new = self._login_bu(TOK_A, "bunew1")
        self.assertEqual(new.status_code, 303)
        # BU乙不受影响（各自独立）
        _, b = self._login_bu(TOK_B, bu.DEFAULT_PW)
        self.assertEqual(b.status_code, 303)
        # 管理端保存配置（改名单）不丢 BU甲 已改的密码
        bu.save_bu_config(self.cfg, self.tmp, [
            {"name": "BU甲", "销售": ["销售A", "销售C"], "token": TOK_A},
            {"name": "BU乙", "销售": ["销售B"], "token": TOK_B}])
        entry = bu.token_map(bu.load_bu_config(self.cfg, self.tmp))[TOK_A]
        self.assertTrue(bu.verify_pw(entry["密码hash"], "bunew1"))

    def test_passwd_requires_session(self):
        r = self.raw.post("/api/passwd", json={"old": "x", "new": "yyyy"})
        self.assertEqual(r.status_code, 401)

    def test_bu_config_api_never_leaks_pw_hash(self):
        a = self._admin()
        d = a.get("/api/bu_config").json()
        for b in d["bus"]:
            self.assertNotIn("密码hash", b)

    # ---- 管理员改密码 ----
    def test_admin_passwd_change(self):
        self.assertEqual(self.raw.post("/api/admin/passwd",
                                       json={"old": "x", "new": "yyyy"}).status_code, 401)
        a = self._admin()
        r = a.post("/api/admin/passwd", json={"old": "wrong", "new": "admnew1"})
        self.assertEqual(r.status_code, 400)
        r = a.post("/api/admin/passwd", json={"old": server.DEFAULT_PW, "new": "admnew1"})
        self.assertEqual(r.status_code, 200)
        c = self._client()
        self.assertEqual(c.post("/admin/login",
                                data={"identity": "明昊", "password": server.DEFAULT_PW}).status_code, 401)
        self.assertEqual(c.post("/admin/login",
                                data={"identity": "明昊", "password": "admnew1"}).status_code, 303)


if __name__ == "__main__":
    unittest.main(verbosity=1)
