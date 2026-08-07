#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内定时刷新循环（任务书60 / 2.6.3·B2）。

只在 server.serve() 启动一处 daemon 线程；禁止在 create_app / 请求路径启动。
到点调用既有 start_refresh_async(..., trigger="schedule")，不复制管道。

2.6.3·B2：
- 判据改为「今天这个时间点已过且今天还没成功跑过 → 补跑」（不再要求 hhmm 精确相等）
- start_refresh_async 返回 False 时排队重试不丢
- 跑批台账：当天计划几次/成功几次/漏哪次；/api/v1/health 可取 schedule_ledger()
- 3.7.19：漏跑不进体检黄、不发用户告警；每配置时点独立完整刷新
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import loaders
from settings_io import get_schedule_times

log = logging.getLogger("kanban.schedule_loop")

THREAD_NAME = "kanban-schedule-loop"

# 进程内跑批台账（供 /api/v1/health）
_LEDGER_LOCK = threading.Lock()
_SCHEDULE_LEDGER: dict = {
    "date": "",
    "planned": [],  # ["09:30", ...]
    "success": [],  # 成功触发的 hhmm
    "pending": [],  # 已过点待补跑
    "missed": [],  # 日终确认漏跑（跨日时写入）
    "last_tick": "",
    "last_fire": "",
    "last_busy": "",
}


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def health_messages_from_schedule(sched: dict | None) -> tuple[list[str], bool]:
    """从 schedule_ledger 快照生成 health run_reasons 片段。

    3.7.5：upcoming（待执行）永不进 reasons、不称漏跑、不抬黄。
    3.7.19：missed 漏跑**不**进 messages、**不**抬黄、不发用户告警；failed 可 info 不抬黄；
    pending 待补仍可 info、不抬黄。返回 (messages, yellow_nudge)。
    """
    sched = sched or {}
    pend = list(sched.get("pending") or [])
    up = list(sched.get("upcoming") or [])
    failed = list(sched.get("failed") or [])
    up_set = set(up)
    pend = [t for t in pend if t not in up_set]
    msgs: list[str] = []
    # 3.7.19：调度类不抬黄（漏跑假阳性曾长期污染体检）
    yellow = False
    if failed:
        msgs.append(f"定时刷新本次失败：{', '.join(failed)}")
    if pend:
        msgs.append(f"定时刷新待补：{', '.join(pend)}")
    # missed / upcoming 不入 reasons
    return msgs, yellow


def _resolve_now_hhmm(last_tick: str = "") -> str:
    """从 last_tick 或墙钟取 HH:MM。"""
    now_hhmm = ""
    lt = last_tick or ""
    if " " in str(lt):
        now_hhmm = str(lt).split()[-1][:5]
    if not now_hhmm or ":" not in now_hhmm:
        now_hhmm = time.strftime("%H:%M")
    return now_hhmm


def _split_past_future(slots: list[str], now_hhmm: str) -> tuple[list[str], list[str]]:
    """按 now 拆成已过点 / 未到点。解析失败的槽归入已过点侧（保守）。"""
    try:
        now_m = _hhmm_to_minutes(now_hhmm)
    except Exception:
        return list(slots or []), []
    past, future = [], []
    for t in slots or []:
        try:
            tmins = _hhmm_to_minutes(str(t))
        except Exception:
            past.append(t)
            continue
        if tmins <= now_m:
            past.append(t)
        else:
            future.append(t)
    return past, future


def _mem_ledger_snapshot() -> dict:
    with _LEDGER_LOCK:
        return {
            "date": _SCHEDULE_LEDGER.get("date") or "",
            "planned": list(_SCHEDULE_LEDGER.get("planned") or []),
            "success": list(_SCHEDULE_LEDGER.get("success") or []),
            "pending": list(_SCHEDULE_LEDGER.get("pending") or []),
            "missed": list(_SCHEDULE_LEDGER.get("missed") or []),
            "upcoming": list(_SCHEDULE_LEDGER.get("upcoming") or []),
            "last_tick": _SCHEDULE_LEDGER.get("last_tick") or "",
            "last_fire": _SCHEDULE_LEDGER.get("last_fire") or "",
            "last_busy": _SCHEDULE_LEDGER.get("last_busy") or "",
            "missed_date": _SCHEDULE_LEDGER.get("missed_date") or "",
        }


