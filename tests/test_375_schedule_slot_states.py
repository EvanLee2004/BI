# -*- coding: utf-8 -*-
"""3.7.5 G2：调度槽状态 — 未到点=待执行，已到未成=待补，跨日=漏跑；手动不伪造定时成功。

健康文案走 shipped health_messages_from_schedule；
手动刷新走 start_refresh_async(trigger=manual) 真入口。
"""

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
        """驱动 start_refresh_async(trigger=manual)：成功后定时槽仍无 schedule success。"""
        import schedule_ledger as sl_disk
        import server
        from refresh_pipeline import start_refresh_async
        from schedule_ledger import day_summary, get_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        planned = ["09:30", "12:00"]
        # 磁盘无任何定时 success
        summ0 = day_summary(tmp, "2026-08-02", planned, now_hhmm="10:00")
        self.assertIn("09:30", summ0["pending"])
        self.assertEqual(summ0["success"], [])

        done = {"ok": None}

        def on_complete(success: bool):
            done["ok"] = success

        orig = getattr(server, "_do_full", None)
        server._do_full = lambda c, r, trigger: {"result": "绿", "trigger": trigger}
        try:
            started = start_refresh_async(
                cfg, tmp, trigger="manual", on_complete=on_complete
            )
            self.assertTrue(started, "manual start_refresh_async 应取得锁并启动")
            # 等管道结束
            for _ in range(100):
                if done["ok"] is not None:
                    break
                _time.sleep(0.02)
            self.assertTrue(done["ok"] is True, f"manual 管道应成功 done={done}")
        finally:
            if orig is not None:
                server._do_full = orig
            else:
                try:
                    delattr(server, "_do_full")
                except Exception:
                    pass

        # 手动成功不得写定时槽 success
        self.assertIsNone(get_slot(tmp, "2026-08-02", "09:30"))
        self.assertIsNone(get_slot(tmp, "2026-08-02", "12:00"))
        led = sl_disk.load_ledger(tmp)
        for k, row in (led.get("slots") or {}).items():
            if str((row or {}).get("trigger") or "") == "schedule":
                self.fail(f"manual 路径不应写入 schedule 槽: {k}={row}")
        summ1 = day_summary(tmp, "2026-08-02", planned, now_hhmm="10:00")
        self.assertEqual(summ1["success"], [])
        self.assertIn("09:30", summ1["pending"])

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
        with sl._LEDGER_LOCK:
            pend = list(sl._SCHEDULE_LEDGER.get("pending") or [])
        self.assertNotIn("12:00", pend)
        self.assertNotIn("17:00", pend)
        row = get_slot(tmp, "2026-08-02", "09:30")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["status"], "success")
        led = sl.schedule_ledger(cfg, tmp)
        self.assertNotIn("12:00", led.get("pending") or [])
        self.assertNotIn("17:00", led.get("pending") or [])
        self.assertIn("12:00", led.get("upcoming") or [])


class TestHealthScheduleMessages375(unittest.TestCase):
    def test_health_messages_from_schedule_shipped(self):
        """驱动 shipped health_messages_from_schedule：upcoming 不产生漏跑文案、不抬黄。"""
        from schedule_loop import health_messages_from_schedule

        msgs, yellow = health_messages_from_schedule(
            {
                "upcoming": ["12:00", "17:00"],
                "pending": [],
                "missed": [],
                "failed": [],
            }
        )
        blob = " ".join(msgs)
        self.assertEqual(msgs, [])
        self.assertFalse(yellow)
        self.assertNotIn("漏跑", blob)
        self.assertNotIn("12:00", blob)
        self.assertNotIn("17:00", blob)

        # 已过点 pending → 待补，不称漏跑
        msgs2, yellow2 = health_messages_from_schedule(
            {
                "upcoming": ["17:00"],
                "pending": ["12:00"],
                "missed": [],
                "failed": [],
            }
        )
        self.assertTrue(any("待补" in m and "12:00" in m for m in msgs2))
        self.assertFalse(any("漏跑" in m for m in msgs2))
        self.assertFalse(yellow2)  # 待补不抬黄（与 data_api 一致：仅 miss/failed 抬黄）

        # 3.7.19：跨日 missed → 不进 reasons、不抬黄（假漏跑污染已下线）
        msgs3, yellow3 = health_messages_from_schedule(
            {
                "upcoming": ["12:00"],
                "pending": [],
                "missed": ["17:00"],
                "missed_date": "2026-08-01",
                "failed": [],
            }
        )
        blob3 = " ".join(msgs3)
        self.assertNotIn("漏跑", blob3)
        self.assertNotIn("17:00", blob3)
        self.assertFalse(yellow3)

    def test_data_api_health_uses_shipped_helper(self):
        """源码契约：api_health 调用 health_messages_from_schedule，不内联重写过滤。"""
        src = (
            Path(__file__).resolve().parents[1] / "src" / "routes" / "data_api.py"
        ).read_text(encoding="utf-8")
        self.assertIn("health_messages_from_schedule", src)
        self.assertIn("schedule_ledger", src)


if __name__ == "__main__":
    unittest.main()
