#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维护模式标志（2.7.3）：更新 / 重启 / 冷启动窗口用户可见「系统正在更新中」。

- 状态以文件 flag 为准（进程死后 nginx 仍可读）；禁止仅内存。
- 路径：{data_dir}/maintenance.flag（生产即 数据/maintenance.flag）
- 原子写：同目录 tmp → os.replace（与项目 secure 写一致）
- data_dir 一律 loaders.data_dir，禁止自拼路径。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import loaders

DEFAULT_MAX_MINUTES = 10
FLAG_NAME = "maintenance.flag"
_REASONS = frozenset({"update", "restart", "boot", "manual"})


def flag_path(cfg: dict | None = None, root: Path | None = None) -> Path:
    """维护标志文件绝对路径。cfg 缺省时 load_config(strict=False)。"""
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    return loaders.data_dir(cfg, root) / FLAG_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def turn_on(
    reason: str = "manual",
    cfg: dict | None = None,
    root: Path | None = None,
    *,
    pid: int | None = None,
) -> Path:
    """打开维护态：原子写 flag。reason ∈ update|restart|boot|manual。"""
    reason = (reason or "manual").strip().lower()
    if reason not in _REASONS:
        reason = "manual"
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    path = flag_path(cfg, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "reason": reason,
        "ts": _now_iso(),
        "pid": int(pid if pid is not None else os.getpid()),
    }
    raw = json.dumps(payload, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(raw, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
    return path


def turn_off(cfg: dict | None = None, root: Path | None = None) -> bool:
    """关闭维护态：删除 flag。不存在返回 False，不抛。"""
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    path = flag_path(cfg, root)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def is_on(cfg: dict | None = None, root: Path | None = None) -> bool:
    """flag 文件存在即为维护 on（先 maybe_expire 由调用方或中间件负责）。"""
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    return flag_path(cfg, root).is_file()


def read_flag(cfg: dict | None = None, root: Path | None = None) -> dict[str, Any] | None:
    """读 flag JSON；坏文件/不存在 → None。"""
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    path = flag_path(cfg, root)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"reason": "manual", "ts": "", "pid": 0}
        return json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {"reason": "manual", "ts": "", "pid": 0}


def _flag_age_seconds(path: Path, data: dict[str, Any] | None) -> float | None:
    """优先 mtime；ts 可解析时也可用。返回秒龄，不可知则 None。"""
    try:
        mtime = path.stat().st_mtime
        age = time.time() - mtime
        if age >= 0:
            return age
    except OSError:
        pass
    if data and data.get("ts"):
        ts = str(data["ts"]).strip()
        for candidate in (ts, ts.replace("Z", "+00:00")):
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.astimezone()  # 当本地
                return max(0.0, time.time() - dt.timestamp())
            except ValueError:
                continue
    return None


def maybe_expire(
    max_minutes: float = DEFAULT_MAX_MINUTES,
    cfg: dict | None = None,
    root: Path | None = None,
) -> bool:
    """超时强制 off 并写告警。返回 True=本次因超时关闭。"""
    if cfg is None:
        cfg = loaders.load_config(root, strict=False) if root else loaders.load_config(strict=False)
    path = flag_path(cfg, root)
    if not path.is_file():
        return False
    data = read_flag(cfg, root)
    age = _flag_age_seconds(path, data)
    limit = max(0.1, float(max_minutes)) * 60.0
    if age is None or age < limit:
        return False
    turn_off(cfg, root)
    detail = (
        f"maintenance.flag 超时强制关闭 age_sec={age:.0f} max_min={max_minutes} "
        f"reason={(data or {}).get('reason', '?')}"
    )
    try:
        from notify import alert_event

        alert_event("maintenance_expire", detail, root=root)
    except Exception:
        try:
            import alert_store

            alert_store.append_alert("warning", "maintenance_expire", detail[:500], cfg=cfg, root=root)
        except Exception:
            pass
    return True


def maintenance_html_path(root: Path | None = None) -> Path:
    """仓库内 static/maintenance.html。"""
    base = Path(root) if root else loaders.ROOT
    return base / "static" / "maintenance.html"


def load_maintenance_html(root: Path | None = None) -> str:
    """读维护页正文；缺失时最小兜底（仍含关键文案）。"""
    p = maintenance_html_path(root)
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    # 禁止在 .py 内嵌 HTML 标签（test_no_html_in_py）；缺文件时纯文本兜底
    return "系统正在更新中\n请稍后，服务恢复后将自动刷新。\n"