def _filter_mem_future_pending(mem: dict) -> dict:
    """无 cfg 时：pending 中未来槽挪到 upcoming。"""
    now_hhmm = _resolve_now_hhmm(str(mem.get("last_tick") or ""))
    past, future = _split_past_future(list(mem.get("pending") or []), now_hhmm)
    mem["pending"] = past
    if future:
        mem["upcoming"] = list(dict.fromkeys(list(mem.get("upcoming") or []) + future))
    return mem


def _merge_disk_day_summary(mem: dict, cfg, root) -> dict:
    """合并持久 day_summary；upcoming 永不进 missed。"""
    import schedule_ledger as _sl

    dd = loaders.data_dir(cfg, root)
    d = mem.get("date") or time.strftime("%Y-%m-%d")
    mem["date"] = d
    planned = list(mem.get("planned") or [])
    if not planned:
        try:
            planned = list(get_schedule_times(loaders.load_config()) or [])
            mem["planned"] = planned
        except Exception:
            planned = []
    now_hhmm = _resolve_now_hhmm(str(mem.get("last_tick") or ""))
    summ = _sl.day_summary(dd, d, planned, now_hhmm=now_hhmm)
    succ = list(dict.fromkeys(list(mem.get("success") or []) + list(summ.get("success") or [])))
    mem["success"] = succ
    mem["pending"] = list(summ.get("pending") or [])
    mem["upcoming"] = list(summ.get("upcoming") or [])
    mem["failed"] = list(summ.get("failed") or [])
    mem["coalesced"] = list(summ.get("coalesced") or [])
    up_set = set(mem["upcoming"])
    mem["missed"] = [t for t in (mem.get("missed") or []) if t not in up_set]
    mem["durable"] = True
    mem["now_hhmm"] = now_hhmm
    return mem


def schedule_ledger(cfg=None, root=None) -> dict:
    """只读副本：当天计划/成功/待补/待执行/漏跑。

    3.6.0：若 data_dir 有持久 schedule_ledger.json，合并 success 集合（重启后仍可见）。
    3.7.5：upcoming=未到点待执行，永不进 pending/missed；missed 仅跨日归入。
    """
    mem = _mem_ledger_snapshot()
    if cfg is None:
        return _filter_mem_future_pending(mem)
    try:
        return _merge_disk_day_summary(mem, cfg, root)
    except Exception:
        return mem


def _roll_ledger_to_date(date_iso: str, planned: list[str]) -> None:
    """跨日：重置今日集合。3.7.19 起不因「内存未记 success」发漏跑告警/抬黄。

    仍可在内存记 missed 供调试字段，但不调用 maybe_alert_text，health 亦不展示漏跑。
    """
    old_date = _SCHEDULE_LEDGER.get("date") or ""
    old_planned = list(_SCHEDULE_LEDGER.get("planned") or [])
    old_success = set(_SCHEDULE_LEDGER.get("success") or [])
    old_miss = [t for t in old_planned if t not in old_success]
    if old_date and old_miss:
        _SCHEDULE_LEDGER["missed"] = old_miss
        _SCHEDULE_LEDGER["missed_date"] = old_date
        log.info(
            "schedule_loop: day roll %s unfinished slots (no alert): %s",
            old_date,
            old_miss,
        )
    _SCHEDULE_LEDGER["date"] = date_iso
    _SCHEDULE_LEDGER["planned"] = list(planned or [])
    _SCHEDULE_LEDGER["success"] = []
    _SCHEDULE_LEDGER["pending"] = []
    _SCHEDULE_LEDGER["upcoming"] = []


