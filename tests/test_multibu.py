#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""③ 账号绑定多个 BU 测试。跑：.venv/bin/python tests/test_multibu.py

守卫点（明昊 2026-07-12 拍板：权限从「单个BU/整体」→ 可绑一组 BU；整体=全部）：
- accounts.bu_names_of / can_see_bu：权限=BU→可见BU 列表；旧单 BU 名→[该名]；管理员/整体→[]
- 落盘/读回保留 可见BU（权限=BU）；旧单名账号仍兼容；public_row 带 可见BU
- 多 BU 账号：`/` 落第一个绑定 BU + 顶部「我的 BU」切换条（只列绑定的、不泄漏他 BU）
- 多 BU 账号：可看绑定的每个 /bu/{x}，**不可看未绑定的**（出登录页、不泄漏名）
- 整体/管理员仍看全部；BU 账号 `_can_view_main` 仍 False；绑定 BU 全被移除→提示
- 控制台含多 BU UI 锚点（acct-bus / acctToggleBu / 按 BU）
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts
import bu
import loaders
import server
from support import fake_main_frags, fake_bu_page, fake_views  # noqa: E402


def _write_bucfg(cfg, root, names):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"bus": [{"name": n, "销售": [f"S{n}"]} for n in names]}, ensure_ascii=False), encoding="utf-8"
    )


class TestAccountsMultiBu(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()

    def test_bu_names_of(self):
        self.assertEqual(accounts.bu_names_of({"权限": "BU", "可见BU": ["甲", "乙"]}), ["甲", "乙"])
        self.assertEqual(accounts.bu_names_of({"权限": "丙"}), ["丙"])  # 旧单 BU 名
        self.assertEqual(accounts.bu_names_of({"权限": "整体"}), [])
        self.assertEqual(accounts.bu_names_of({"权限": "管理员"}), [])
        self.assertEqual(accounts.bu_names_of({"权限": "BU"}), [])  # BU 但没绑=看不到

    def test_can_see_bu(self):
        m = {"权限": "BU", "可见BU": ["甲", "乙"]}
        self.assertTrue(accounts.can_see_bu(m, "甲"))
        self.assertTrue(accounts.can_see_bu(m, "乙"))
        self.assertFalse(accounts.can_see_bu(m, "丙"))
        self.assertFalse(accounts.can_see_bu({"权限": "整体"}, "甲"))

    def test_roundtrip_multi(self):
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "权限": "管理员", "密码": "kanban2026", "显示名": "管"},
                {"账号": "m", "权限": "BU", "可见BU": ["甲", "乙", "整体", "甲"], "密码": "8888", "显示名": "多"},
                {"账号": "leg", "权限": "丙", "密码": "8888", "显示名": "旧"},
            ],
        )
        rows = {a["账号"]: a for a in accounts.load_accounts(self.cfg, self.tmp)}
        self.assertEqual(rows["m"]["权限"], "BU")
        self.assertEqual(rows["m"]["可见BU"], ["甲", "乙"])  # 去重 + 去「整体」保留字
        self.assertEqual(accounts.bu_names_of(rows["leg"]), ["丙"])  # 旧单名保留
        self.assertNotIn("可见BU", rows["leg"])  # 旧账号不写空列表

    def test_public_row_has_bus(self):
        acc = {"账号": "m", "权限": "BU", "可见BU": ["甲", "乙"], "密码": "8888"}
        self.assertEqual(accounts.public_row(acc)["可见BU"], ["甲", "乙"])
        self.assertEqual(accounts.public_row({"账号": "o", "权限": "整体", "密码": "8888"})["可见BU"], [])


