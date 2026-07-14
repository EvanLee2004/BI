#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视图档案测试（2026-07-15：精简视图已下线，统一完整 full）。

守卫：
- accounts.view_profile 恒返回 full（忽略角色 / 账号「视图」字段）
- server._apply_profile 对 full/非法不改 HTML；对 executive 仍能换属性（兼容旧路径，但线上不再注入）
- 登录后整体/管理员/BU 页根节点均为 data-profile=full
- 管理端无「精简视图」预览按钮
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, render, server  # noqa: E402

_SHELL = '<html lang="zh-CN" data-profile="full"><body><div class="wrap">{}</div></body></html>'


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestViewProfileResolve(unittest.TestCase):
    def test_always_full_regardless_of_role(self):
        self.assertEqual(accounts.view_profile({"权限": "管理员"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "整体"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "BU", "可见BU": ["甲"]}), "full")
        self.assertEqual(accounts.view_profile({"权限": "数据"}), "full")

    def test_account_field_ignored(self):
        # 旧配置若写了 executive，也不再生效
        self.assertEqual(accounts.view_profile({"权限": "整体", "视图": "executive"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "管理员", "视图": "executive"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "整体", "视图": "乱填"}), "full")

    def test_none_account(self):
        self.assertEqual(accounts.view_profile(None), "full")


class TestApplyProfile(unittest.TestCase):
    def test_swaps_full_to_executive_once_compat(self):
        # 兼容：函数仍可把 full→executive（不主动调用）；只换根节点一次
        html = _SHELL.format("X") + '<span>data-profile="full"</span>'
        out = server._apply_profile(html, "executive")
        self.assertIn('<html lang="zh-CN" data-profile="executive">', out)
        self.assertIn('<span>data-profile="full"</span>', out)

    def test_full_unchanged(self):
        html = _SHELL.format("X")
        self.assertEqual(server._apply_profile(html, "full"), html)

    def test_invalid_unchanged(self):
        html = _SHELL.format("X")
        self.assertEqual(server._apply_profile(html, "乱填"), html)
        self.assertEqual(server._apply_profile(html, ""), html)

    def test_empty_html(self):
        self.assertEqual(server._apply_profile("", "executive"), "")


class TestProfileServing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        accounts.save_accounts(self.cfg, self.tmp, [
            {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
            {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            {"账号": "user_a", "显示名": "甲负责人", "权限": "BU甲", "密码": server.DEFAULT_VIEW_PW},
        ])
        server._state["user_html"] = _SHELL.format("USER-MAIN")
        server._state["bu_pages"] = {"BU甲": {"name": "BU甲", "html": _SHELL.format("PAGE-A")}}
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, follow_redirects=False)

    def _login(self, account, pw):
        c = self._client()
        c.post("/login", data={"account": account, "password": pw})
        return c

    def test_overall_gets_full(self):
        c = self._login("overall", server.DEFAULT_VIEW_PW)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)

    def test_admin_gets_full(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)

    def test_bu_account_gets_full_on_root(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)

    def test_bu_account_gets_full_on_bu_route(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        r = c.get("/bu/" + quote("BU甲"))
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)


class TestProfileStatics(unittest.TestCase):
    def test_admin_console_no_preview_toggle(self):
        page = server._admin_page('<html data-profile="full"><div class="wrap">D</div></html>', {})
        self.assertNotIn('id="profBtn"', page)
        self.assertNotIn("精简视图", page)
        self.assertIn('id="chrome"', page)  # 顶栏冻结容器
        self.assertIn("position:sticky", page)

    def test_dashboard_shell_defaults_full(self):
        import inspect
        src = inspect.getsource(render)
        self.assertIn('data-profile="full"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