def _write_pending_split(pending: list[str], last_tick: str | None) -> None:
    """写入 pending，未来槽剔到 upcoming。"""
    now_hhmm = _resolve_now_hhmm(
        str(last_tick or _SCHEDULE_LEDGER.get("last_tick") or "")
    )
    past, future = _split_past_future(list(pending or []), now_hhmm)
    _SCHEDULE_LEDGER["pending"] = past
    if future:
        _SCHEDULE_LEDGER["upcoming"] = list(
            dict.fromkeys(list(_SCHEDULE_LEDGER.get("upcoming") or []) + future)
        )


def _update_ledger(*, date_iso: str, planned: list[str], success_add: str | None = None,
                   pending: list[str] | None = None, missed: list[str] | None = None,
                   last_fire: str | None = None, last_busy: str | None = None,
                   last_tick: str | None = None) -> None:
    with _LEDGER_LOCK:
        if _SCHEDULE_LEDGER.get("date") != date_iso:
            _roll_ledger_to_date(date_iso, planned)
        else:
            _SCHEDULE_LEDGER["planned"] = list(planned or _SCHEDULE_LEDGER.get("planned") or [])
        if success_add and success_add not in _SCHEDULE_LEDGER["success"]:
            _SCHEDULE_LEDGER["success"] = list(_SCHEDULE_LEDGER["success"]) + [success_add]
        if pending is not None:
            _write_pending_split(pending, last_tick)
        if missed is not None:
            _SCHEDULE_LEDGER["missed"] = list(missed)
        if last_fire is not None:
            _SCHEDULE_LEDGER["last_fire"] = last_fire
        if last_busy is not None:
            _SCHEDULE_LEDGER["last_busy"] = last_busy
        if last_tick is not None:
            _SCHEDULE_LEDGER["last_tick"] = last_tick


