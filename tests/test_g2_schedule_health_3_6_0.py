# -*- coding: utf-8 -*-
"""3.6.0 G2：持久调度账本、补跑合并、四层健康。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestScheduleLedgerDurable(unittest.TestCase):
    def test_success_survives_reload(self):
        from schedule_ledger import get_slot, load_ledger, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-07-31", slot="09:30", status="success", build_id="b1")
        # 模拟重启：直接读盘
        row = get_slot(tmp, "2026-07-31", "09:30")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["status"], "success")
        led = load_ledger(tmp)
        self.assertIn("2026-07-31|09:30", led["slots"])

    def test_plan_catchup_only_latest(self):
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:30", "12:00", "17:00"]
        slots = {}
        run, coal = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run, "17:00")
        self.assertEqual(coal, ["09:30", "12:00"])

        # 最新已 success → 不补
        slots[slot_key("2026-07-31", "17:00")] = {"status": "success"}
        run2, coal2 = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertIsNone(run2)

    def test_cross_day_isolation(self):
        from schedule_ledger import day_summary, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-07-30", slot="09:30", status="success")
        summ = day_summary(tmp, "2026-07-31", ["09:30", "17:00"])
        self.assertEqual(summ["success"], [])
        self.assertIn("09:30", summ["pending"])


class TestHealthLayers(unittest.TestCase):
    def test_business_yellow_not_system(self):
        from health_layers import build_layered_health

        h = build_layered_health(
            system={"level": "ok"},
            business_completeness={"level": "yellow", "manual_missing_months": ["2026-01"]},
            viewer={"level": "ok", "numbers_safe": True},
        )
        self.assertEqual(h["system_health"]["level"], "ok")
        self.assertEqual(h["business_completeness"]["level"], "yellow")
        self.assertTrue(h["viewer_state"]["no_technical_yellow_banner"])
        self.assertFalse(h["viewer_state"]["blocking"])

    def test_critical_blocks_only_when_unsafe(self):
        from health_layers import build_layered_health, viewer_blocks_numbers

        self.assertTrue(viewer_blocks_numbers(level="critical", numbers_safe=False))
        self.assertFalse(viewer_blocks_numbers(level="yellow", numbers_safe=False))
        h = build_layered_health(
            viewer={"level": "critical", "numbers_safe": False},
        )
        self.assertTrue(h["viewer_state"]["blocking"])


if __name__ == "__main__":
    unittest.main()
