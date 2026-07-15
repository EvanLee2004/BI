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

import accounts, bu, loaders, server  # noqa: E402


def _write_bucfg(cfg, root, names):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": [{"name": n, "销售": [f"S{n}"]} for n in names]},
                            ensure_ascii=False), encoding="utf-8")


class TestAccountsMultiBu(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()

    def test_bu_names_of(self):
        self.assertEqual(accounts.bu_names_of({"权限": "BU", "可见BU": ["甲", "乙"]}), ["甲", "乙"])
        self.assertEqual(accounts.bu_names_of({"权限": "丙"}), ["丙"])  # 旧单 BU 名
        self.assertEqual(accounts.bu_names_of({"权限": "整体"}), [])
        self.assertEqual(accounts.bu_names_of({"权限": "管理员"}), [])
        self.assertEqual(accounts.bu_names_of({"权限": "BU"}), [])       # BU 但没绑=看不到

    def test_can_see_bu(self):
        m = {"权限": "BU", "可见BU": ["甲", "乙"]}
        self.assertTrue(accounts.can_see_bu(m, "甲"))
        self.assertTrue(accounts.can_see_bu(m, "乙"))
        self.assertFalse(accounts.can_see_bu(m, "丙"))
        self.assertFalse(accounts.can_see_bu({"权限": "整体"}, "甲"))

    def test_roundtrip_multi(self):
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "权限": "管理员", "密码": "kanban2026", "显示名": "管"},
            {"账号": "m", "权限": "BU", "可见BU": ["甲", "乙", "整体", "甲"], "密码": "8888", "显示名": "多"},
            {"账号": "leg", "权限": "丙", "密码": "8888", "显示名": "旧"},
        ])
        rows = {a["账号"]: a for a in accounts.load_accounts(self.cfg, self.tmp)}
        self.assertEqual(rows["m"]["权限"], "BU")
        self.assertEqual(rows["m"]["可见BU"], ["甲", "乙"])            # 去重 + 去「整体」保留字
        self.assertEqual(accounts.bu_names_of(rows["leg"]), ["丙"])    # 旧单名保留
        self.assertNotIn("可见BU", rows["leg"])                        # 旧账号不写空列表

    def test_public_row_has_bus(self):
        acc = {"账号": "m", "权限": "BU", "可见BU": ["甲", "乙"], "密码": "8888"}
        self.assertEqual(accounts.public_row(acc)["可见BU"], ["甲", "乙"])
        self.assertEqual(accounts.public_row({"账号": "o", "权限": "整体", "密码": "8888"})["可见BU"], [])


class TestServerMultiBu(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, ["BU甲", "BU乙", "BU丙"])
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "权限": "管理员", "密码": server.DEFAULT_PW, "显示名": "管"},
            {"账号": "overall", "权限": "整体", "密码": server.DEFAULT_VIEW_PW, "显示名": "整"},
            {"账号": "multi", "权限": "BU", "可见BU": ["BU甲", "BU乙"],
             "密码": server.DEFAULT_VIEW_PW, "显示名": "多"},
            {"账号": "legacy", "权限": "BU丙", "密码": server.DEFAULT_VIEW_PW, "显示名": "旧"},
            {"账号": "ghost", "权限": "BU", "可见BU": ["已删BU"],
             "密码": server.DEFAULT_VIEW_PW, "显示名": "全删"},
        ])
        server._state["user_html"] = '<html><div class="wrap">MAIN</div></html>'
        server._state["bu_pages"] = {
            "BU甲": {"name": "BU甲", "html": '<html><div class="wrap">PAGE-甲</div></html>'},
            "BU乙": {"name": "BU乙", "html": '<html><div class="wrap">PAGE-乙</div></html>'},
            "BU丙": {"name": "BU丙", "html": '<html><div class="wrap">PAGE-丙</div></html>'},
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
        home = c.get("/").text
        self.assertIn("PAGE-甲", home)          # 落第一个绑定 BU
        self.assertIn("我的 BU", home)          # 切换条
        self.assertIn("BU甲", home)
        self.assertIn("BU乙", home)
        self.assertNotIn("BU丙", home)          # 不泄漏未绑定 BU 名

    def test_multi_can_view_each_bound(self):
        c = self._login("multi")
        a = c.get("/bu/BU甲"); b = c.get("/bu/BU乙")
        self.assertEqual(a.status_code, 200); self.assertIn("PAGE-甲", a.text)
        self.assertEqual(b.status_code, 200); self.assertIn("PAGE-乙", b.text)
        self.assertIn("我的 BU", a.text)        # BU 页也带切换条
        self.assertIn("BU乙", a.text)           # 切换条含另一个绑定 BU

    def test_multi_cannot_view_unbound(self):
        c = self._login("multi")
        r = c.get("/bu/BU丙")
        self.assertNotIn("PAGE-丙", r.text)     # 看不到未绑定 BU 内容
        self.assertIn("看板登录", r.text)        # 出登录页

    def test_legacy_single_still_works(self):
        c = self._login("legacy")
        home = c.get("/").text
        self.assertIn("PAGE-丙", home)
        self.assertNotIn("我的 BU", home)        # 单个绑定不出切换条
        self.assertNotIn("PAGE-甲", c.get("/bu/BU甲").text)  # 越权不行

    def test_overall_sees_all(self):
        c = self._login("overall")
        home = c.get("/").text
        self.assertIn("MAIN", home)
        for n in ("BU甲", "BU乙", "BU丙"):
            self.assertIn(n, home)
            self.assertIn(f"PAGE-{n[-1]}", c.get(f"/bu/{n}").text)

    def test_bu_account_not_main(self):
        c = self._login("multi")
        # /api/daily 只认整体/管理员 → BU 账号 401
        self.assertEqual(c.get("/api/daily").status_code, 401)

    def test_all_bound_removed(self):
        c = self._login("ghost")            # 只绑「已删BU」（不在 bu_pages）
        home = c.get("/").text
        self.assertIn("已被管理员移除", home)
        self.assertNotIn("PAGE-", home)

    def test_console_has_multibu_ui(self):
        html = server.admin_ui_source()
        for anchor in ("acct-bus", "acctToggleBu", "acctSetType", "按 BU"):
            self.assertIn(anchor, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