class ScheduleLoop:
    """可单测的定时逻辑：假时钟 + mock start_refresh_async。

    3.6.0 小修：磁盘 schedule_ledger 为 SSOT；内存 fired 仅缓存今日 success。
    tick 经 plan_catchup 只补最新应跑槽，更早未满足写 skipped_coalesced。
    """

    def __init__(
        self,
        cfg,
        root,
        start_refresh_async_fn: Callable,
        *,
        clock=None,
        load_times_fn=None,
    ):
        self.cfg = cfg
        self.root = root
        self.start_refresh_async_fn = start_refresh_async_fn
        self.clock = clock or time.localtime
        self.load_times_fn = load_times_fn or (lambda: get_schedule_times(loaders.load_config()))
        # 成功触发去重键 (date_iso, hhmm) — 缓存；启动时从磁盘 hydrate
        self.fired: set[tuple[str, str]] = set()
        # 排队：start 返回 False 时保留，下 tick 重试（仅 hhmm 列表）
        self._queue: list[str] = []
        self._hydrate_fired_from_disk()

    def _data_dir(self):
        """解析 data_dir；cfg 缺键（旧单测 mock）→ None，调用方跳过磁盘。"""
        try:
            if not isinstance(self.cfg, dict) or "data_dir" not in self.cfg:
                return None
            return loaders.data_dir(self.cfg, self.root)
        except Exception:
            return None

    def _hydrate_fired_from_disk(self, date_iso: str | None = None) -> None:
        """从持久账本恢复今日 success → self.fired（重启后不重复补跑）。"""
        try:
            import schedule_ledger as _sl

            dd = self._data_dir()
            if dd is None:
                return
            now = self.clock()
            d = date_iso or time.strftime("%Y-%m-%d", now)
            led = _sl.load_ledger(dd)
            for _k, row in (led.get("slots") or {}).items():
                if not isinstance(row, dict):
                    continue
                if row.get("business_date") != d:
                    continue
                if row.get("status") != "success":
                    continue
                slot = str(row.get("slot") or "")
                if slot:
                    self.fired.add((d, slot))
        except Exception as e:
            log.warning("schedule_loop: hydrate fired from disk failed: %s", e)

    def tick(self) -> bool:  # noqa: C901  # 2.6.3·B2 补跑/排队/台账分支
        """执行一次检查。返回是否成功启动了刷新。

        3.7.19：磁盘账本 + plan_catchup —— 每点独立完整刷新；每次只启最早未 success 的 due 槽。
        """
        try:
            times = list(self.load_times_fn() or [])
        except Exception as e:
            log.warning("schedule_loop: load schedule_times failed: %s", e)
            return False
        now = self.clock()
        try:
            date_iso = time.strftime("%Y-%m-%d", now)
            hhmm = f"{int(now.tm_hour):02d}:{int(now.tm_min):02d}"
        except Exception:
            return False

        # 跨日：清空内存缓存后从磁盘重载（仅今日）
        self.fired = {(d, s) for (d, s) in self.fired if d == date_iso}
        self._hydrate_fired_from_disk(date_iso)

        _update_ledger(date_iso=date_iso, planned=times, last_tick=f"{date_iso} {hhmm}")

        import schedule_ledger as _sl

        dd = self._data_dir()
        slots_map: dict = {}
        if dd is not None:
            try:
                led = _sl.load_ledger(dd)
                slots_map = dict(led.get("slots") or {})
            except Exception as e:
                log.warning("schedule_loop: load ledger failed: %s", e)
        # 内存 fired 也合成 success 行，供 plan_catchup（无盘时）
        for _d, _s in self.fired:
            if _d == date_iso:
                k = _sl.slot_key(date_iso, _s)
                slots_map.setdefault(k, {"status": "success", "slot": _s, "business_date": date_iso})
        # plan_catchup：最早未完成 due；3.7.19 不再写 skipped_coalesced
        target, _coalesced = _sl.plan_catchup(
            business_date=date_iso,
            planned_slots=times,
            now_hhmm=hhmm,
            ledger_slots=slots_map,
        )

        # 失败重试：队列中的槽优先（且未 success）
        want: list[str] = []
        for t in list(self._queue):
            if t not in want and (date_iso, t) not in self.fired:
                want.append(t)
        if target and (date_iso, target) not in self.fired and target not in want:
            want.append(target)
        # 若 plan 无 target 但队列空 → 无事
        self._queue = list(want)
        _update_ledger(date_iso=date_iso, planned=times, pending=list(want))

        if not want:
            return False

        # 优先 plan_catchup 的最早未完成槽；否则队列最早
        if target and target in want:
            run_slot = target
        else:
            run_slot = sorted(want, key=_hhmm_to_minutes)[0]
        slot = run_slot
        d_iso = date_iso
        planned_times = times
        now_hhmm = hhmm

        if dd is not None:
            try:
                _sl.upsert_slot(
                    dd,
                    business_date=d_iso,
                    slot=slot,
                    status="running",
                    trigger="schedule",
                )
            except Exception as e:
                log.warning("schedule_ledger running write failed: %s", e)

        def _on_complete(
            success: bool,
            *,
            _slot=slot,
            _d=d_iso,
            _times=planned_times,
            _hhmm=now_hhmm,
        ) -> None:
            # 2.6.7 C-3：success 只在管道真成功后登记；失败当日回队列补跑
            if success:
                self.fired.add((_d, _slot))
                log.info(
                    "schedule_loop: pipeline OK trigger=schedule at %s %s (slot %s)",
                    _d,
                    _hhmm,
                    _slot,
                )
                _update_ledger(
                    date_iso=_d,
                    planned=_times,
                    success_add=_slot,
                    pending=list(self._queue),
                    last_fire=f"{_d} {_hhmm}→{_slot}",
                )
                try:
                    import schedule_ledger as _sl2

                    dd2 = self._data_dir()
                    if dd2 is not None:
                        _sl2.upsert_slot(
                            dd2,
                            business_date=_d,
                            slot=_slot,
                            status="success",
                            trigger="schedule",
                            build_id=f"{_d}T{_hhmm}",
                        )
                except Exception as e:
                    log.warning("schedule_ledger success write failed: %s", e)
            else:
                if _slot not in self._queue:
                    self._queue.append(_slot)
                log.warning(
                    "schedule_loop: pipeline FAIL slot %s on %s — re-queued for retry",
                    _slot,
                    _d,
                )
                _update_ledger(
                    date_iso=_d,
                    planned=_times,
                    pending=list(self._queue),
                    last_busy=f"{_d} {_hhmm} pipeline_fail {_slot}",
                )
                try:
                    import schedule_ledger as _sl2

                    dd2 = self._data_dir()
                    if dd2 is not None:
                        _sl2.upsert_slot(
                            dd2,
                            business_date=_d,
                            slot=_slot,
                            status="failed",
                            trigger="schedule",
                            error="pipeline_fail",
                        )
                except Exception as e:
                    log.warning("schedule_ledger fail write failed: %s", e)

        try:
            ok = self.start_refresh_async_fn(
                self.cfg, self.root, trigger="schedule", on_complete=_on_complete
            )
        except TypeError:
            # BE-011：无 on_complete 的旧签名禁止登记 success（生产入口必须带回调）
            try:
                ok = self.start_refresh_async_fn(self.cfg, self.root, trigger="schedule")
            except TypeError:
                try:
                    ok = self.start_refresh_async_fn(self.cfg, self.root, "schedule")
                except Exception as e:
                    log.warning("schedule_loop: start_refresh_async failed: %s", e)
                    return False
            else:
                if ok:
                    log.error(
                        "schedule_loop: start_refresh_async lacks on_complete; "
                        "refusing fake success (BE-011) — update caller to pass on_complete"
                    )
                    # 启动了但不记 success/fired；从队列移出防同 tick 连发，下一分钟 plan 可再补
            if not isinstance(ok, bool):
                return False
        except Exception as e:
            log.warning("schedule_loop: start_refresh_async failed: %s", e)
            return False

        if ok:
            # 线程已启动：先移出队列防连发；success/fired 等 on_complete
            self._queue = [t for t in self._queue if t != run_slot]
            log.info(
                "schedule_loop: started trigger=schedule at %s %s (slot %s)",
                date_iso,
                hhmm,
                run_slot,
            )
            _update_ledger(
                date_iso=date_iso,
                planned=times,
                pending=list(self._queue),
                last_fire=f"{date_iso} {hhmm} started→{run_slot}",
            )
            return True

        # 忙：保留队列，不登记 fired
        log.info(
            "schedule_loop: refresh busy, queued retry for %s %s (now %s)",
            date_iso,
            run_slot,
            hhmm,
        )
        _update_ledger(
            date_iso=date_iso,
            planned=times,
            pending=list(self._queue),
            last_busy=f"{date_iso} {hhmm} busy for {run_slot}",
        )
        return False


