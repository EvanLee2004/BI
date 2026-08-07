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

    def test_plan_catchup_earliest_unfinished(self):
        """3.7.19：多槽未完成时返回最早 due，不 coalesce 其余。"""
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:30", "12:00", "17:00"]
        slots = {}
        run, coal = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run, "09:30")
        self.assertEqual(coal, [])

        # 仅最早 success → 下一个未完成
        slots[slot_key("2026-07-31", "09:30")] = {"status": "success"}
        run2, coal2 = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run2, "12:00")
        self.assertEqual(coal2, [])

        # 全部 success → 不补
        for s in planned:
            slots[slot_key("2026-07-31", s)] = {"status": "success"}
        run3, coal3 = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertIsNone(run3)
        self.assertEqual(coal3, [])

    def test_early_success_does_not_coalesce_later_slots(self):
        """3.7.19：早槽 success 后晚间 due 仍要独立完整刷新。"""
        from schedule_ledger import plan_catchup, slot_key

        planned = ["09:30", "12:00", "17:00"]
        slots = {slot_key("2026-07-31", "09:30"): {"status": "success"}}
        run, coal = plan_catchup(
            business_date="2026-07-31",
            planned_slots=planned,
            now_hhmm="23:00",
            ledger_slots=slots,
        )
        self.assertEqual(run, "12:00")
        self.assertEqual(coal, [])

    def test_day_summary_future_not_pending(self):
        """已过点才 pending；未来 12:00/17:00 在 10:01 不算待补跑。"""
        from schedule_ledger import day_summary, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-07-31", slot="09:30", status="success")
        planned = ["09:30", "12:00", "17:00"]
        summ = day_summary(tmp, "2026-07-31", planned, now_hhmm="10:01")
        self.assertEqual(summ["success"], ["09:30"])
        self.assertEqual(summ["pending"], [])
        self.assertNotIn("12:00", summ["pending"])
        self.assertNotIn("17:00", summ["pending"])
        # 无 now → 兼容：全部未完成仍可进 pending（旧调用）
        summ2 = day_summary(tmp, "2026-07-31", planned)
        self.assertIn("12:00", summ2["pending"])

    def test_cross_day_isolation(self):
        from schedule_ledger import day_summary, upsert_slot

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        upsert_slot(tmp, business_date="2026-07-30", slot="09:30", status="success")
        summ = day_summary(tmp, "2026-07-31", ["09:30", "17:00"], now_hhmm="18:00")
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


