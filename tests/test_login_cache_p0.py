#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 0 · 登录页 HTTP 缓存 P0：会话态文档路由必须 Cache-Control: no-store。

根因：未登录 GET /admin、/、/bu/* 回登录页 FileResponse 无 no-store → 浏览器缓存
「该 URL=登录页」；登录后 location.replace 同 URL 直接吃缓存 → 永远卡登录页。

断言：
1. 各文档路由响应头含 no-store
2. TestClient：未登录 GET → 登录 → 再 GET 同 URL，两次 body 不同且第二次非登录页
3. 前端 shell 对 fragments 401 跳 /login（静态字符串守卫）
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
from support import fake_bu_page, fake_main_frags, fake_views  # noqa: E402


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(__import__("json").dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


def _std_accts():
    return [
        {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
        {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
        {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
    ]


def _has_no_store(resp) -> bool:
    cc = resp.headers.get("cache-control") or resp.headers.get("Cache-Control") or ""
    return "no-store" in cc.lower()


class TestLoginCacheP0(unittest.TestCase):
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

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_document_routes_send_no_store(self):
        """未登录/已登录文档路由一律带 Cache-Control: no-store。"""
        c = self._client()
        # 未登录：登录页
        for path in ("/", "/login", "/admin", f"/bu/{quote('BU甲')}"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertTrue(_has_no_store(r), f"{path} 缺 no-store: {r.headers.get('cache-control')}")

        # 整体账号登录后：/ 为 shell
        c_main = self._client()
        r_login = c_main.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r_login.status_code, 303)
        r_home = c_main.get("/")
        self.assertEqual(r_home.status_code, 200)
        self.assertTrue(_has_no_store(r_home), "已登录 / 缺 no-store")
        self.assertIn("加载驾驶舱", r_home.text)

        # BU 账号：/bu 为 shell-bu
        c_bu = self._client()
        r_login = c_bu.post("/login", data={"account": "user_a", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(r_login.status_code, 303)
        r_bu = c_bu.get(f"/bu/{quote('BU甲')}")
        self.assertEqual(r_bu.status_code, 200)
        self.assertTrue(_has_no_store(r_bu), "已登录 /bu 缺 no-store")
        self.assertIn("加载 BU", r_bu.text)

        # 管理员：/admin 控制台
        c_adm = self._client()
        r_login = c_adm.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.assertEqual(r_login.status_code, 303)
        r_adm = c_adm.get("/admin")
        self.assertEqual(r_adm.status_code, 200)
        self.assertTrue(_has_no_store(r_adm), "已登录 /admin 缺 no-store")
        self.assertIn("管理员控制台", r_adm.text)

        # /admin/app.js 先例仍在
        r_js = c_adm.get("/admin/app.js")
        self.assertEqual(r_js.status_code, 200)
        self.assertTrue(_has_no_store(r_js), "/admin/app.js 缺 no-store")

    def test_login_then_same_url_body_flips(self):
        """模拟：先未登录 GET 造缓存场景 → 登录 → 再 GET 同 URL，body 须变且非登录页。"""
        cases = [
            # label, path, login_url, creds, after_marker
            ("admin", "/admin", "/admin/login", {"account": "lushasha", "password": server.DEFAULT_PW}, "管理员控制台"),
            ("overall", "/", "/login", {"account": "overall", "password": server.DEFAULT_VIEW_PW}, "加载驾驶舱"),
            (
                "bu",
                f"/bu/{quote('BU甲')}",
                "/login",
                {"account": "user_a", "password": server.DEFAULT_VIEW_PW},
                "加载 BU",
            ),
        ]
        for label, path, login_url, creds, after_marker in cases:
            with self.subTest(label=label):
                c = self._client()
                r0 = c.get(path)
                self.assertEqual(r0.status_code, 200)
                self.assertTrue(_has_no_store(r0), f"{label} 未登录缺 no-store")
                # 未登录：登录页（看端「看板登录」/ 管理端「管理员端登录」）
                self.assertTrue(
                    "看板登录" in r0.text or "管理员端登录" in r0.text,
                    f"{label}: 未登录应回登录页",
                )
                r_login = c.post(login_url, data=creds)
                self.assertEqual(r_login.status_code, 303, r_login.text)
                r1 = c.get(path)
                self.assertEqual(r1.status_code, 200)
                self.assertTrue(_has_no_store(r1), f"{label} 已登录缺 no-store")
                self.assertNotEqual(r0.text, r1.text, f"{label}: 登录前后 body 应不同")
                self.assertIn(after_marker, r1.text, f"{label}: 登录后应是目标页")
                self.assertNotIn("管理员端登录", r1.text)
                self.assertNotIn("看板登录", r1.text)

    def test_shell_fragments_401_navigates_to_login(self):
        """shell / shell-bu 对 fragments 401 必须 location.replace('/login')（会话过期不白屏）。"""
        for name in ("shell.html", "shell-bu.html"):
            src = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertIn("status===401", src, name)
            self.assertIn("location.replace('/login')", src, name)
            self.assertIn("fragments", src, name)

        # admin 端 401 → /admin
        admin_js = (ROOT / "static" / "admin" / "admin.js").read_text(encoding="utf-8")
        self.assertIn("status===401", admin_js.replace(" ", "").replace("\n", "") or admin_js)
        self.assertTrue(
            'location.href="/admin"' in admin_js
            or "location.href='/admin'" in admin_js
            or "r.status===401" in admin_js,
            "admin.js 须对 401 跳登录",
        )

    def test_viewer_pages_have_logout_button(self):
        """深检①：看端整体/BU 须有退出入口，调 /api/v1/logout。"""
        for name in (
            "static/templates/render/dashboard_body.html",
            "static/templates/render/bu_body.html",
        ):
            t = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("logoutBtn", t, name)
        for name in ("static/js/cockpit.js", "static/js/cockpit-bu.js"):
            t = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("logoutBtn", t, name)
            self.assertIn("/api/v1/logout", t, name)


if __name__ == "__main__":
    unittest.main()
