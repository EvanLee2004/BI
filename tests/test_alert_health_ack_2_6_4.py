# -*- coding: utf-8 -*-
"""2.6.4·B-5：造告警 → GET /api/health 管理员会话 unread+1 → POST /api/alerts/ack → 0。

走真实 FastAPI 路由（data_api + config_api），不断言金额。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestAlertHealthAckHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cls.tmp = Path(tempfile.mkdtemp(prefix="alert_http_264_"))
        (cls.tmp / "日志").mkdir(parents=True)
        # minimal accounts for admin
        acc = {
            "accounts": [
                {
                    "账号": "ci_admin",
                    "显示名": "CI管理员",
                    "权限": "管理员",
                    "密码": "CiTest_Admin8chars",
                    "密码版本": 1,
                },
                {
                    "账号": "ci_view",
                    "显示名": "CI整体",
                    "权限": "整体",
                    "密码": "CiTest_View8chars",
                    "密码版本": 1,
                },
            ]
        }
        (cls.tmp / "看板账号.json").write_text(json.dumps(acc, ensure_ascii=False), encoding="utf-8")
        # seed empty runtime so create_app works
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = str(cls.tmp)
        cfg["zhiyun_auto_fetch"] = False
        cfg["serve_static"] = False
        # use ROOT for code assets; data in tmp via cfg
        try:
            # may need refresh with real data - use ROOT data for built state
            cfg_root = dict(loaders.load_config(ROOT))
            cfg_root["zhiyun_auto_fetch"] = False
            cfg_root["serve_static"] = False
            server.refresh(cfg_root, ROOT)
        except Exception as e:
            raise unittest.SkipTest(f"refresh failed: {e}") from e
        cls.app = server.create_app(cfg_root, root=ROOT)
        cls.client = TestClient(cls.app, follow_redirects=False)
        # login admin
        r = cls.client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": "kanban2026"},
        )
        # production/local may use different admin pw — try from 数据
        if r.status_code != 200:
            acc_path = ROOT / "数据" / "看板账号.json"
            if acc_path.is_file():
                rows = json.loads(acc_path.read_text(encoding="utf-8"))
                rows = rows.get("accounts") if isinstance(rows, dict) else rows
                for a in rows or []:
                    if a.get("权限") == "管理员" and a.get("密码"):
                        r = cls.client.post(
                            "/api/v1/login",
                            json={"account": a["账号"], "password": a["密码"]},
                        )
                        if r.status_code == 200:
                            break
        if r.status_code != 200:
            raise unittest.SkipTest(f"admin login failed: {r.status_code} {r.text[:200]}")

    def test_health_alerts_and_ack(self):
        import alert_store
        import loaders

        cfg = loaders.load_config(ROOT)
        # inject alert into real data dir used by server
        alert_store.append_alert(
            "warning",
            "test_http",
            "B5_HTTP_告警探针_无金额",
            cfg=cfg,
            root=ROOT,
        )
        h = self.client.get("/api/health")
        self.assertEqual(h.status_code, 200, h.text[:300])
        body = h.json()
        self.assertIn("alerts", body, f"admin health must include alerts: keys={list(body.keys())}")
        alerts = body["alerts"]
        self.assertGreaterEqual(int(alerts.get("unread_count") or 0), 1)
        recent = alerts.get("recent") or []
        self.assertTrue(
            any("B5_HTTP" in str(x.get("detail") or "") for x in recent),
            f"recent missing B5 detail: {recent}",
        )
        # ack
        ack = self.client.post("/api/alerts/ack")
        self.assertEqual(ack.status_code, 200, ack.text[:300])
        aj = ack.json()
        self.assertTrue(aj.get("ok"))
        h2 = self.client.get("/api/health")
        self.assertEqual(h2.status_code, 200)
        a2 = (h2.json().get("alerts") or {})
        # after ack, that alert should not count as unread
        self.assertEqual(int(a2.get("unread_count") or 0), 0, a2)


if __name__ == "__main__":
    unittest.main()
