#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.4.0 Stage D：管理端两轴分摊 API + UI 锚点 + 超额拒写。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import accounts  # noqa: E402
import bu  # noqa: E402
import db  # noqa: E402
import loaders  # noqa: E402
import server  # noqa: E402


class TestAllocPanelApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "数据").mkdir(exist_ok=True)
        cls.cfg = dict(loaders.load_config(ROOT))
        cls.cfg["data_dir"] = "数据"
        cls.cfg["db_path"] = "数据/看板.db"
        cls.cfg["zhiyun_auto_fetch"] = False
        bus = [
            {"name": "数据部", "销售": ["销售A"]},
            {"name": "游戏部", "销售": ["销售B"]},
        ]
        p = bu.config_path(cls.cfg, cls.tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"bus": bus}, ensure_ascii=False), encoding="utf-8")
        accounts.save_accounts(
            cls.cfg,
            cls.tmp,
            [
                {
                    "账号": "lushasha",
                    "显示名": "管理员",
                    "权限": "管理员",
                    "密码": server.DEFAULT_PW,
                },
            ],
        )
        conn = db.connect(cls.cfg, cls.tmp)
        conn.commit()
        conn.close()
        server._state["summary"] = {
            "meta": {"year_key": "2026年"},
            "periods": {},
        }
        server._state["has_data"] = True
        server._state["user_html"] = "ready"
        server._state["built_at"] = "test"
        cls.app = server.create_app(cls.cfg, root=cls.tmp)
        cls._prev = os.environ.get("KANBAN_OFFLINE")
        os.environ["KANBAN_OFFLINE"] = "1"

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("KANBAN_OFFLINE", None)
        else:
            os.environ["KANBAN_OFFLINE"] = cls._prev
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(self.app, follow_redirects=False)

    def _login_admin(self):
        c = self._client()
        r = c.post(
            "/login",
            data={"account": "lushasha", "password": server.DEFAULT_PW},
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (200, 302, 303), r.text[:300])
        return c

    def test_get_panel_has_details_and_defaults(self):
        c = self._login_admin()
        r = c.get("/api/alloc_ratios", params={"month": "2026-07"})
        self.assertEqual(r.status_code, 200, r.text[:400])
        d = r.json()
        self.assertIn("bus", d)
        self.assertIn("ratios", d)
        self.assertIn("details", d)
        self.assertIsInstance(d["details"], list)
        self.assertIn("by_bu_disp", d)
        self.assertIn("remain_company_disp", d)

    def test_save_ratio_fine_and_amount_fine_and_rent_override(self):
        c = self._login_admin()
        # 先写默认比例
        r0 = c.post(
            "/api/alloc_ratios",
            json={
                "归属月": "2026-07",
                "ratios": {"数据部": 20, "游戏部": 10},
            },
        )
        self.assertEqual(r0.status_code, 200, r0.text[:400])
        # 精配 1 项比例 + 1 项金额 + 房租手填
        body = {
            "归属月": "2026-07",
            "overrides": {"房租物业": 56.4},
            "detail_rules": {
                "打印费": {"mode": "比例", "values": {"数据部": 80, "游戏部": 20}},
                "装修费": {"mode": "金额", "values": {"数据部": 5.0, "游戏部": 3.0}},
                "房租物业": {"mode": "比例", "values": {"数据部": 50, "游戏部": 30}},
            },
        }
        r = c.post("/api/alloc_ratios", json=body)
        self.assertEqual(r.status_code, 200, r.text[:500])
        d = r.json()
        self.assertEqual(d.get("status"), "ok")
        cats = {x["category"]: x for x in d.get("details") or []}
        # 房租物业 应在 details 且 source=override
        self.assertIn("房租物业", cats)
        self.assertEqual(cats["房租物业"].get("amount_source"), "override")
        self.assertAlmostEqual(float(cats["房租物业"]["amount_yuan"]), 56.4, places=2)
        # 读库
        conn = db.connect(self.cfg, self.tmp)
        try:
            ov = db.get_public_detail_amount_overrides(conn, "2026-07")
            self.assertEqual(ov.get("房租物业"), 5640)
            rules = db.get_alloc_detail_rules(conn, "2026-07")
            self.assertEqual(rules["打印费"]["数据部"]["mode"], "比例")
            self.assertEqual(rules["打印费"]["数据部"]["value"], 80.0)
            self.assertEqual(rules["装修费"]["数据部"]["mode"], "金额")
            self.assertAlmostEqual(rules["装修费"]["数据部"]["value"], 5.0, places=2)
        finally:
            conn.close()

    def test_reject_over_ratio_and_over_amount(self):
        c = self._login_admin()
        r = c.post(
            "/api/alloc_ratios",
            json={
                "归属月": "2026-07",
                "detail_rules": {
                    "打印费": {
                        "mode": "比例",
                        "values": {"数据部": 80, "游戏部": 30},
                    }
                },
            },
        )
        self.assertEqual(r.status_code, 400, r.text[:300])
        # 金额超额：先设覆盖 10 元，再配 8+5
        c.post(
            "/api/alloc_ratios",
            json={"归属月": "2026-07", "overrides": {"装修费": 10.0}},
        )
        r2 = c.post(
            "/api/alloc_ratios",
            json={
                "归属月": "2026-07",
                "detail_rules": {
                    "装修费": {
                        "mode": "金额",
                        "values": {"数据部": 8.0, "游戏部": 5.0},
                    }
                },
            },
        )
        self.assertEqual(r2.status_code, 400, r2.text[:300])

    def test_ui_source_anchors(self):
        vue = (ROOT / "frontend/src/admin/views/ManualView.vue").read_text(encoding="utf-8")
        self.assertIn("公共费用统一分摊", vue)
        self.assertIn("alloc-detail-table", vue)
        self.assertIn("detail_rules", vue)
        self.assertIn("overrides", vue)
        self.assertIn("默认分摊比例", vue)
        self.assertIn("amount_editable", vue)


if __name__ == "__main__":
    unittest.main()
