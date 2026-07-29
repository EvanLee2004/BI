#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G3 · 2.7.8：导出 HTML 与 PNG 同源 kanban_snapshot pack；PNG 路由禁 render/assemble_export_html。"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402
from support import fake_bu_page, fake_main_frags, fake_views  # noqa: E402


def _write_bucfg(cfg, root, bus):
    import bu as bu_mod
    import json

    p = bu_mod.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


def _write_accts(cfg, root, rows):
    accounts.save_accounts(cfg, root, rows)


def _std_accts():
    return [
        {
            "账号": accounts.MASTER_ACCOUNT,
            "显示名": "管",
            "权限": accounts.PERM_ADMIN,
            "密码": accounts.DEFAULT_ADMIN_PW,
        },
        {
            "账号": "overall",
            "显示名": "整",
            "权限": "整体",
            "密码": accounts.DEFAULT_VIEW_PW,
        },
        {
            "账号": "user_a",
            "显示名": "甲",
            "权限": "BU甲",
            "密码": accounts.DEFAULT_VIEW_PW,
        },
    ]


class TestG3PngSourceZeroOldPath(unittest.TestCase):
    """源码：PNG 路由不得再走 assemble_export_html / render_* 整页。"""

    def test_export_py_png_routes_no_old_builders(self):
        src = (ROOT / "src" / "routes" / "export.py").read_text(encoding="utf-8")
        # 整文件不得 import 旧 PNG 路径依赖（HTML 路径用 export_html）
        self.assertNotIn("from refresh_pipeline import assemble_export_html", src)
        self.assertNotIn("assemble_export_html(", src)
        self.assertNotIn("render_dashboard", src)
        self.assertNotIn("render_bu_page", src)
        self.assertNotIn("page.get(\"html\")", src)
        # 必须走 snapshot 标记
        self.assertIn("kanban_snapshot", src)
        self.assertIn("assemble_export_pack", src)
        self.assertIn("build_export_html", src)


class TestG3ExportSamePackHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.cfg = loaders.load_config()
        _write_bucfg(
            cls.cfg,
            cls.tmp,
            [
                {"name": "BU甲", "销售": ["销售A"]},
                {"name": "BU乙", "销售": ["销售B"]},
            ],
        )
        _write_accts(cls.cfg, cls.tmp, _std_accts())
        server._state["fragments"] = fake_main_frags("USER-MAIN")
        server._state["views"] = fake_views("USER-MAIN")
        server._state["summary"] = {
            "periods": {"2026年": {}, "2026年3月": {}},
            "meta": {"year_key": "2026年"},
            "trend": [],
            "receipt_order_monthly": [],
        }
        server._state["has_data"] = True
        server._state["built_at"] = "2026-07-29 00:00:00"
        server._state["bu_pages"] = {
            "BU甲": fake_bu_page("BU甲", "PAGE-A"),
            "BU乙": fake_bu_page("BU乙", "PAGE-B"),
        }
        for _name, page in server._state["bu_pages"].items():
            if isinstance(page, dict) and not page.get("summary"):
                page["summary"] = {
                    "periods": {"2026年": {}},
                    "meta": {"year_key": "2026年"},
                    "trend": [],
                    "receipt_order_monthly": [],
                }
        server._state["admin_html"] = "ready"
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls._prev_offline = os.environ.get("KANBAN_OFFLINE")
        os.environ["KANBAN_OFFLINE"] = "1"

    @classmethod
    def tearDownClass(cls):
        if cls._prev_offline is None:
            os.environ.pop("KANBAN_OFFLINE", None)
        else:
            os.environ["KANBAN_OFFLINE"] = cls._prev_offline

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _login_overall(self):
        c = self._client()
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        return c

    def test_html_and_png_source_share_kanban_snapshot(self):
        """同一会话：export.html 含快照；export.png 截图输入 HTML 也必须含同源快照标记。"""
        captured: list[str] = []

        def _fake_shot(html, blk="", width=1440):
            captured.append(html if isinstance(html, str) else html.decode("utf-8", "replace"))
            return b"\x89PNG\r\n\x1a\nG3FAKE"

        orig = server._screenshot_png
        server._screenshot_png = _fake_shot
        try:
            c = self._login_overall()
            rh = c.get("/api/v1/export.html", params={"blk": "2026年"})
            self.assertEqual(rh.status_code, 200, rh.text[:400])
            html_body = rh.text
            self.assertIn("kanban_snapshot", html_body)
            self.assertIn("__KANBAN_SNAPSHOT__", html_body)
            self.assertNotIn('data-export-fallback="1"', html_body)

            rp = c.get("/api/v1/export.png", params={"blk": "2026年"})
            self.assertEqual(rp.status_code, 200, rp.text[:400] if rp.headers.get("content-type", "").startswith("text") else rp.content[:80])
            self.assertEqual(rp.headers.get("content-type"), "image/png")
            self.assertEqual(1, len(captured), "PNG 应截一次图")
            png_html = captured[0]
            self.assertIn("kanban_snapshot", png_html)
            self.assertIn("__KANBAN_SNAPSHOT__", png_html)
            self.assertNotIn('data-export-fallback="1"', png_html)
            # 同源：均含 schema 标记
            self.assertIn('data-export-scheme="A"', html_body)
            self.assertIn('data-export-scheme="A"', png_html)
            # pack kind 一致
            mh = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", html_body)
            mp = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", png_html)
            self.assertIsNotNone(mh)
            self.assertIsNotNone(mp)
            import json

            ph, pp = json.loads(mh.group(1)), json.loads(mp.group(1))
            self.assertEqual(ph.get("kind"), "kanban_snapshot")
            self.assertEqual(pp.get("kind"), "kanban_snapshot")
            self.assertEqual(ph.get("scope"), pp.get("scope"))
            self.assertEqual(ph.get("default_period") or "2026年", pp.get("default_period") or "2026年")
        finally:
            server._screenshot_png = orig

    def test_bu_png_source_is_snapshot_not_render_page(self):
        captured: list[str] = []

        def _fake_shot(html, blk="", width=1440):
            captured.append(html if isinstance(html, str) else str(html))
            return b"\x89PNG\r\n\x1a\nG3BU"

        orig = server._screenshot_png
        server._screenshot_png = _fake_shot
        try:
            c = self._client()
            c.post("/login", data={"account": "user_a", "password": server.DEFAULT_VIEW_PW})
            r = c.get(f"/api/v1/export/bu/{quote('BU甲')}/png", params={"blk": "2026年"})
            self.assertEqual(r.status_code, 200, getattr(r, "text", "")[:300])
            self.assertEqual(1, len(captured))
            h = captured[0]
            self.assertIn("kanban_snapshot", h)
            self.assertIn("__KANBAN_SNAPSHOT__", h)
            m = re.search(r"window\.__KANBAN_SNAPSHOT__ = (\{.*\});\s*</script>", h)
            self.assertIsNotNone(m)
            import json

            pack = json.loads(m.group(1))
            self.assertEqual(pack.get("scope"), "BU")
            self.assertEqual(list((pack.get("bu") or {}).keys()), ["BU甲"])
            # 旧 render 整页常见字样不应作为装配主路径（snapshot 播放器可有其它文案）
            self.assertNotIn("data-assembled=\"1\"", h)
        finally:
            server._screenshot_png = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
