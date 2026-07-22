#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2.3.0 S6.B：/api/health metrics 不许恒 null；api_p95_ms 已删。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestHealthMetrics230(unittest.TestCase):
    def test_server_writes_metrics(self):
        src = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertIn('_state["metrics"]', src)
        self.assertIn("update_ms", src)
        self.assertIn("fetch_fail_rate", src)

    def test_health_no_permanent_null_api_p95(self):
        src = (ROOT / "src" / "routes" / "data_api.py").read_text(encoding="utf-8")
        # 不再返回恒 null 的 api_p95_ms
        self.assertNotIn('"api_p95_ms"', src)
        self.assertIn("m_out", src)

    def test_metrics_only_real_values_path(self):
        src = (ROOT / "src" / "routes" / "data_api.py").read_text(encoding="utf-8")
        self.assertIn('metrics.get("update_ms") is not None', src)


if __name__ == "__main__":
    unittest.main()
