#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""① 产品版本号 + 更新日志测试。跑：.venv/bin/python tests/test_version.py

守卫点（明昊 2026-07-12 拍板·2026-07-13 升 Beta）：
- 产品版本号唯一源=根目录 VERSION（现 1.0-beta=公测 Beta；0.9=试运行；主版本≥1 无 -beta=正式版），与 git 开发号(v8.x)分开；
- version 模块：read_version / product_stage / product_label / version_info 结构；changelog 是副本（改不动常量）；
- `/api/version`：仅管理员会话（无会话/查看端 401），下发 version/stage/label/changelog。
"""

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
import version as V  # noqa: E402


class TestVersionModule(unittest.TestCase):
    def test_version_file_is_source_of_truth(self):
        # 根目录 VERSION 真实存在且与模块读到的一致
        self.assertTrue((ROOT / "VERSION").exists())
        self.assertEqual(V.read_version(), (ROOT / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(V.PRODUCT_VERSION, V.read_version())

    def test_stage_derivation(self):
        self.assertEqual(V.product_stage("0.9"), "试运行")
        self.assertEqual(V.product_stage("0.1"), "试运行")
        self.assertEqual(V.product_stage("1.0-beta"), "公测 Beta")  # 预发布标记优先
        self.assertEqual(V.product_stage("1.0-BETA"), "公测 Beta")  # 大小写不敏感
        self.assertEqual(V.product_stage("2.0.0-rc1"), "发布候选")
        self.assertEqual(V.product_stage("1.0"), "正式版")
        self.assertEqual(V.product_stage("2.3"), "正式版")
        self.assertEqual(V.product_stage("坏值"), "试运行")  # 解析不了按试运行兜底

    def test_current_is_rc(self):
        # 封板 54.11：VERSION=2.0.0-rc2 发布候选（rc* 均兼容）
        cur = V.read_version()
        self.assertTrue("rc" in cur.lower(), cur)
        self.assertEqual(V.product_stage(cur), "发布候选")
        self.assertEqual(V.product_label("2.0.0-rc2"), "v2.0.0（发布候选）")
        self.assertEqual(V.product_label("2.0.0-rc1"), "v2.0.0（发布候选）")
        self.assertEqual(V.product_label("1.0-beta"), "v1.0（公测 Beta）")
        self.assertEqual(V.product_label("0.9"), "v0.9（试运行）")

    def test_changelog_is_copy(self):
        cl = V.changelog()
        self.assertTrue(cl and isinstance(cl, list))
        cl[0]["items"].append("篡改")
        cl[0]["title"] = "改了"
        # 原常量不受影响
        self.assertNotIn("篡改", V.PRODUCT_CHANGELOG[0]["items"])
        self.assertNotEqual(V.PRODUCT_CHANGELOG[0]["title"], "改了")

    def test_changelog_shape(self):
        for e in V.PRODUCT_CHANGELOG:
            self.assertIn("date", e)
            self.assertIn("title", e)
            self.assertTrue(isinstance(e.get("items"), list) and e["items"])

    def test_version_info_structure(self):
        info = V.version_info()
        self.assertEqual(set(info), {"version", "stage", "label", "changelog"})
        self.assertEqual(info["version"], V.PRODUCT_VERSION)
        # label 用主号（去 -beta 预发布后缀）：v1.0（公测 Beta）
        self.assertEqual(info["label"], f"v{info['version'].split('-')[0]}（{info['stage']}）")


class TestVersionApi(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = loaders.load_config()
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员甲", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体甲", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        server._state["user_html"] = '<html><div class="wrap">USER-MAIN</div></html>'
        server._state["admin_html"] = server._admin_page(server._state["user_html"], {})
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def test_requires_admin(self):
        # 未登录 → 401
        c = self._client()
        self.assertEqual(c.get("/api/version").status_code, 401)
        # 查看端（整体）会话也 401（管理员专属）
        cv = self._client()
        cv.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        self.assertEqual(cv.get("/api/version").status_code, 401)

    def test_admin_gets_version(self):
        c = self._client()
        r = c.post("/admin/login", data={"account": "lushasha", "password": server.DEFAULT_PW})
        self.assertEqual(r.status_code, 303, r.text)
        d = c.get("/api/version").json()
        self.assertEqual(d["version"], V.PRODUCT_VERSION)
        self.assertEqual(d["stage"], V.PRODUCT_STAGE)
        self.assertIn(V.PRODUCT_STAGE, d["label"])
        self.assertTrue(d["changelog"] and d["changelog"][0]["items"])

    def test_console_has_version_ui(self):
        # 管理端：摘要卡 + 右侧日志抽屉（默认折叠）
        html = server.admin_ui_source()
        for anchor in ("verPill", "verCard", "loadVersion", "版本与更新", "verDrawer", "openVerDrawer", "更新日志"):
            self.assertIn(anchor, html, anchor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
