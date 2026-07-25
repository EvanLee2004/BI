# -*- coding: utf-8 -*-
"""2.6.4·B 本机告警：造告警 → unread +1 → ack → 0。零外发。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestAlertStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="alert264_"))
        self.cfg = {"data_dir": str(self.tmp)}
        (self.tmp / "日志").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_unread_ack(self):
        import alert_store

        s0 = alert_store.unread_summary(cfg=self.cfg, root=None)
        self.assertEqual(s0["unread_count"], 0)
        alert_store.append_alert("warning", "test", "单元测告警一条", cfg=self.cfg, root=None)
        s1 = alert_store.unread_summary(cfg=self.cfg, root=None)
        self.assertEqual(s1["unread_count"], 1)
        self.assertEqual(len(s1["recent"]), 1)
        self.assertIn("单元测", s1["recent"][0]["detail"])
        logp = alert_store.alert_log_path(self.cfg, None)
        self.assertTrue(logp.is_file())
        raw = logp.read_text(encoding="utf-8")
        self.assertIn("单元测告警一条", raw)
        alert_store.set_watermark(cfg=self.cfg, root=None)
        s2 = alert_store.unread_summary(cfg=self.cfg, root=None)
        self.assertEqual(s2["unread_count"], 0)
        # 新告警再出现
        alert_store.append_alert("error", "test", "第二条", cfg=self.cfg, root=None)
        s3 = alert_store.unread_summary(cfg=self.cfg, root=None)
        self.assertEqual(s3["unread_count"], 1)

    def test_notify_writes_store(self):
        import notify

        notify.maybe_alert_text(self.cfg, "来自 notify 的告警")
        import alert_store

        u = alert_store.unread_alerts(cfg=self.cfg, root=None)
        self.assertTrue(any("notify" in (x.get("detail") or "") or "告警" in (x.get("detail") or "") for x in u))


if __name__ == "__main__":
    unittest.main()
