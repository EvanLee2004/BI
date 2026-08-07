# -*- coding: utf-8 -*-
"""3.7.19：每配置时点独立完整刷新；漏跑不进 health 黄/文案。

驱动 shipped plan_catchup / health_messages_from_schedule / 跨日 roll。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestPlanCatchupPerSlot3719(unittest.TestCase):
    def test_early_success_still_runs_later_unfinished(self):
        """T1：早槽 success 后，晚间 due 未 success 的槽仍要 run（最早未完成）。"""
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:00", "12:00", "18:00"]
        slots = {slot_key("2026-08-07", "09:00"): {"status": "success"}}
        run, coal = plan_catchup(
            business_date="2026-08-07",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run, "12:00")
        self.assertEqual(coal, [])

    def test_no_records_picks_earliest_due(self):
        """T2：三槽皆无记录、now 已过全部 → 先返回最早槽，不 coal 前两个。"""
        from schedule_ledger import plan_catchup

        planned = ["09:00", "12:00", "18:00"]
        run, coal = plan_catchup(
            business_date="2026-08-07",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots={},
        )
        self.assertEqual(run, "09:00")
        self.assertEqual(coal, [])

    def test_all_success_no_run(self):
        """T3：三槽均 success → run is None。"""
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:00", "12:00", "18:00"]
        slots = {
            slot_key("2026-08-07", s): {"status": "success"} for s in planned
        }
        run, coal = plan_catchup(
            business_date="2026-08-07",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertIsNone(run)
        self.assertEqual(coal, [])

    def test_future_slots_not_run_or_coalesced(self):
        """T4：now=10:00 仅第一槽 due。"""
        from schedule_ledger import plan_catchup

        planned = ["09:00", "12:00", "18:00"]
        run, coal = plan_catchup(
            business_date="2026-08-07",
            planned_slots=planned,
            now_hhmm="10:00",
            ledger_slots={},
        )
        self.assertEqual(run, "09:00")
        self.assertEqual(coal, [])

    def test_historical_coalesced_counts_as_unfinished(self):
        """历史 skipped_coalesced 视为未完成，应安排真实 success 跑。"""
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:00", "12:00", "18:00"]
        slots = {
            slot_key("2026-08-07", "09:00"): {"status": "success"},
            slot_key("2026-08-07", "12:00"): {"status": "skipped_coalesced"},
        }
        run, coal = plan_catchup(
            business_date="2026-08-07",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run, "12:00")
        self.assertEqual(coal, [])


class TestHealthNoMissYellow3719(unittest.TestCase):
    def test_missed_only_no_leak_message_no_yellow(self):
        """T5：仅 missed → 不含漏跑、不抬黄。"""
        from schedule_loop import health_messages_from_schedule

        msgs, yellow = health_messages_from_schedule(
            {
                "missed": ["09:30", "12:00", "17:00"],
                "missed_date": "2026-08-06",
                "pending": [],
                "failed": [],
                "upcoming": [],
            }
        )
        blob = " ".join(msgs)
        self.assertNotIn("漏跑", blob)
        self.assertNotIn("定时刷新漏跑", blob)
        self.assertFalse(yellow)

    def test_cross_day_roll_no_miss_alert(self):
        """T6：跨日 roll 不发漏跑告警。"""
        import schedule_loop as sl

        with sl._LEDGER_LOCK:
            sl._SCHEDULE_LEDGER.clear()
            sl._SCHEDULE_LEDGER.update(
                {
                    "date": "2026-08-06",
                    "planned": ["09:30", "12:00", "17:00"],
                    "success": [],
                    "pending": [],
                    "missed": [],
                    "upcoming": [],
                    "last_tick": "2026-08-06 23:50",
                }
            )
        with mock.patch("schedule_loop.loaders.load_config", return_value={}):
            with mock.patch("notify.maybe_alert_text") as alert:
                sl._update_ledger(
                    date_iso="2026-08-07",
                    planned=["09:00", "12:00", "18:00"],
                    last_tick="2026-08-07 00:01",
                )
                alert.assert_not_called()

    def test_day_summary_noon_pending_after_morning_success(self):
        """T7：早 success 后中午未跑 → pending，非 coalesced-done。"""
        from schedule_ledger import day_summary, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-08-07", slot="09:00", status="success")
        planned = ["09:00", "12:00", "18:00"]
        summ = day_summary(tmp, "2026-08-07", planned, now_hhmm="14:00")
        self.assertEqual(summ["success"], ["09:00"])
        self.assertIn("12:00", summ["pending"])
        self.assertNotIn("12:00", summ["coalesced"])
        self.assertNotIn("12:00", summ["success"])


if __name__ == "__main__":
    unittest.main()
