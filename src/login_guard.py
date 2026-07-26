#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录防爆破（任务书43 / 2.6.3·D2）：按「账号 + 来源 IP」双维度计数。

外部 IP 刷失败不得导致该账号对正常 IP 也进不去。
内存计数，进程重启清零。
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
# key = f"{account}|{ip}" -> timestamps of failures
_fails: dict[str, list[float]] = {}


def _norm_ip(ip: str | None) -> str:
    s = (ip or "").strip()
    return s or "unknown"


def _key(account: str, ip: str | None) -> str:
    return f"{(account or '').strip().lower()}|{_norm_ip(ip)}"


def _cfg_n(cfg: dict | None) -> tuple[int, float]:
    cfg = cfg or {}
    n = int(cfg.get("login_max_failures", 10) or 10)
    mins = float(cfg.get("login_lock_minutes", 5) or 5)
    return max(1, n), max(0.1, mins) * 60.0


def is_locked(
    account: str, cfg: dict | None = None, now: float | None = None, *, ip: str | None = None
) -> bool:
    account = (account or "").strip().lower()
    if not account:
        return False
    n, window = _cfg_n(cfg)
    now = time.time() if now is None else now
    k = _key(account, ip)
    with _lock:
        ts = _fails.get(k) or []
        ts = [t for t in ts if now - t < window]
        _fails[k] = ts
        return len(ts) >= n


def _prune_expired(now: float, window: float) -> None:
    """2.6.7 D-5：按窗口淘汰过期键，防止 _fails 无限涨。"""
    dead = []
    for k, ts in _fails.items():
        kept = [t for t in ts if now - t < window]
        if kept:
            _fails[k] = kept
        else:
            dead.append(k)
    for k in dead:
        _fails.pop(k, None)


def register_failure(
    account: str, cfg: dict | None = None, now: float | None = None, *, ip: str | None = None
) -> None:
    account = (account or "").strip().lower()
    if not account:
        return
    now = time.time() if now is None else now
    _, window = _cfg_n(cfg)
    k = _key(account, ip)
    with _lock:
        _prune_expired(now, window)
        ts = [t for t in (_fails.get(k) or []) if now - t < window]
        ts.append(now)
        _fails[k] = ts


def clear_failures(account: str, *, ip: str | None = None) -> None:
    """清除该账号+IP 的失败计数；ip 省略时清该账号所有 IP（登录成功用）。"""
    account = (account or "").strip().lower()
    with _lock:
        if ip is not None:
            _fails.pop(_key(account, ip), None)
            return
        prefix = f"{account}|"
        for k in list(_fails.keys()):
            if k.startswith(prefix):
                _fails.pop(k, None)


def reset_all_for_tests() -> None:
    with _lock:
        _fails.clear()


def lock_message(cfg: dict | None = None) -> str:
    n, mins = _cfg_n(cfg)
    return f"登录失败次数过多，请 {int(mins // 60) or 5} 分钟后再试"
