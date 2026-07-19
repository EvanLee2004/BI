#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录防爆破（任务书43）：同账号连续失败 N 次锁 M 分钟。内存计数，进程重启清零。"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}  # account -> timestamps of failures


def _cfg_n(cfg: dict | None) -> tuple[int, float]:
    cfg = cfg or {}
    n = int(cfg.get("login_max_failures", 10) or 10)
    mins = float(cfg.get("login_lock_minutes", 5) or 5)
    return max(1, n), max(0.1, mins) * 60.0


def is_locked(account: str, cfg: dict | None = None, now: float | None = None) -> bool:
    account = (account or "").strip().lower()
    if not account:
        return False
    n, window = _cfg_n(cfg)
    now = time.time() if now is None else now
    with _lock:
        ts = _fails.get(account) or []
        ts = [t for t in ts if now - t < window]
        _fails[account] = ts
        return len(ts) >= n


def register_failure(account: str, cfg: dict | None = None, now: float | None = None) -> None:
    account = (account or "").strip().lower()
    if not account:
        return
    now = time.time() if now is None else now
    _, window = _cfg_n(cfg)
    with _lock:
        ts = [t for t in (_fails.get(account) or []) if now - t < window]
        ts.append(now)
        _fails[account] = ts


def clear_failures(account: str) -> None:
    account = (account or "").strip().lower()
    with _lock:
        _fails.pop(account, None)


def reset_all_for_tests() -> None:
    with _lock:
        _fails.clear()


def lock_message(cfg: dict | None = None) -> str:
    n, mins = _cfg_n(cfg)
    return f"登录失败次数过多，请 {int(mins // 60) or 5} 分钟后再试"
