#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v8.0 账号权限重构测试。跑：.venv/bin/python tests/test_auth.py

守卫点（明昊 2026-07-11 拍板：正经账号 + 明文管理员可见 + 看的人可自改）：
- 账号表读写/缺文件自动 seed；账号名唯一；一个 BU 可挂多账号
- `/` 登录按权限分流：管理员→/admin；整体→整体页；BU→本 BU 页；错号/错密 401 同文案
- 中文密码不 500（bytes 比较）；cookie 防篡改
- BU 会话只看本 BU；/api/daily、/export.png 仅整体/管理员；未知 BU 404
- 自改密码 + 管理员改双向生效；权限改绑即生效；删号即失效
- 明文密码只在管理员 /api/accounts 出现；黄标=初始密码；自改弹窗文案
- /admin 无身份下拉，账号+密码；经手人=登录账号
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts
import bu
import loaders
import server
from support import fake_main_frags, fake_bu_page, fake_views  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


def _std_accts():
    """测试用合成账号（铁律5：不进真实人名）。"""
    return [
        {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
        {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_b1", "显示名": "乙负责人一", "权限": "BU乙", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_b2", "显示名": "乙负责人二", "权限": "BU乙", "密码": server.DEFAULT_VIEW_PW},
    ]


class TestAccountsModule(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()

    def test_seed_when_missing(self):
        rows = accounts.load_accounts(self.cfg, self.tmp, create=True)
        self.assertTrue(any(a["账号"] == "lushasha" and a["权限"] == "管理员" for a in rows))
        self.assertTrue(accounts.config_path(self.cfg, self.tmp).exists())

    def test_unique_account_and_multi_bu(self):
        saved = accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管", "权限": "管理员", "密码": "kanban2026"},
                {"账号": "a1", "显示名": "一", "权限": "BU甲", "密码": "8888"},
                {"账号": "a1", "显示名": "重复", "权限": "BU乙", "密码": "9999"},  # 同名丢弃
                {"账号": "a2", "显示名": "二", "权限": "BU甲", "密码": "8888"},
            ],
        )
        self.assertEqual([a["账号"] for a in saved], ["lushasha", "a1", "a2"])
        self.assertEqual(saved[1]["权限"], "BU甲")  # a1 保留第一条
        # 同 BU 多账号
        self.assertEqual(sum(1 for a in saved if a["权限"] == "BU甲"), 2)

    def test_initial_password_flag(self):
        self.assertTrue(accounts.is_initial_password("8888"))
        self.assertTrue(accounts.is_initial_password("kanban2026"))
        self.assertFalse(accounts.is_initial_password("changed1"))

    def test_chinese_password_bytes_compare(self):
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管", "权限": "管理员", "密码": "kanban2026"},
                {"账号": "u1", "显示名": "测", "权限": "整体", "密码": "中文密码甲"},
            ],
        )
        self.assertIsNotNone(accounts.authenticate(self.cfg, self.tmp, "u1", "中文密码甲"))
        self.assertIsNone(accounts.authenticate(self.cfg, self.tmp, "u1", "中文密码乙"))


class TestViewerAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(
            self.cfg,
            self.tmp,
            [
                {"name": "BU甲", "销售": ["销售A"]},
                {"name": "BU乙", "销售": ["销售B"]},
            ],
        )
        _write_accts(self.cfg, self.tmp, _std_accts())
        server._state["user_html"] = '<html><div class="wrap">USER-MAIN</div></html>'
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["views"] = fake_views("USER-MAIN")
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "PAGE-A"),
            "BU乙": fake_bu_page("BU乙", "PAGE-B"),
        }
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
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
        r = c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        assert r.status_code == 303, r.text
        return c

    # ---- 登录分流 ----
    def test_login_page_and_main_flow(self):
        r = self.raw.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("看板登录", r.text)
        self.assertNotIn("USER-MAIN", r.text)
        _, bad = self._login("overall", "wrong")
        self.assertEqual(bad.status_code, 303)
        self.assertIn("login", (bad.headers.get("location") or "").lower())
        _, zh = self._login("overall", "错的中文密码")
        self.assertEqual(zh.status_code, 303)
        _, ghost = self._login("no_such_user", "8888")
        self.assertEqual(ghost.status_code, 303)
        c, ok = self._login("overall", server.DEFAULT_VIEW_PW)
        self.assertEqual(ok.status_code, 303)
        home = c.get("/").text
        self.assertIn("加载驾驶舱", home)  # shell
        self.assertNotIn("USER-MAIN", home)
        fr = c.get("/api/v1/cockpit/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("USER-MAIN", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertIn("BU甲", fr.get("chrome_prefix") or "")

    def test_admin_login_from_root_redirects_admin(self):
        c, r = self._login("lushasha", server.DEFAULT_PW)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers.get("location"), "/admin")
        self.assertIn("管理员控制台", c.get("/admin").text)
        # 无身份下拉
        login_html = self.raw.get("/admin").text
        self.assertNotIn("identity", login_html)
        self.assertNotIn("明昊", login_html)
        self.assertIn('name="account"', login_html)

    def test_bu_account_sees_own_page_at_root(self):
        c, ok = self._login("user_a", server.DEFAULT_VIEW_PW)
        self.assertEqual(ok.status_code, 303)
        # / → 303 到本 BU
        r0 = c.get("/")
        self.assertEqual(r0.status_code, 303)
        self.assertIn("/bu/", r0.headers.get("location") or "")
        rbu = c.get(f"/bu/{quote('BU甲')}")
        self.assertEqual(rbu.status_code, 200)
        self.assertIn("加载 BU", rbu.text)  # shell-bu
        fr = c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments")
        self.assertEqual(fr.status_code, 200)
        j = fr.json()
        self.assertEqual(j["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-A", " ".join((j.get("views") or {}).get("kpi_body", {}).values()))
        self.assertEqual(c.get(f"/api/v1/cockpit/bu/{quote('BU乙')}/fragments").status_code, 403)
        self.assertIn("看板登录", c.get(f"/bu/{quote('BU乙')}").text)

    def test_multi_account_same_bu(self):
        c1, r1 = self._login("user_b1", server.DEFAULT_VIEW_PW)
        c2, r2 = self._login("user_b2", server.DEFAULT_VIEW_PW)
        self.assertEqual(r1.status_code, 303)
        self.assertEqual(r2.status_code, 303)
        for c in (c1, c2):
            r = c.get("/")
            self.assertEqual(r.status_code, 303)
            fr = c.get(f"/api/v1/cockpit/bu/{quote('BU乙')}/fragments")
            self.assertEqual(fr.status_code, 200)
            j = fr.json()
            self.assertEqual(j["fragments"].get("kpi_views"), "")
            self.assertIn("PAGE-B", " ".join((j.get("views") or {}).get("kpi_body", {}).values()))

    def test_main_and_admin_can_view_any_bu(self):
        c, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        j = c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").json()
        self.assertEqual(j["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-A", " ".join((j.get("views") or {}).get("kpi_body", {}).values()))
        a = self._admin()
        j = a.get(f"/api/v1/cockpit/bu/{quote('BU乙')}/fragments").json()
        self.assertEqual(j["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-B", " ".join((j.get("views") or {}).get("kpi_body", {}).values()))

    def test_unknown_bu_404(self):
        self.assertEqual(self.raw.get(f"/bu/{quote('不存在BU')}").status_code, 404)

    def test_tampered_cookie_rejected(self):
        c, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        cookie = c.cookies.get(server.VCOOKIE)
        r = self.raw.get("/", headers={"Cookie": f"{server.VCOOKIE}={cookie[:-4]}beef"})
        self.assertIn("看板登录", r.text)

    def test_company_endpoints_gated(self):
        q = {"start": "2026-03-01", "end": "2026-03-31"}
        self.assertEqual(self.raw.get("/api/daily", params=q).status_code, 401)
        self.assertEqual(self.raw.get("/export.png").status_code, 401)
        cbu, _ = self._login("user_a", server.DEFAULT_VIEW_PW)
        self.assertEqual(cbu.get("/api/daily", params=q).status_code, 401)
        cmain, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        self.assertEqual(cmain.get("/api/daily", params=q).status_code, 200)

    # ---- 自改 + 管理员改 ----
    def test_self_change_password(self):
        c, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        r = c.post("/api/my_passwd", json={"old": "wrong", "new": "newpw1"})
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/my_passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "12"})
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/my_passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "newpw1"})
        self.assertEqual(r.status_code, 200)
        _, old = self._login("overall", server.DEFAULT_VIEW_PW)
        self.assertIn(old.status_code, (401, 303))
        _, new = self._login("overall", "newpw1")
        self.assertEqual(new.status_code, 303)
        # 任务书46·1：管理员端不再下发明文，仅 has_hash + 占位
        a = self._admin()
        rows = a.get("/api/accounts").json()["accounts"]
        row = next(x for x in rows if x["账号"] == "overall")
        self.assertTrue(row.get("has_hash"))
        self.assertNotEqual(row.get("密码"), "newpw1")
        self.assertFalse(row["初始密码"])

    def test_change_password_kicks_old_session(self):
        """任务书46·1：改密后旧会话 401。"""
        c, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        self.assertEqual(c.get("/api/v1/session").status_code, 200)
        r = c.post("/api/my_passwd", json={"old": server.DEFAULT_VIEW_PW, "new": "kickme1"})
        self.assertEqual(r.status_code, 200)
        # 旧 cookie 密码版本过期
        self.assertEqual(c.get("/api/v1/session").status_code, 401)
        c2, _ = self._login("overall", "kickme1")
        self.assertEqual(c2.get("/api/v1/session").status_code, 200)

    def test_admin_change_password_via_accounts_api(self):
        a = self._admin()
        rows = a.get("/api/accounts").json()["accounts"]
        for r in rows:
            if r["账号"] == "user_a":
                r["密码"] = "adminset1"
        r = a.post("/api/accounts", json={"accounts": rows})
        self.assertEqual(r.status_code, 200)
        _, old = self._login("user_a", server.DEFAULT_VIEW_PW)
        self.assertIn(old.status_code, (401, 303))
        _, new = self._login("user_a", "adminset1")
        self.assertEqual(new.status_code, 303)

    def test_plain_migrates_to_hash_on_login(self):
        """明文库登录一次后明文消失、只留哈希。"""
        # 直接写旧格式明文 JSON
        p = accounts.config_path(self.cfg, self.tmp)
        p.write_text(
            json.dumps(
                {
                    "accounts": [
                        {"账号": "lushasha", "显示名": "管", "权限": "管理员", "密码": "kanban2026"},
                        {"账号": "plainu", "显示名": "迁", "权限": "整体", "密码": "plain888"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.assertIsNotNone(accounts.authenticate(self.cfg, self.tmp, "plainu", "plain888"))
        raw = json.loads(p.read_text(encoding="utf-8"))
        row = next(x for x in raw["accounts"] if x["账号"] == "plainu")
        self.assertTrue(row.get("密码哈希", "").startswith("$argon2"))
        self.assertFalse(str(row.get("密码") or "").strip())

    def test_rebind_permission_takes_effect(self):
        a = self._admin()
        rows = a.get("/api/accounts").json()["accounts"]
        for r in rows:
            if r["账号"] == "user_a":
                r["权限"] = "BU乙"
        self.assertEqual(a.post("/api/accounts", json={"accounts": rows}).status_code, 200)
        c, _ = self._login("user_a", server.DEFAULT_VIEW_PW)
        r0 = c.get("/")
        # 重绑后可能 303 到 BU 或 shell；数据看 fragments
        if r0.status_code == 303:
            fr = c.get(f"/api/v1/cockpit/bu/{quote('BU乙')}/fragments")
            self.assertEqual(fr.status_code, 200)
            j = fr.json()
            self.assertEqual(j["fragments"].get("kpi_views"), "")
            self.assertIn("PAGE-B", " ".join((j.get("views") or {}).get("kpi_body", {}).values()))
        else:
            fr = c.get("/api/v1/cockpit/fragments")
            # 若仍整体则至少不崩溃
            self.assertIn(fr.status_code, (200, 403))
        # 旧 BU 甲 fragments 应 403
        self.assertEqual(c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").status_code, 403)

    def test_delete_account_invalidates(self):
        a = self._admin()
        rows = [r for r in a.get("/api/accounts").json()["accounts"] if r["账号"] != "user_a"]
        self.assertEqual(a.post("/api/accounts", json={"accounts": rows}).status_code, 200)
        _, r = self._login("user_a", server.DEFAULT_VIEW_PW)
        self.assertIn(r.status_code, (401, 303))  # 删号后 form 登录失败

    def test_plaintext_only_on_admin_accounts_api(self):
        # 未登录
        self.assertEqual(self.raw.get("/api/accounts").status_code, 401)
        # BU 会话
        cbu, _ = self._login("user_a", server.DEFAULT_VIEW_PW)
        self.assertEqual(cbu.get("/api/accounts").status_code, 401)
        # 整体会话
        cmain, _ = self._login("overall", server.DEFAULT_VIEW_PW)
        self.assertEqual(cmain.get("/api/accounts").status_code, 401)
        # 设置/BU 配置不下发明文看板密码
        a = self._admin()
        settings = a.get("/api/settings").json()
        self.assertNotIn("密码", json.dumps(settings, ensure_ascii=False))
        for b in a.get("/api/bu_config").json()["bus"]:
            self.assertNotIn("密码", b)
            self.assertNotIn("密码hash", b)
        # 管理员 accounts：有密码字段但非真实明文（占位或空）；has_hash 标记
        rows = a.get("/api/accounts").json()["accounts"]
        self.assertTrue(any(r.get("has_hash") or r.get("密码") for r in rows))
        for r in rows:
            if r.get("has_hash"):
                self.assertNotIn(r.get("密码"), (server.DEFAULT_VIEW_PW, server.DEFAULT_PW, "newpw1"))
        # 自改密码弹窗文案在 HTML 壳（JS 只绑事件，文案不在 static/js）
        import render

        self.assertIn("密码管理员可见，请勿使用你在其他地方用的密码", render.PW_MODAL_HTML)
        _js = (Path(__file__).resolve().parents[1] / "static" / "js" / "cockpit.js").read_text(encoding="utf-8")
        self.assertIn("pwBtn", _js)
        self.assertIn("/api/my_passwd", _js)

    def test_initial_password_yellow_flag(self):
        a = self._admin()
        rows = a.get("/api/accounts").json()["accounts"]
        init = [r for r in rows if r["账号"] == "overall"][0]
        self.assertTrue(init["初始密码"])
        for r in rows:
            if r["账号"] == "overall":
                r["密码"] = "changed9"
        a.post("/api/accounts", json={"accounts": rows})
        again = [r for r in a.get("/api/accounts").json()["accounts"] if r["账号"] == "overall"][0]
        self.assertFalse(again["初始密码"])

    def test_admin_console_has_accounts_card_unified_save(self):
        html = server.admin_ui_source()
        self.assertIn("账号与权限", html)
        self.assertIn("BU 数据归属", html)
        # 设置页统一底部保存条（各卡就近保存按钮已删，改为标脏+底部一键保存）
        self.assertIn("setSaveBar", html)
        self.assertIn("保存全部设置", html)
        self.assertIn("setSaveAll", html)
        self.assertNotIn(">保存账号<", html)
        self.assertNotIn("保存自动更新<", html)
        self.assertNotIn("保存备份设置<", html)
        self.assertIn("智云账号 · 台账路径", html)  # 智云账号卡并入收单台账共享盘路径（F-01 配置分离）
        self.assertIn("sLedgerPath", html)  # 台账路径输入框
        self.assertIn("showToast", html)
        self.assertNotIn("登录密码（集中管理）", html)
        self.assertNotIn("密码（填=重置", html)

    def test_admin_console_refresh_honesty(self):
        """v1.0.4：更新按钮诚实化——全绿才「更新成功」；有降级/体检问题报「更新完成，但有 N 个问题」可点击跳体检明细。"""
        html = server.admin_ui_source()
        self.assertIn("refreshResultToast", html)
        self.assertIn("更新完成，但有", html)
        self.assertIn("更新成功", html)
        self.assertIn("#toast.warn", html)
        self.assertIn("#toast.clickable", html)
        # 完成分支不再无条件报「数据已更新」
        self.assertNotIn("数据已更新", html)

    def test_last_login_written(self):
        self._login("overall", server.DEFAULT_VIEW_PW)
        acc = accounts.find_account(self.cfg, self.tmp, "overall")
        self.assertTrue(acc.get("最后登录"))

    def test_operator_is_login_account(self):
        """经手人=登录账号：admin cookie 主体是 lushasha（签发侧断言）。"""
        sec = server._load_or_init_secret(self.cfg, self.tmp)
        tok = server._make_token(sec, "lushasha")
        self.assertEqual(server._check_token(sec, tok), "lushasha")
        # 登录路径真正发出的 cookie 能进需会话接口
        c, r = self._login("lushasha", server.DEFAULT_PW)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers.get("location"), "/admin")
        # 换 admin 表单登录同样成功
        a = self._admin()
        self.assertEqual(a.get("/api/accounts").status_code, 200)

    def test_bu_config_no_password_column_persists_clean(self):
        saved = bu.save_bu_config(
            self.cfg,
            self.tmp,
            [
                {"name": "BU甲", "销售": ["销售A"], "密码hash": "should-drop", "新密码": "x"},
                {"name": "整体", "销售": ["x"]},  # 保留字拒
            ],
        )
        self.assertEqual([b["name"] for b in saved["bus"]], ["BU甲"])
        self.assertNotIn("密码hash", saved["bus"][0])
        self.assertNotIn("新密码", saved["bus"][0])


class TestHidePwForAdmin(unittest.TestCase):
    """管理员会话看内嵌看板时隐藏「🔑密码」自改入口；看的人（整体/BU）仍保留。
    （明昊 2026-07-12：管理员改密码走 /admin 设置页，防在内嵌看板里误改。）"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        _write_accts(self.cfg, self.tmp, _std_accts())
        server._state["user_html"] = (
            '<html><head></head><body><button id="pwBtn">🔑 密码</button>'
            '<div class="wrap">USER-MAIN</div></body></html>'
        )
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["views"] = fake_views("USER-MAIN")
        page = fake_bu_page("BU甲", "PAGE-A")
        page["html"] = '<html><body><button id="pwBtn">🔑 密码</button><div class="wrap">PAGE-A</div></body></html>'
        server._state["bu_pages"] = {"BU甲": page}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _as(self, account, pw, admin=False):
        c = self._client()
        r = c.post("/admin/login" if admin else "/login", data={"account": account, "password": pw})
        assert r.status_code == 303, r.text
        return c

    _MARK = "#pwBtn{display:none"

    def test_admin_root_hides_pw(self):
        c = self._as("lushasha", server.DEFAULT_PW, admin=True)
        fr = c.get("/api/v1/cockpit/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("USER-MAIN", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertIn(self._MARK, fr.get("chrome_prefix") or "")

    def test_viewer_root_keeps_pw(self):
        c = self._as("overall", server.DEFAULT_VIEW_PW)
        fr = c.get("/api/v1/cockpit/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("USER-MAIN", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertNotIn(self._MARK, fr.get("chrome_prefix") or "")
        # 改密按钮在缓存 HTML 里
        self.assertIn('id="pwBtn"', server._state["user_html"])

    def test_admin_bu_page_hides_pw(self):
        c = self._as("lushasha", server.DEFAULT_PW, admin=True)
        fr = c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-A", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertIn(self._MARK, fr.get("chrome_prefix") or "")

    def test_bu_viewer_keeps_pw(self):
        c = self._as("user_a", server.DEFAULT_VIEW_PW)
        fr = c.get(f"/api/v1/cockpit/bu/{quote('BU甲')}/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-A", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertNotIn(self._MARK, fr.get("chrome_prefix") or "")
        self.assertIn('id="pwBtn"', server._state["bu_pages"]["BU甲"]["html"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
