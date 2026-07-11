#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v7.9 看板账号制测试。跑：.venv/bin/python tests/test_auth.py

守卫点（明昊 2026-07-11 拍板：看的人一个入口 `/` 账号+密码分流；密码由管理员集中管理，看的人不能自己改）：
- `/` 未登录=登录页（账号+密码）；账号「整体」看整体页（带 BU 入口条）；账号=BU 名直接看本 BU 页
- 账号不存在与密码错同一文案（不提示存在性）；中文密码不 500；cookie 防篡改
- BU 会话只看本 BU：`/` 出本 BU 页、/bu/<他BU> 不出内容、全公司口径出口（/api/daily、/export.png）401
- 整体/管理员会话可看任意 /bu/<名>；BU 不存在 404
- 密码集中管理：/api/viewer_passwd（设整体密码）、BU 配置行内「新密码」重置、/api/admin/passwd 验旧设新；
  三处独立、持久化；保存 BU 配置不带新密码=沿用；/api/bu_config 不下发密码 hash
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bu, loaders, server  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestViewerAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [
            {"name": "BU甲", "销售": ["销售A"]},
            {"name": "BU乙", "销售": ["销售B"]},
        ])
        server._state["user_html"] = '<html><div class="wrap">USER-MAIN</div></html>'
        server._state["bu_pages"] = {"BU甲": {"name": "BU甲", "html": "<html>PAGE-A</html>"},
                                     "BU乙": {"name": "BU乙", "html": "<html>PAGE-B</html>"}}
        self.app = server.create_app(self.cfg, root=self.tmp)
        self.raw = self._client()

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def _login(self, account, pw):
        c = self._client()
        r = c.post("/login", data={"account": account, "password": pw})
        return c, r

    def _admin(self):
        c = self._client()
        r = c.post("/admin/login", data={"identity": "明昊", "password": server.DEFAULT_PW})
        assert r.status_code == 303
        return c

    # ---- 登录分流 ----
    def test_login_page_and_main_flow(self):
        r = self.raw.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("看板登录", r.text)
        self.assertIn("账号", r.text)
        self.assertNotIn("USER-MAIN", r.text)
        _, bad = self._login("整体", "wrong")
        self.assertEqual(bad.status_code, 401)
        _, zh = self._login("整体", "错的中文密码")   # compare_digest 非 ASCII——曾 500，锁死
        self.assertEqual(zh.status_code, 401)
        _, ghost = self._login("不存在的账号", "8888")  # 账号不存在同一文案
        self.assertEqual(ghost.status_code, 401)
        self.assertIn("账号或密码不正确", ghost.text)
        c, ok = self._login("整体", server.DEFAULT_VIEW_PW)
        self.assertEqual(ok.status_code, 303)
        home = c.get("/").text
        self.assertIn("USER-MAIN", home)
        self.assertIn("/bu/", home)          # 整体页带 BU 入口条
        self.assertIn("BU甲", home)

    def test_bu_account_sees_own_page_at_root(self):
        c, ok = self._login("BU甲", bu.DEFAULT_PW)
        self.assertEqual(ok.status_code, 303)
        self.assertIn("PAGE-A", c.get("/").text)                       # 首页即本 BU 页
        self.assertIn("PAGE-A", c.get(f"/bu/{quote('BU甲')}").text)     # 直连也行
        self.assertNotIn("PAGE-B", c.get(f"/bu/{quote('BU乙')}").text)  # 他 BU 出登录页
        self.assertNotIn("USER-MAIN", c.get(f"/bu/{quote('BU乙')}").text)

    def test_main_and_admin_can_view_any_bu(self):
        c, _ = self._login("整体", server.DEFAULT_VIEW_PW)
        self.assertIn("PAGE-A", c.get(f"/bu/{quote('BU甲')}").text)
        a = self._admin()
        self.assertIn("PAGE-B", a.get(f"/bu/{quote('BU乙')}").text)

    def test_unknown_bu_404(self):
        self.assertEqual(self.raw.get(f"/bu/{quote('不存在BU')}").status_code, 404)

    def test_tampered_cookie_rejected(self):
        c, _ = self._login("整体", server.DEFAULT_VIEW_PW)
        cookie = c.cookies.get(server.VCOOKIE)
        r = self.raw.get("/", headers={"Cookie": f"{server.VCOOKIE}={cookie[:-4]}beef"})
        self.assertIn("看板登录", r.text)

    # ---- 全公司口径出口 ----
    def test_company_endpoints_gated(self):
        q = {"start": "2026-03-01", "end": "2026-03-31"}
        self.assertEqual(self.raw.get("/api/daily", params=q).status_code, 401)
        self.assertEqual(self.raw.get("/export.png").status_code, 401)
        cbu, _ = self._login("BU甲", bu.DEFAULT_PW)
        self.assertEqual(cbu.get("/api/daily", params=q).status_code, 401)   # BU 会话不给全公司口径
        cmain, _ = self._login("整体", server.DEFAULT_VIEW_PW)
        self.assertEqual(cmain.get("/api/daily", params=q).status_code, 200)

    # ---- 密码集中管理 ----
    def test_viewer_passwd_admin_only_and_persists(self):
        self.assertEqual(self.raw.post("/api/viewer_passwd", json={"new": "npw1"}).status_code, 401)
        a = self._admin()
        self.assertEqual(a.post("/api/viewer_passwd", json={"new": "123"}).status_code, 400)  # <4位
        self.assertEqual(a.post("/api/viewer_passwd", json={"new": "npw123"}).status_code, 200)
        _, old = self._login("整体", server.DEFAULT_VIEW_PW)
        self.assertEqual(old.status_code, 401)
        _, new = self._login("整体", "npw123")
        self.assertEqual(new.status_code, 303)
        sec = json.loads((self.tmp / "数据" / "管理员密钥.json").read_text(encoding="utf-8"))
        self.assertIn("viewer_pw_hash", sec)

    def test_bu_passwd_reset_via_save_and_kept_when_blank(self):
        # 行内带「新密码」= 重置该 BU；另一行不带 = 沿用
        bu.save_bu_config(self.cfg, self.tmp, [
            {"name": "BU甲", "销售": ["销售A"], "新密码": "bunew1"},
            {"name": "BU乙", "销售": ["销售B"]}])
        _, old = self._login("BU甲", bu.DEFAULT_PW)
        self.assertEqual(old.status_code, 401)
        _, new = self._login("BU甲", "bunew1")
        self.assertEqual(new.status_code, 303)
        _, b = self._login("BU乙", bu.DEFAULT_PW)   # 未动的 BU 仍初始密码
        self.assertEqual(b.status_code, 303)
        # 再保存一次不带新密码 → BU甲 密码保持 bunew1
        bu.save_bu_config(self.cfg, self.tmp, [
            {"name": "BU甲", "销售": ["销售A", "销售C"]},
            {"name": "BU乙", "销售": ["销售B"]}])
        entry = bu.by_name(bu.load_bu_config(self.cfg, self.tmp))["BU甲"]
        self.assertTrue(bu.verify_pw(entry["密码hash"], "bunew1"))

    def test_bu_config_api_never_leaks_pw_hash(self):
        a = self._admin()
        for b in a.get("/api/bu_config").json()["bus"]:
            self.assertNotIn("密码hash", b)

    def test_main_account_name_reserved(self):
        """BU 名不能叫「整体」（与整体账号撞名会造成分流混乱）——配置层直接拒。"""
        saved = bu.save_bu_config(self.cfg, self.tmp, [
            {"name": "整体", "销售": ["销售A"]}, {"name": "BU丙", "销售": ["销售C"]}])
        self.assertEqual([b["name"] for b in saved["bus"]], ["BU丙"])

    # ---- 管理员改密码 ----
    def test_admin_passwd_change(self):
        self.assertEqual(self.raw.post("/api/admin/passwd",
                                       json={"old": "x", "new": "yyyy"}).status_code, 401)
        a = self._admin()
        self.assertEqual(a.post("/api/admin/passwd",
                                json={"old": "wrong", "new": "admnew1"}).status_code, 400)
        self.assertEqual(a.post("/api/admin/passwd",
                                json={"old": server.DEFAULT_PW, "new": "admnew1"}).status_code, 200)
        c = self._client()
        self.assertEqual(c.post("/admin/login",
                                data={"identity": "明昊", "password": server.DEFAULT_PW}).status_code, 401)
        self.assertEqual(c.post("/admin/login",
                                data={"identity": "明昊", "password": "admnew1"}).status_code, 303)


if __name__ == "__main__":
    unittest.main(verbosity=1)
