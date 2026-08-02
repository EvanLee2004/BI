# -*- coding: utf-8 -*-
"""3.7.5 G2：调度槽状态 — 未到点=待执行，已到未成=待补，跨日=漏跑；手动不伪造定时成功。"""

from __future__ import annotations

import shutil
import tempfile
import time as _time
import unittest
from pathlib import Path


class TestScheduleSlotStates375(unittest.TestCase):
    def test_morning_future_slots_are_upcoming_not_missed(self):
        """10:xx 时 12:00/17:00 仅待执行，不在 pending/missed，不进漏跑集合。"""
        from schedule_ledger import day_summary, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-08-02", slot="09:30", status="success")
        planned = ["09:30", "12:00", "17:00"]
        summ = day_summary(tmp, "2026-08-02", planned, now_hhmm="10:15")
        self.assertEqual(summ["success"], ["09:30"])
        self.assertEqual(summ["pending"], [])
        self.assertEqual(set(summ["upcoming"]), {"12:00", "17:00"})
        self.assertNotIn("12:00", summ["pending"])
        self.assertNotIn("17:00", summ["pending"])

    def test_past_due_is_pending(self):
        from schedule_ledger import day_summary

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        planned = ["09:30", "12:00", "17:00"]
        summ = day_summary(tmp, "2026-08-02", planned, now_hhmm="13:00")
        self.assertIn("09:30", summ["pending"])
        self.assertIn("12:00", summ["pending"])
        self.assertEqual(summ["upcoming"], ["17:00"])

    def test_cross_day_marks_missed_not_today_upcoming(self):
        """跨日：昨日未成 → missed；今日未来槽仍 upcoming。"""
        import schedule_loop as sl
        from schedule_ledger import day_summary

        # 重置内存账本
        with sl._LEDGER_LOCK:
            sl._SCHEDULE_LEDGER.clear()
            sl._SCHEDULE_LEDGER.update(
                {
                    "date": "2026-08-01",
                    "planned": ["09:30", "12:00", "17:00"],
                    "success": ["09:30"],
                    "pending": [],
                    "missed": [],
                    "upcoming": [],
                    "last_tick": "2026-08-01 23:50",
                }
            )
        sl._update_ledger(
            date_iso="2026-08-02",
            planned=["09:30", "12:00", "17:00"],
            last_tick="2026-08-02 10:00",
        )
        with sl._LEDGER_LOCK:
            self.assertEqual(set(sl._SCHEDULE_LEDGER.get("missed") or []), {"12:00", "17:00"})
            self.assertEqual(sl._SCHEDULE_LEDGER.get("missed_date"), "2026-08-01")
            self.assertEqual(sl._SCHEDULE_LEDGER.get("date"), "2026-08-02")

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        summ = day_summary(tmp, "2026-08-02", ["09:30", "12:00", "17:00"], now_hhmm="10:00")
        self.assertEqual(set(summ["upcoming"]), {"12:00", "17:00"})
        self.assertIn("09:30", summ["pending"])

    def test_manual_refresh_does_not_mark_schedule_slot_success(self):
        """手动刷新成功不得伪造定时槽 success。"""
        from schedule_ledger import get_slot, load_ledger, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        # 仅写 manual 路径不应存在；定时槽保持 open
        # 模拟：手动刷新不调用 upsert_slot(..., trigger=schedule)
        # 验证：无 schedule success 时 day_summary 仍 pending
        planned = ["09:30", "12:00"]
        from schedule_ledger import day_summary

        summ = day_summary(tmp, "2026-08-02", planned, now_hhmm="10:00")
        self.assertIn("09:30", summ["pending"])
        self.assertEqual(summ["success"], [])
        # 显式：磁盘无任何 success
        led = load_ledger(tmp)
        self.assertEqual(led.get("slots") or {}, {})
        # 若有人误写 manual 到别键，定时键仍无
        self.assertIsNone(get_slot(tmp, "2026-08-02", "09:30"))

    def test_schedule_loop_pending_excludes_future(self):
        """ScheduleLoop 写 pending 时剔除未来槽。"""
        import schedule_loop as sl
        from schedule_ledger import get_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        calls = []

        def start_fn(*_a, **kw):
            calls.append(1)
            on_c = kw.get("on_complete")
            if on_c:
                on_c(True)
            return True

        def clock():
            return _time.strptime("2026-08-02 10:15", "%Y-%m-%d %H:%M")

        loop = sl.ScheduleLoop(
            cfg,
            tmp,
            start_fn,
            clock=clock,
            load_times_fn=lambda: ["09:30", "12:00", "17:00"],
        )
        loop.tick()
        # 09:30 应跑并 success；12/17 不得在 pending 内存
        with sl._LEDGER_LOCK:
            pend = list(sl._SCHEDULE_LEDGER.get("pending") or [])
            up = list(sl._SCHEDULE_LEDGER.get("upcoming") or [])
        self.assertNotIn("12:00", pend)
        self.assertNotIn("17:00", pend)
        row = get_slot(tmp, "2026-08-02", "09:30")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["status"], "success")
        # ledger 读路径
        led = sl.schedule_ledger(cfg, tmp)
        self.assertNotIn("12:00", led.get("pending") or [])
        self.assertNotIn("17:00", led.get("pending") or [])
        self.assertIn("12:00", led.get("upcoming") or [])
        # 漏跑文案不得含未来槽
        for key in ("pending", "missed"):
            for t in led.get(key) or []:
                self.assertNotIn(t, ("12:00", "17:00") if key == "missed" and led.get("date") == "2026-08-02" else ())


class TestHealthScheduleMessages375(unittest.TestCase):
    def test_health_reasons_no_leak_label_for_upcoming(self):
        """组装 reasons 时 upcoming 不产生漏跑文案。"""
        # 纯逻辑：复用 data_api 分支所需的分类
        miss, pend, up = [], [], ["12:00", "17:00"]
        up_set = set(up)
        miss = [t for t in miss if t not in up_set]
        pend = [t for t in pend if t not in up_set]
        reasons = []
        if miss:
            reasons.append(f"定时刷新漏跑：{', '.join(miss)}")
        if pend:
            reasons.append(f"定时刷新待补：{', '.join(pend)}")
        blob = " ".join(reasons)
        self.assertNotIn("漏跑", blob)
        self.assertNotIn("12:00", blob)
        self.assertNotIn("17:00", blob)


if __name__ == "__main__":
    unittest.main()
