#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内定时刷新循环（任务书60 / 2.6.3·B2）。

只在 server.serve() 启动一处 daemon 线程；禁止在 create_app / 请求路径启动。
到点调用既有 start_refresh_async(..., trigger="schedule")，不复制管道。

2.6.3·B2：
- 判据改为「今天这个时间点已过且今天还没成功跑过 → 补跑」（不再要求 hhmm 精确相等）
- start_refresh_async 返回 False 时排队重试不丢
- 跑批台账：当天计划几次/成功几次/漏哪次；/api/health 可取 schedule_ledger()
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

# 进程内跑批台账（供 /api/health）
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


def schedule_ledger() -> dict:
    """只读副本：当天计划/成功/待补/漏跑。"""
    with _LEDGER_LOCK:
        return {
            "date": _SCHEDULE_LEDGER.get("date") or "",
            "planned": list(_SCHEDULE_LEDGER.get("planned") or []),
            "success": list(_SCHEDULE_LEDGER.get("success") or []),
            "pending": list(_SCHEDULE_LEDGER.get("pending") or []),
            "missed": list(_SCHEDULE_LEDGER.get("missed") or []),
            "last_tick": _SCHEDULE_LEDGER.get("last_tick") or "",
            "last_fire": _SCHEDULE_LEDGER.get("last_fire") or "",
            "last_busy": _SCHEDULE_LEDGER.get("last_busy") or "",
        }


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
    """可单测的定时逻辑：假时钟 + mock start_refresh_async。"""

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
        # 成功触发去重键 (date_iso, hhmm)
        self.fired: set[tuple[str, str]] = set()
        # 排队：start 返回 False 时保留，下 tick 重试（仅 hhmm 列表）
        self._queue: list[str] = []

    def tick(self) -> bool:  # noqa: C901  # 2.6.3·B2 补跑/排队/台账分支
        """执行一次检查。返回是否成功启动了刷新。

        2.6.3·B2：凡「计划点已过且今日未成功」一律尝试补跑（含精确分钟与之后）。
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
            now_mins = int(now.tm_hour) * 60 + int(now.tm_min)
        except Exception:
            return False

        _update_ledger(date_iso=date_iso, planned=times, last_tick=f"{date_iso} {hhmm}")

        # 今天已过点且未成功的计划点
        due: list[str] = []
        for t in times:
            try:
                if _hhmm_to_minutes(t) <= now_mins and (date_iso, t) not in self.fired:
                    due.append(t)
            except Exception:
                continue

        # 合并队列（保序去重）
        want: list[str] = []
        for t in list(self._queue) + due:
            if t not in want and (date_iso, t) not in self.fired:
                want.append(t)
        self._queue = list(want)
        _update_ledger(date_iso=date_iso, planned=times, pending=list(want))

        if not want:
            return False

        # 一次 tick 只尝试一个点（最早的），避免连打
        target = sorted(want, key=_hhmm_to_minutes)[0]
        try:
            ok = self.start_refresh_async_fn(self.cfg, self.root, trigger="schedule")
        except TypeError:
            try:
                ok = self.start_refresh_async_fn(self.cfg, self.root, "schedule")
            except Exception as e:
                log.warning("schedule_loop: start_refresh_async failed: %s", e)
                return False
        except Exception as e:
            log.warning("schedule_loop: start_refresh_async failed: %s", e)
            return False

        if ok:
            self.fired.add((date_iso, target))
            self._queue = [t for t in self._queue if t != target]
            log.info("schedule_loop: fired trigger=schedule at %s %s (target slot %s)", date_iso, hhmm, target)
            _update_ledger(
                date_iso=date_iso,
                planned=times,
                success_add=target,
                pending=list(self._queue),
                last_fire=f"{date_iso} {hhmm}→{target}",
            )
            return True

        # 忙：保留队列，不登记 fired
        log.info(
            "schedule_loop: refresh busy, queued retry for %s %s (now %s)",
            date_iso,
            target,
            hhmm,
        )
        _update_ledger(
            date_iso=date_iso,
            planned=times,
            pending=list(self._queue),
            last_busy=f"{date_iso} {hhmm} busy for {target}",
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