class TestServerMultiBu(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, ["BU甲", "BU乙", "BU丙"])
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "权限": "管理员", "密码": server.DEFAULT_PW, "显示名": "管"},
                {"账号": "overall", "权限": "整体", "密码": server.DEFAULT_VIEW_PW, "显示名": "整"},
                {
                    "账号": "multi",
                    "权限": "BU",
                    "可见BU": ["BU甲", "BU乙"],
                    "密码": server.DEFAULT_VIEW_PW,
                    "显示名": "多",
                },
                {"账号": "legacy", "权限": "BU丙", "密码": server.DEFAULT_VIEW_PW, "显示名": "旧"},
                {"账号": "ghost", "权限": "BU", "可见BU": ["已删BU"], "密码": server.DEFAULT_VIEW_PW, "显示名": "全删"},
            ],
        )
        server._state["user_html"] = '<html><div class="wrap">MAIN</div></html>'
        server._state["fragments"] = fake_main_frags("MAIN")
        server._state["views"] = fake_views("MAIN")
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "PAGE-甲"),
            "BU乙": fake_bu_page("BU乙", "PAGE-乙"),
            "BU丙": fake_bu_page("BU丙", "PAGE-丙"),
        }
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _login(self, account, pw=None):
        from fastapi.testclient import TestClient

        c = TestClient(self.app, follow_redirects=False)
        c.post("/login", data={"account": account, "password": pw or server.DEFAULT_VIEW_PW})
        return c

    def test_multi_landing_and_switcher(self):
        c = self._login("multi")
        r0 = c.get("/")
        self.assertEqual(r0.status_code, 303)
        from urllib.parse import unquote

        loc = unquote(r0.headers.get("location") or "")
        self.assertIn("/bu/BU甲", loc)
        fr = c.get("/api/v1/cockpit/bu/BU甲/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-甲", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        chrome = fr.get("chrome_prefix") or ""
        self.assertIn("我的 BU", chrome)
        self.assertIn("BU甲", chrome)
        self.assertIn("BU乙", chrome)
        self.assertNotIn("BU丙", chrome)

    def test_multi_can_view_each_bound(self):
        c = self._login("multi")
        for n, mark in (("BU甲", "PAGE-甲"), ("BU乙", "PAGE-乙")):
            self.assertEqual(c.get(f"/bu/{n}").status_code, 200)
            self.assertIn("智能经营罗盘", c.get(f"/bu/{n}").text)
            fr = c.get(f"/api/v1/cockpit/bu/{n}/fragments").json()
            self.assertEqual(fr["fragments"].get("kpi_views"), "")
            self.assertIn(mark, " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
            self.assertIn("我的 BU", fr.get("chrome_prefix") or "")

    def test_multi_cannot_view_unbound(self):
        c = self._login("multi")
        r = c.get("/bu/BU丙")
        self.assertIn("看板登录", r.text)
        self.assertEqual(c.get("/api/v1/cockpit/bu/BU丙/fragments").status_code, 403)

    def test_legacy_single_still_works(self):
        c = self._login("legacy")
        r0 = c.get("/")
        self.assertEqual(r0.status_code, 303)
        fr = c.get("/api/v1/cockpit/bu/BU丙/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("PAGE-丙", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        self.assertNotIn("我的 BU", fr.get("chrome_prefix") or "")
        self.assertEqual(c.get("/api/v1/cockpit/bu/BU甲/fragments").status_code, 403)

    def test_overall_sees_all(self):
        c = self._login("overall")
        home = c.get("/").text
        self.assertIn("智能经营罗盘", home)
        fr = c.get("/api/v1/cockpit/fragments").json()
        self.assertEqual(fr["fragments"].get("kpi_views"), "")
        self.assertIn("MAIN", " ".join((fr.get("views") or {}).get("kpi_body", {}).values()))
        for n in ("BU甲", "BU乙", "BU丙"):
            self.assertIn(n, fr.get("chrome_prefix") or "")
            mark = f"PAGE-{n[-1]}"
            j = c.get(f"/api/v1/cockpit/bu/{n}/fragments").json()
            self.assertEqual(j["fragments"].get("kpi_views"), "")
            self.assertIn(mark, " ".join((j.get("views") or {}).get("kpi_body", {}).values()))

    def test_bu_account_not_main(self):
        c = self._login("multi")
        self.assertEqual(c.get("/api/daily").status_code, 401)

    def test_all_bound_removed(self):
        c = self._login("ghost")
        r0 = c.get("/")
        self.assertEqual(r0.status_code, 303)
        loc = r0.headers.get("location") or ""
        self.assertIn("login", loc)
        from urllib.parse import unquote as _uq

        self.assertIn("移除", _uq(loc))

    def test_console_has_multibu_ui(self):
        html = server.admin_ui_source()
        for anchor in ("acct-bus", "acctToggleBu", "acctSetType", "按 BU"):
            self.assertIn(anchor, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
