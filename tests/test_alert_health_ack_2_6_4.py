# -*- coding: utf-8 -*-
"""2.6.7 B-7：红条/ack 下线后，/api/v1/health 不再下发 alerts；告警仍写本地日志。

原 2.6.4 路径：造告警 → health unread → ack → 0。现改为：
- POST /api/alerts/ack 不存在（404）
- health 无 alerts 字段（或无未读横幅所需字段）
- alert_store.append 仍落盘
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

        cls.tmp = Path(tempfile.mkdtemp(prefix="alert_http_267_"))
        (cls.tmp / "日志").mkdir(parents=True)
        try:
            cfg_root = dict(loaders.load_config(ROOT))
            cfg_root["zhiyun_auto_fetch"] = False
            cfg_root["serve_static"] = False
            server.refresh(cfg_root, ROOT)
        except Exception as e:
            raise unittest.SkipTest(f"refresh failed: {e}") from e
        cls.app = server.create_app(cfg_root, root=ROOT)
        cls.client = TestClient(cls.app, follow_redirects=False)
        r = cls.client.post(
            "/api/v1/login",
            json={"account": "lushasha", "password": "kanban2026"},
        )
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

    def test_health_no_alerts_banner_and_ack_gone(self):
        import alert_store
        import loaders

        cfg = loaders.load_config(ROOT)
        alert_store.append_alert(
            "warning",
            "test_http",
            "B7_HTTP_告警探针_无金额",
            cfg=cfg,
            root=ROOT,
        )
        h = self.client.get("/api/v1/health")
        self.assertEqual(h.status_code, 200, h.text[:300])
        body = h.json()
        # 红条下线：health 不再承载未读计数
        self.assertNotIn("alerts", body, f"health must not expose alerts for banner: keys={list(body.keys())}")
        # ack 路由已删
        ack = self.client.post("/api/alerts/ack")
        self.assertEqual(ack.status_code, 404, ack.text[:200])
        # 本机告警库仍可统计未读（给运维/后续）；与 UI 解耦
        summary = alert_store.unread_summary(cfg=cfg, root=ROOT)
        self.assertGreaterEqual(int(summary.get("unread_count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
