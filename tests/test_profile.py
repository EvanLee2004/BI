#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 视图档案（view_profile）测试。跑：.venv/bin/python tests/test_profile.py

守卫点（2026-07-14）：
- accounts.view_profile：管理员→full、整体/BU→executive；账号 `视图` 字段可覆盖；非法值兜底角色默认。
- server._apply_profile：只换根节点 data-profile 一次；full/空/非法 → 不改（安全默认=完整）。
- 服务分档：整体(姜总)登录 / → executive；管理员看 / → full；BU 账号 / 与 /bu/{name} → executive。
- 纯展示层：executive 只 CSS 隐藏公式/标注（theme 有 [data-profile="executive"] 规则），**页面数字/生成缓存不变**（回归红线中性）。
- 管理端有「详细/精简（姜总视角）」预览开关（profBtn + cockpit-profile postMessage）。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts, bu, loaders, render, theme, server  # noqa: E402

_SHELL = '<html lang="zh-CN" data-profile="full"><body><div class="wrap">{}</div></body></html>'


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestViewProfileResolve(unittest.TestCase):
    def test_role_defaults(self):
        self.assertEqual(accounts.view_profile({"权限": "管理员"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "整体"}), "executive")
        self.assertEqual(accounts.view_profile({"权限": "BU", "可见BU": ["甲"]}), "executive")
        self.assertEqual(accounts.view_profile({"权限": "数据"}), "executive")  # 旧单 BU 名

    def test_account_field_overrides(self):
        self.assertEqual(accounts.view_profile({"权限": "整体", "视图": "full"}), "full")
        self.assertEqual(accounts.view_profile({"权限": "管理员", "视图": "executive"}), "executive")

    def test_bad_field_falls_back_to_role(self):
        self.assertEqual(accounts.view_profile({"权限": "整体", "视图": "乱填"}), "executive")
        self.assertEqual(accounts.view_profile({"权限": "管理员", "视图": ""}), "full")

    def test_none_account(self):
        # 无账号（未登录）不应崩；按非管理员=executive 兜底
        self.assertEqual(accounts.view_profile(None), "executive")


class TestApplyProfile(unittest.TestCase):
    def test_swaps_full_to_executive_once(self):
        html = _SHELL.format("X") + '<span>data-profile="full"</span>'  # 正文里再有一处也不该被换
        out = server._apply_profile(html, "executive")
        self.assertIn('<html lang="zh-CN" data-profile="executive">', out)
        # 正文那处未被替换（replace(...,1) 只命中第一处=<html> 标签）
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

    def test_overall_gets_executive(self):
        c = self._login("overall", server.DEFAULT_VIEW_PW)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="executive"', r.text)
        self.assertNotIn('data-profile="full"', r.text)

    def test_admin_gets_full(self):
        c = self._client()
        c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        r = c.get("/")  # 管理员会话看整体页
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="full"', r.text)
        self.assertNotIn('data-profile="executive"', r.text)

    def test_bu_account_gets_executive_on_root(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        r = c.get("/")  # BU 账号落本 BU 页
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="executive"', r.text)

    def test_bu_account_gets_executive_on_bu_route(self):
        c = self._login("user_a", server.DEFAULT_VIEW_PW)
        r = c.get("/bu/" + quote("BU甲"))
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-profile="executive"', r.text)


class TestProfileStatics(unittest.TestCase):
    def test_theme_css_hides_formulas_in_executive(self):
        css = theme.get_css()
        self.assertIn('[data-profile="executive"]', css)
        # 隐藏的是公式/标注类，不碰数字类
        for cls in (".src", ".pr-formula", ".chart-note", ".foot", ".faint-note", ".kinds"):
            self.assertIn(cls, css)

    def test_admin_console_has_preview_toggle(self):
        page = server._admin_page('<html data-profile="full"><div class="wrap">D</div></html>', {})
        self.assertIn('id="profBtn"', page)
        self.assertIn('cockpit-profile', page)

    def test_dashboard_shell_defaults_full_and_listens_profile(self):
        # 渲染层脚本应含 cockpit-profile 监听（管理端预览开关切内嵌看板用）
        import inspect
        src = inspect.getsource(render)
        self.assertIn('cockpit-profile', src)
        self.assertIn('data-profile="full"', src)  # 两个页面外壳默认完整


if __name__ == "__main__":
    unittest.main(verbosity=2)
