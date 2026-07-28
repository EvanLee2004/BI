# -*- coding: utf-8 -*-
"""2.7.4 阶段调查：残留项结案状态的源码级守卫（非重实现业务）。

证明：
- 现网 VERSION 为 2.7.4
- 2.6.11 旧 P1/P2 结案标记仍在源码（勿当未修重开）
- UX-1 双口径仍编码存在（峰值 gross / 趋势 net）——产品债未关
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestStageInventory274Baseline(unittest.TestCase):
    def test_version_at_least_2_7_4(self):
        """2.7.4 调查基线之后 tip 只升不降；不再锁死等于 2.7.4。"""
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        parts = [int(x) for x in v.split(".")[:3]]
        while len(parts) < 3:
            parts.append(0)
        self.assertGreaterEqual(tuple(parts[:3]), (2, 7, 4), f"VERSION={v}")

    def test_password_policy_free_not_min8(self):
        """N01 superseded：2.6.12 非空即可，禁止再当『必须≥8』开单。"""
        src = (ROOT / "src" / "accounts.py").read_text(encoding="utf-8")
        self.assertIn("非空即可", src)
        self.assertNotIn("新密码至少 8 位", src)

    def test_ranking_f05_conservation_comment(self):
        """N03 fixed：F-05 分项去税再加总。"""
        src = (ROOT / "src" / "profit" / "tax_revenue.py").read_text(encoding="utf-8")
        self.assertIn("F-05", src)
        self.assertIn("分项去税再加总", src)

    def test_snapshot_requires_marker(self):
        """N04 fixed：仅 _SNAPSHOT_OK 算 exists。"""
        src = (ROOT / "src" / "ingest" / "archive.py").read_text(encoding="utf-8")
        self.assertIn("_SNAPSHOT_OK", src)
        self.assertIn("_month_snapshot_exists", src)

    def test_expense_ssot_int_path(self):
        """N06/F-07 主路径：build_period 走 expense_totals_from_man_led。"""
        src = (ROOT / "src" / "profit" / "budget_manual.py").read_text(encoding="utf-8")
        self.assertIn("expense_totals_from_man_led", src)

    def test_ux1_peak_gross_trend_net_still_split(self):
        """UX-1 仍开：KPI 交付金额=gross；trend 序列=net。"""
        widgets = (ROOT / "src" / "render_widgets.py").read_text(encoding="utf-8")
        summary = (ROOT / "src" / "profit" / "summary.py").read_text(encoding="utf-8")
        self.assertIn('("交付金额", "revenue_gross"', widgets)
        # trend tuple 含 revenue_net
        self.assertIn('P[k]["revenue_net"]', summary)
        self.assertIn("trend = [", summary)

    def test_maintenance_and_v1_health_shipped(self):
        self.assertTrue((ROOT / "src" / "maintenance_mode.py").is_file())
        self.assertTrue((ROOT / "static" / "maintenance.html").is_file())
        hc = (ROOT / "deploy" / "healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn("/api/v1/health", hc)
        self.assertIn("8018", hc)


if __name__ == "__main__":
    unittest.main()
