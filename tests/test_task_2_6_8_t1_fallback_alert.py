# -*- coding: utf-8 -*-
"""2.6.8 T1：local_fallback 告警人话 + 禁止「体检红：红」+ business_gaps 台账降级字段。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestPipelineAlertHumanCopy(unittest.TestCase):
    def test_local_fallback_detail_has_source_and_date(self):
        import notify

        report = {
            "result": "红",
            "fetch": {
                "status": "local_fallback",
                "source": "收单台账",
                "local_as_of_cn": "7月23日 17:18",
                "data_as_of_cn": "7月21日",
                "detail": "收单台账共享盘不可达…",
            },
        }
        detail = notify.format_pipeline_alert_detail(report)
        self.assertIn("收单台账", detail)
        self.assertIn("7月23日", detail)
        self.assertIn("7月21日", detail)
        self.assertNotEqual(detail.strip(), "红")
        self.assertNotIn("体检红：红", detail)

    def test_fallback_never_bare_red(self):
        import notify

        # 空 report 仍结果红 → 兜底有字
        d = notify.format_pipeline_alert_detail({"result": "红"})
        self.assertTrue(len(d) > 2)
        self.assertNotEqual(d.strip(), "红")

    def test_maybe_alert_writes_human_text(self):
        import notify
        import alert_store

        tmp = Path(tempfile.mkdtemp())
        (tmp / "数据").mkdir()
        cfg = {"data_dir": "数据"}
        report = {
            "result": "红",
            "fetch": {
                "status": "local_fallback",
                "source": "收单台账",
                "local_as_of_cn": "7月23日 17:18",
                "data_as_of_cn": "7月21日",
            },
        }
        with patch.object(alert_store, "append_alert") as mock_app:
            notify.maybe_alert_pipeline(cfg, report, root=tmp)
            self.assertTrue(mock_app.called)
            args = mock_app.call_args[0]
            # level, category, message
            msg = args[2] if len(args) >= 3 else mock_app.call_args.kwargs.get("message") or ""
            if not msg and mock_app.call_args:
                # positional: append_alert(level, cat, text, ...)
                msg = mock_app.call_args[0][2]
            self.assertIn("体检红：", msg)
            self.assertNotEqual(msg, "体检红：红")
            self.assertIn("收单台账", msg)
            self.assertIn("7月23日", msg)

    def test_run_reasons_local_fallback_human(self):
        from audit_diff import _run_reasons

        reasons = _run_reasons(
            {
                "fetch": {
                    "status": "local_fallback",
                    "source": "收单台账",
                    "local_as_of_cn": "7月23日 17:18",
                    "data_as_of_cn": "7月21日",
                }
            }
        )
        self.assertTrue(any("本地副本" in r and "收单台账" in r for r in reasons), reasons)
        self.assertFalse(any(r.strip() == "红" for r in reasons))

    def test_banner_ledger_mentions_expense_data_end(self):
        import loaders
        import server

        tmp = Path(tempfile.mkdtemp())
        ddir = tmp / "数据"
        ddir.mkdir()
        led = ddir / "收单台账.xlsx"
        led.write_bytes(b"PK\x03\x04fake")
        cfg = dict(loaders.load_config(ROOT))
        cfg["data_dir"] = "数据"
        cfg["files"] = dict(cfg.get("files") or {})
        cfg["files"]["ledger"] = "收单台账.xlsx"
        b = server.build_fetch_fallback_banners(
            {
                "fetch": {
                    "status": "local_fallback",
                    "detail": "路径不存在",
                    "local_as_of_cn": "7月23日 17:18",
                    "data_as_of_cn": "7月21日",
                }
            },
            cfg,
            tmp,
        )
        texts = [x["text"] for x in b]
        self.assertTrue(any("费用" in t or "数据止于" in t for t in texts), texts)
        self.assertTrue(any("7月" in t for t in texts), texts)


class TestBusinessGapsLedgerFallback(unittest.TestCase):
    def test_health_business_gaps_ledger_fields_when_authed(self):
        import loaders
        import server
        from fastapi.testclient import TestClient

        cfg = dict(loaders.load_config(ROOT))
        cfg["zhiyun_auto_fetch"] = False
        app = server.create_app(cfg, root=ROOT)
        c = TestClient(app)
        rows = json.loads((ROOT / "数据" / "看板账号.json").read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("accounts") or []
        admin = next(a for a in rows if a.get("权限") == "管理员")
        lr = c.post("/api/v1/login", json={"account": admin["账号"], "password": admin["密码"]})
        self.assertIn(lr.status_code, (200, 303), lr.text[:200])
        r = c.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        g = r.json().get("business_gaps") or {}
        for k in (
            "ledger_fallback",
            "ledger_fallback_as_of",
            "ledger_fallback_data_end",
            "ledger_fallback_text",
            "ledger_fallback_owner",
        ):
            self.assertIn(k, g, g.keys())

    def test_admin_layout_has_ledger_fallback_ui(self):
        src = (ROOT / "frontend/src/admin/layout/AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn("health-gap-ledger-fallback", src)
        self.assertIn("ledger_fallback", src)
        self.assertIn("费用台账沿用本地副本", src)


if __name__ == "__main__":
    unittest.main()