def start_schedule_loop(
    cfg,
    root,
    start_refresh_async_fn: Callable,
    *,
    poll_seconds: int = 20,
    clock=None,
) -> threading.Thread:
    """启动 daemon 定时循环。

    - cfg：服务进程持有的同一个 cfg 对象（与管理端路由闭包同源）；刷新时传此对象。
    - schedule_times：每 tick 热读 loaders.load_config()，管理端改时间无需重启。
    - 去重键 (date_iso, "HH:MM") 仅在 start_refresh_async_fn 返回 True 时登记；
      返回 False（锁占用）排队，下 tick 重试（2.6.3·B2）。
    """
    loop = ScheduleLoop(cfg, root, start_refresh_async_fn, clock=clock)
    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            loop.tick()
            stop.wait(poll_seconds)

    t = threading.Thread(target=_loop, name=THREAD_NAME, daemon=True)
    t._kanban_schedule_stop = stop  # type: ignore[attr-defined]
    t.start()
    try:
        times0 = get_schedule_times(loaders.load_config())
    except Exception:
        times0 = []
    print(f"[server] schedule_loop started times={times0} poll={poll_seconds}s")
    log.info("schedule_loop started times=%s poll=%ss", times0, poll_seconds)
    return t


def schedule_loop_thread_running() -> bool:
    """进程内是否有 schedule loop 工作线程（供测试断言 create_app 不启动）。"""
    for t in threading.enumerate():
        if t.name == THREAD_NAME and t.is_alive():
            return True
    return False
