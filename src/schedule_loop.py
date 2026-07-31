#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内定时刷新循环（任务书60 / 2.6.3·B2）。

只在 server.serve() 启动一处 daemon 线程；禁止在 create_app / 请求路径启动。
到点调用既有 start_refresh_async(..., trigger="schedule")，不复制管道。

2.6.3·B2：
- 判据改为「今天这个时间点已过且今天还没成功跑过 → 补跑」（不再要求 hhmm 精确相等）
- start_refresh_async 返回 False 时排队重试不丢
- 跑批台账：当天计划几次/成功几次/漏哪次；/api/v1/health 可取 schedule_ledger()
- 漏跑 → 体检黄 + 告警
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


def schedule_ledger(cfg=None, root=None) -> dict:
    """只读副本：当天计划/成功/待补/漏跑。

    3.6.0：若 data_dir 有持久 schedule_ledger.json，合并 success 集合（重启后仍可见）。
    """
    with _LEDGER_LOCK:
        mem = {
            "date": _SCHEDULE_LEDGER.get("date") or "",
            "planned": list(_SCHEDULE_LEDGER.get("planned") or []),
            "success": list(_SCHEDULE_LEDGER.get("success") or []),
            "pending": list(_SCHEDULE_LEDGER.get("pending") or []),
            "missed": list(_SCHEDULE_LEDGER.get("missed") or []),
            "last_tick": _SCHEDULE_LEDGER.get("last_tick") or "",
            "last_fire": _SCHEDULE_LEDGER.get("last_fire") or "",
            "last_busy": _SCHEDULE_LEDGER.get("last_busy") or "",
        }
    if cfg is None:
        return mem
    try:
        import schedule_ledger as _sl

        dd = loaders.data_dir(cfg, root)
        d = mem.get("date") or ""
        if not d:
            # 无内存日：用本地今日，仍可读磁盘
            d = time.strftime("%Y-%m-%d")
            mem["date"] = d
        planned = list(mem.get("planned") or [])
        if not planned:
            try:
                planned = list(get_schedule_times(loaders.load_config()) or [])
                mem["planned"] = planned
            except Exception:
                planned = []
        summ = _sl.day_summary(dd, d, planned)
        # 并集 success（持久优先补内存空白）
        succ = list(dict.fromkeys(list(mem.get("success") or []) + list(summ.get("success") or [])))
        mem["success"] = succ
        mem["pending"] = list(summ.get("pending") or mem.get("pending") or [])
        mem["failed"] = list(summ.get("failed") or [])
        mem["coalesced"] = list(summ.get("coalesced") or [])
        mem["durable"] = True
    except Exception:
        pass
    return mem


def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _update_ledger(*, date_iso: str, planned: list[str], success_add: str | None = None,
                   pending: list[str] | None = None, missed: list[str] | None = None,
                   last_fire: str | None = None, last_busy: str | None = None,
                   last_tick: str | None = None) -> None:
    with _LEDGER_LOCK:
        if _SCHEDULE_LEDGER.get("date") != date_iso:
            # 跨日：把昨日未成功且已过点的记入 missed 并告警
            old_date = _SCHEDULE_LEDGER.get("date") or ""
            old_planned = list(_SCHEDULE_LEDGER.get("planned") or [])
            old_success = set(_SCHEDULE_LEDGER.get("success") or [])
            old_miss = [t for t in old_planned if t not in old_success]
            if old_date and old_miss:
                _SCHEDULE_LEDGER["missed"] = old_miss
                log.warning("schedule_loop: missed runs on %s: %s", old_date, old_miss)
                try:
                    from notify import maybe_alert_text

                    maybe_alert_text(
                        loaders.load_config(strict=False),
                        f"【经营看板告警】定时刷新漏跑 {old_date}：{', '.join(old_miss)}",
                    )
                except Exception:
                    pass
            _SCHEDULE_LEDGER["date"] = date_iso
            _SCHEDULE_LEDGER["planned"] = list(planned or [])
            _SCHEDULE_LEDGER["success"] = []
            _SCHEDULE_LEDGER["pending"] = []
            # missed 保留昨日记录供 health 展示至新日有成功前
        else:
            _SCHEDULE_LEDGER["planned"] = list(planned or _SCHEDULE_LEDGER.get("planned") or [])
        if success_add and success_add not in _SCHEDULE_LEDGER["success"]:
            _SCHEDULE_LEDGER["success"] = list(_SCHEDULE_LEDGER["success"]) + [success_add]
        if pending is not None:
            _SCHEDULE_LEDGER["pending"] = list(pending)
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

        3.6.0：磁盘账本 + plan_catchup —— 只补最新应跑槽；更早槽 coalesced。
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
        # plan_catchup：只补最新 due；更早未成功 → coalesced
        target, coalesced = _sl.plan_catchup(
            business_date=date_iso,
            planned_slots=times,
            now_hhmm=hhmm,
            ledger_slots=slots_map,
        )
        for cslot in coalesced:
            if (date_iso, cslot) in self.fired:
                continue
            st = (slots_map.get(_sl.slot_key(date_iso, cslot)) or {}).get("status")
            if st == "success":
                continue
            if dd is None:
                continue
            try:
                _sl.upsert_slot(
                    dd,
                    business_date=date_iso,
                    slot=cslot,
                    status="skipped_coalesced",
                    trigger="schedule",
                )
            except Exception as e:
                log.warning("schedule_ledger coalesced write failed: %s", e)

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

        # 优先跑 plan_catchup 的最新槽；否则队列最早
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
            # 兼容旧签名 mock：无 on_complete 时启动即成功（单测）
            try:
                ok = self.start_refresh_async_fn(self.cfg, self.root, trigger="schedule")
            except TypeError:
                try:
                    ok = self.start_refresh_async_fn(self.cfg, self.root, "schedule")
                except Exception as e:
                    log.warning("schedule_loop: start_refresh_async failed: %s", e)
                    return False
            else:
                # 旧 mock 返回 True 即视为管道成功
                if ok:
                    _on_complete(True)
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
