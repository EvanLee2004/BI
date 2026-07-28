#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B shipped HTTP（2.7.7：fragments 404；strip 工具与 publish 缓存守卫）
必须清空全部 client 卡字段，并带 views（cfg 参与）。

禁止只测 api_v1.cockpit_fragments(client=True) 绕过 server 缓存分支。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts
import bu
import loaders
import server
import render
import api_v1
import core
import assets  # noqa: E402

_CLIENT_FIELDS = api_v1._CLIENT_ASSEMBLE_FIELDS


def _write_bucfg(cfg, root, bus):
    p = bu.config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")


class TestHttpShippedFragments(unittest.TestCase):
    """模拟 publish 后的生产状态：_state 含 Python 全量预拼 fragments。"""

    @classmethod
    def setUpClass(cls):
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "_golden_data"
        cfg["db_path"] = "看板.db"
        cfg["zhiyun_auto_fetch"] = False
        cfg["show_delivered_unpaid"] = False
        cls.golden_cfg = cfg
        cls.summary, cls.html, _, _ = core.generate(cfg, date(2026, 6, 30), trigger="http-shipped")
        cls.logo = assets.load_logo_base64(cfg) or ""
        # 满血 Python 预拼（publish 会缓存这个）
        cls.fr_full = render.build_dashboard_fragments(cls.summary, cfg, cls.logo)
        # 确认预拼非空
        assert cls.fr_full.get("kpi_views"), "golden fragments missing kpi_views"
        assert cls.fr_full.get("rank_views"), "golden fragments missing rank_views"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = dict(self.golden_cfg)
        _write_bucfg(self.cfg, self.tmp, [{"name": "BU甲", "销售": ["销售A"]}])
        accounts.save_accounts(
            self.cfg,
            self.tmp,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": server.DEFAULT_PW},
                {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": server.DEFAULT_VIEW_PW},
            ],
        )
        # 模拟 publish 后：缓存满血预拼 HTML
        server._state["summary"] = self.summary
        server._state["fragments"] = dict(self.fr_full)
        server._state["views"] = None  # 逼 HTTP 分支 rebuild views with cfg
        server._state["user_html"] = self.html
        server._state["bu_pages"] = {}
        server._state["admin_html"] = "ready"
        self.app = server.create_app(self.cfg, root=self.tmp)

    def _login_overall(self):
        from fastapi.testclient import TestClient

        c = TestClient(self.app, follow_redirects=False)
        c.post("/login", data={"account": "overall", "password": server.DEFAULT_VIEW_PW})
        return c

    def test_http_cache_path_strips_all_client_fields(self):
        """2.7.7：fragments API 404；状态可仍有历史键但不得再 HTTP 下发。"""
        c = self._login_overall()
        r = c.get("/api/v1/cockpit/fragments")
        self.assertEqual(r.status_code, 404, r.text[:200])
        r2 = c.get("/api/v1/vm/cockpit")
        self.assertEqual(r2.status_code, 200, r2.text[:300])
        self.assertIn("kpi", r2.json())

    def test_http_views_built_with_cfg(self):
        c = self._login_overall()
        self.assertEqual(c.get("/api/v1/cockpit/fragments").status_code, 404)
        r = c.get("/api/v1/vm/cockpit")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        yk = self.summary["meta"]["year_key"]
        cards = (body.get("kpi") or {}).get("cards_by_period") or {}
        self.assertIn(yk, cards)

    def test_client_strip_helper_clears_all(self):
        dirty = {f: f"X-{f}" for f in _CLIENT_FIELDS}
        dirty["title"] = "keep"
        clean = api_v1.client_strip_fragments(dirty)
        self.assertEqual(clean["title"], "keep")
        for f in _CLIENT_FIELDS:
            self.assertEqual(clean[f], "")

    def test_publish_then_http_strip(self):
        """publish 可写入任意 fragments 键；HTTP fragments 仍 404。"""
        import refresh_pipeline

        refresh_pipeline.set_admin_page_builder(lambda h, s, c: "ready")
        fr_full = dict(self.fr_full)
        refresh_pipeline.publish(self.cfg, self.summary, self.html, bu_pages={}, fragments=fr_full)
        c = self._login_overall()
        self.assertEqual(c.get("/api/v1/cockpit/fragments").status_code, 404)
        self.assertEqual(c.get("/api/v1/vm/cockpit").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
