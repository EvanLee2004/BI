# -*- coding: utf-8 -*-
"""前端错误只写日志（任务书57·B-5）。

- 落盘：数据/前端错误.log
- 轮转：单文件上限 5MB，最多 2 份（.log / .log.1）
- 去重：同一 (message, page) 24h 内只增计数，防死循环灌盘
- 鉴权：仅收错误文本，无数据读取；端点应公开可写但限流+截断
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_MAX_BYTES = 5 * 1024 * 1024
_MAX_MSG = 800
_MAX_STACK = 1200
_DEDUP_TTL = 24 * 3600
# 进程内去重表 {(msg, page): (count, first_ts, last_ts)}
_DEDUP: dict[tuple[str, str], tuple[int, float, float]] = {}
# 简易限流：滑动窗口 60s 最多 30 条
_RATE: deque[float] = deque()
_RATE_WINDOW = 60.0
_RATE_MAX = 30


def _log_path(root: Path | None, cfg: dict | None) -> Path:
    import loaders

    return loaders.data_dir(cfg or {}, root) / "前端错误.log"


def _rotate_if_needed(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < _MAX_BYTES:
        return
    bak = path.with_suffix(path.suffix + ".1")
    if bak.is_file():
        bak.unlink()
    path.rename(bak)


def _truncate(s: Any, n: int) -> str:
    t = str(s or "").replace("\x00", "")
    if len(t) > n:
        return t[: n - 1] + "…"
    return t


def _rate_ok() -> bool:
    now = time.time()
    while _RATE and now - _RATE[0] > _RATE_WINDOW:
        _RATE.popleft()
    if len(_RATE) >= _RATE_MAX:
        return False
    _RATE.append(now)
    return True


def record_frontend_error(
    payload: dict,
    *,
    cfg: dict | None = None,
    root: Path | None = None,
) -> dict:
    """写入一条前端错误。返回 {ok, deduped, count} 或 {ok:False, reason}。"""
    if not _rate_ok():
        return {"ok": False, "reason": "rate_limited"}

    msg = _truncate(payload.get("message") or payload.get("msg") or "unknown", _MAX_MSG)
    stack = _truncate(payload.get("stack") or payload.get("stack_top") or "", _MAX_STACK)
    page = _truncate(payload.get("page") or payload.get("url") or "", 200)
    # 不收 cookie / 用户输入 / 金额字段
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    key = (msg, page)

    with _LOCK:
        now = time.time()
        # 清理过期去重
        expired = [k for k, v in _DEDUP.items() if now - v[2] > _DEDUP_TTL]
        for k in expired:
            _DEDUP.pop(k, None)

        if key in _DEDUP:
            cnt, first, _ = _DEDUP[key]
            cnt += 1
            _DEDUP[key] = (cnt, first, now)
            path = _log_path(root, cfg)
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(path)
            line = json.dumps(
                {"ts": ts, "message": msg, "page": page, "dedup_count": cnt, "note": "dedup"},
                ensure_ascii=False,
            )
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            return {"ok": True, "deduped": True, "count": cnt}

        _DEDUP[key] = (1, now, now)
        path = _log_path(root, cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path)
        rec = {
            "ts": ts,
            "message": msg,
            "stack_top": stack.split("\n")[0] if stack else "",
            "stack": stack,
            "page": page,
            "dedup_count": 1,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "deduped": False, "count": 1}


def frontend_error_stats(*, cfg: dict | None = None, root: Path | None = None, hours: float = 24) -> dict:
    """近 N 小时错误条数（按日志行；去重行仍计 1 行）。"""
    path = _log_path(root, cfg)
    if not path.is_file():
        return {"path": str(path), "count_24h": 0, "yellow": False}
    cutoff = time.time() - hours * 3600
    n = 0
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    ts = o.get("ts") or ""
                    # parse ts
                    t = time.mktime(time.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")) if len(ts) >= 19 else 0
                    if t >= cutoff:
                        n += 1
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
    except OSError:
        return {"path": str(path), "count_24h": 0, "yellow": False}
    return {"path": str(path), "count_24h": n, "yellow": n > 0}