class TestScheduleLoopWiresLedger(unittest.TestCase):
    """生产 ScheduleLoop 路径：每点独立完整刷新；success 槽不重跑。"""

    def test_multi_due_runs_earliest_then_next(self):
        """3.7.19：多 due 未完成时每 tick 跑最早槽；不写 skipped_coalesced。"""
        import time as _time
        from schedule_ledger import get_slot
        from schedule_loop import ScheduleLoop

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        calls: list = []

        def start_fn(*_a, **kw):
            calls.append(kw.get("on_complete") or _a)
            on_c = kw.get("on_complete")
            if on_c:
                on_c(True)
            return True

        def clock():
            return _time.strptime("2026-07-31 23:00", "%Y-%m-%d %H:%M")

        loop = ScheduleLoop(
            cfg,
            tmp,
            start_fn,
            clock=clock,
            load_times_fn=lambda: ["09:30", "12:00", "17:00"],
        )
        self.assertTrue(loop.tick())
        self.assertEqual(len(calls), 1)
        self.assertIn(("2026-07-31", "09:30"), loop.fired)
        c0930 = get_slot(tmp, "2026-07-31", "09:30")
        self.assertEqual((c0930 or {}).get("status"), "success")
        # 第二 tick 跑 12:00
        self.assertTrue(loop.tick())
        self.assertEqual(len(calls), 2)
        self.assertIn(("2026-07-31", "12:00"), loop.fired)
        c1200 = get_slot(tmp, "2026-07-31", "12:00")
        self.assertEqual((c1200 or {}).get("status"), "success")
        self.assertNotEqual((c1200 or {}).get("status"), "skipped_coalesced")
        # 第三 tick 跑 17:00
        self.assertTrue(loop.tick())
        self.assertIn(("2026-07-31", "17:00"), loop.fired)
        # 全部完成后不再启动
        n0 = len(calls)
        self.assertFalse(loop.tick())
        self.assertEqual(len(calls), n0)

    def test_restart_hydrates_success_skips_that_slot(self):
        """磁盘已 success 的槽 hydrate 后不重跑；未完成槽仍会补。"""
        import time as _time
        from schedule_ledger import upsert_slot
        from schedule_loop import ScheduleLoop

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        upsert_slot(tmp, business_date="2026-07-31", slot="09:30", status="success")
        upsert_slot(tmp, business_date="2026-07-31", slot="12:00", status="success")
        upsert_slot(tmp, business_date="2026-07-31", slot="17:00", status="success")

        calls: list = []

        def start_fn(*_a, **_k):
            calls.append(1)
            return True

        def clock():
            return _time.strptime("2026-07-31 23:00", "%Y-%m-%d %H:%M")

        loop = ScheduleLoop(
            cfg,
            tmp,
            start_fn,
            clock=clock,
            load_times_fn=lambda: ["09:30", "12:00", "17:00"],
        )
        self.assertIn(("2026-07-31", "09:30"), loop.fired)
        self.assertFalse(loop.tick())
        self.assertEqual(len(calls), 0)

    def test_schedule_ledger_requires_cfg_for_durable(self):
        from schedule_ledger import upsert_slot
        from schedule_loop import schedule_ledger

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        upsert_slot(tmp, business_date="2026-07-31", slot="09:30", status="success")
        mem_only = schedule_ledger()
        self.assertNotIn("durable", mem_only)
        # 有 cfg 才合并磁盘
        import schedule_loop as sl

        with sl._LEDGER_LOCK:
            sl._SCHEDULE_LEDGER["date"] = "2026-07-31"
            sl._SCHEDULE_LEDGER["planned"] = ["09:30"]
            sl._SCHEDULE_LEDGER["success"] = []
        merged = schedule_ledger(cfg, tmp)
        self.assertTrue(merged.get("durable"))
        self.assertIn("09:30", merged.get("success") or [])

    def test_schedule_ledger_future_slots_not_pending_after_morning_ok(self):
        """生产误黄复现：09:30 已成功 + last_tick=10:01 → 未来 12/17 不得进 pending。"""
        from schedule_ledger import upsert_slot
        from schedule_loop import schedule_ledger
        import schedule_loop as sl

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        cfg = {"data_dir": str(tmp), "db_path": "看板.db"}
        upsert_slot(tmp, business_date="2026-07-31", slot="09:30", status="success")
        with sl._LEDGER_LOCK:
            sl._SCHEDULE_LEDGER["date"] = "2026-07-31"
            sl._SCHEDULE_LEDGER["planned"] = ["09:30", "12:00", "17:00"]
            sl._SCHEDULE_LEDGER["success"] = ["09:30"]
            sl._SCHEDULE_LEDGER["pending"] = ["12:00", "17:00"]  # 旧内存脏
            sl._SCHEDULE_LEDGER["last_tick"] = "2026-07-31 10:01"
        out = schedule_ledger(cfg, tmp)
        self.assertTrue(out.get("durable"))
        self.assertIn("09:30", out.get("success") or [])
        self.assertEqual(out.get("pending") or [], [])


class TestHealthApiLayeredContract(unittest.TestCase):
    """health 路由源码接线 + build_layered_health 契约（非 re-implement）。"""

    def test_data_api_calls_build_layered_and_schedule_with_cfg(self):
        src = Path(__file__).resolve().parents[1] / "src" / "routes" / "data_api.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("build_layered_health", text)
        self.assertIn("schedule_ledger(cfg, root)", text)
        self.assertIn("viewer_state", text)


if __name__ == "__main__":
    unittest.main()
