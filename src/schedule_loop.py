#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内定时刷新循环（任务书60）。

只在 server.serve() 启动一处 daemon 线程；禁止在 create_app / 请求路径启动。
到点调用既有 start_refresh_async(..., trigger="schedule")，不复制管道。
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
        self.fired: set[tuple[str, str]] = set()

    def tick(self) -> bool:
        """执行一次检查。返回是否成功启动了刷新（登记了去重键）。"""
        try:
            times = self.load_times_fn()
        except Exception as e:
            log.warning("schedule_loop: load schedule_times failed: %s", e)
            return False
        now = self.clock()
        try:
            date_iso = time.strftime("%Y-%m-%d", now)
            hhmm = f"{int(now.tm_hour):02d}:{int(now.tm_min):02d}"
        except Exception:
            return False
        if hhmm not in (times or []):
            return False
        key = (date_iso, hhmm)
        if key in self.fired:
            return False
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
            self.fired.add(key)
            log.info("schedule_loop: fired trigger=schedule at %s %s", date_iso, hhmm)
            return True
        log.info(
            "schedule_loop: refresh busy, will retry next tick (not registered) %s %s",
            date_iso,
            hhmm,
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
      返回 False（锁占用）不登记，下 tick 重试。
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
