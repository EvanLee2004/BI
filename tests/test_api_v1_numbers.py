#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第1步：API 数字与 golden/baseline_numbers.json 全等（假数据套装）。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GOLDEN = ROOT / "golden" / "baseline_numbers.json"
FAKE_DIR = ROOT / "_golden_data"


def _build_summary():
    import loaders, core, db, ingest, assets

    cfg = loaders.load_config(ROOT)
    cfg["data_dir"] = "_golden_data"
    cfg["zhiyun_auto_fetch"] = False
    cfg["period_pin"] = {"year": 2026, "month": 7}
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, ROOT)
    try:
        ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger="test_golden", archive_backups=False)
        summary = core.summary_from_conn(cfg, conn, today)
        try:
            core.attach_unassigned(cfg, conn, today, summary, ROOT)
        except Exception:
            pass
        try:
            core.attach_allocation_to_summary(cfg, conn, today, summary)
        except Exception:
            pass
        try:
            core.attach_bu_orders(cfg, conn, today, summary)
        except Exception:
            pass
    finally:
        conn.close()
    return summary


class TestGoldenNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLDEN.exists():
            raise unittest.SkipTest("缺少 golden/baseline_numbers.json，请先跑第0步")
        if not FAKE_DIR.exists() or not any(FAKE_DIR.glob("*.xlsx")):
            raise unittest.SkipTest("缺少 _golden_data 假数据，请从测试数据套装拷贝")
        cls.golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        cls.summary = _build_summary()

    def test_extract_numbers_deep_equal(self):
        import api_v1

        got = api_v1.extract_numbers(self.summary)
        # JSON 往返统一类型（tuple→list 等）
        got_j = json.loads(json.dumps(got, ensure_ascii=False, default=str))
        exp_j = json.loads(json.dumps(self.golden, ensure_ascii=False, default=str))
        self.assertEqual(got_j["meta_year"], exp_j["meta_year"])
        self.assertEqual(got_j["meta_year_key"], exp_j["meta_year_key"])
        self.assertEqual(got_j["period_keys"], exp_j["period_keys"])
        self.assertEqual(got_j["periods"], exp_j["periods"])
        self.assertEqual(got_j["trend"], exp_j["trend"])
        self.assertEqual(got_j["receipt_monthly"], exp_j["receipt_monthly"])
        self.assertEqual(got_j["receipt_order_monthly"], exp_j["receipt_order_monthly"])

    def test_cockpit_payload_has_numbers(self):
        import api_v1

        p = api_v1.cockpit_payload(self.summary)
        self.assertEqual(p["api_version"], "v1")
        self.assertIn("numbers", p)
        self.assertEqual(p["numbers"]["meta_year_key"], self.golden["meta_year_key"])


class TestCockpitHttp(unittest.TestCase):
    """HTTP 层：鉴权 + numbers 与 in-process summary 一致。"""

    @classmethod
    def setUpClass(cls):
        if not FAKE_DIR.exists():
            raise unittest.SkipTest("无 _golden_data")
        import tempfile
        from fastapi.testclient import TestClient
        import accounts, server, loaders, db, ingest, core

        cls.tmp = Path(tempfile.mkdtemp())
        # 复用仓库假数据目录（只读）— 通过 cfg data_dir 绝对路径不方便，改用 ROOT/_golden_data
        cfg = loaders.load_config(ROOT)
        cfg["data_dir"] = "_golden_data"
        cfg["zhiyun_auto_fetch"] = False
        cfg["period_pin"] = {"year": 2026, "month": 7}
        cfg["serve_spa"] = False
        # 账号写到真实 数据/ 会污染 — 用 env root
        # server create_app 的 root 用于账号；data 在 ROOT/_golden_data
        # loaders.data_dir(cfg, root) = root / data_dir if relative
        # 所以 root 必须是 ROOT，账号会读 数据/看板账号.json（本机已有）— 测试用临时 seed
        (ROOT / "数据").mkdir(exist_ok=True)
        accounts.save_accounts(
            cfg,
            ROOT,
            [
                {"账号": "lushasha", "显示名": "管理员", "权限": "管理员", "密码": "kanban2026"},
                {"账号": "overall", "显示名": "整体", "权限": "整体", "密码": "8888"},
                {"账号": "bu_only", "显示名": "BU", "权限": "BU", "可见BU": ["营销"], "密码": "8888"},
            ],
        )
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, ROOT)
        try:
            ingest.build_std_db(cfg, today.year, conn=conn, today=today, trigger="http_test", archive_backups=False)
            summary = core.summary_from_conn(cfg, conn, today)
        finally:
            conn.close()
        server._state["summary"] = summary
        server._state["built_at"] = "test"
        server._state["user_html"] = "<html>x</html>"
        server._state["admin_html"] = "<html>a</html>"
        server._state["bu_pages"] = {
            "营销": {"name": "营销", "html": "<html>bu</html>", "summary": summary},
        }
        cls.cfg = cfg
        cls.app = server.create_app(cfg, root=ROOT)
        cls.client = TestClient(cls.app, follow_redirects=False)
        cls.summary = summary

    def test_session_401(self):
        from fastapi.testclient import TestClient

        r = TestClient(self.app, follow_redirects=False).get("/api/v1/session")
        self.assertEqual(r.status_code, 401)

    def test_cockpit_numbers_match(self):
        import api_v1

        r = self.client.post("/api/v1/login", json={"account": "overall", "password": "8888"})
        self.assertEqual(r.status_code, 200, r.text)
        r2 = self.client.get("/api/v1/cockpit")
        self.assertEqual(r2.status_code, 200, r2.text)
        body = r2.json()
        exp = api_v1.extract_numbers(self.summary)
        got = body["numbers"]
        self.assertEqual(
            json.loads(json.dumps(got, default=str)),
            json.loads(json.dumps(exp, default=str)),
        )

    def test_bu_forbidden_main(self):
        from fastapi.testclient import TestClient

        c = TestClient(self.app, follow_redirects=False)
        self.assertEqual(c.post("/api/v1/login", json={"account": "bu_only", "password": "8888"}).status_code, 200)
        self.assertEqual(c.get("/api/v1/cockpit").status_code, 403)


if __name__ == "__main__":
    unittest.main()
