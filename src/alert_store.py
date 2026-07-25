#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机告警存储（2.6.4·B）：只写本地文件，零外发。

- 告警正文：数据/日志/告警.log（轮转 5MB×2）
- 已读水位：数据/告警已读水位.json（时间戳 ISO）
- 禁止金额/客户名进入摘要（调用方负责脱敏）
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("kanban.alert_store")

_LOCK = threading.Lock()
_MAX_BYTES = 5 * 1024 * 1024
_KEEP_BACKUPS = 1  # 告警.log + 告警.log.1

# 类别白名单（非强制，便于扫读）
LEVELS = ("info", "warning", "error")


def _now_iso() -> str:
    # 含微秒，避免同一秒内 ack 后新告警被水位挡住
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f%z")


def _data_dir(cfg: dict | None, root: Path | None) -> Path:
    """解析数据目录：支持测试传入的绝对 data_dir。"""
    import loaders

    base = root or loaders.ROOT
    cfg = cfg or {}
    raw = cfg.get("data_dir")
    if raw:
        p = Path(str(raw))
        if p.is_absolute():
            return p
        return base / p
    try:
        return loaders.data_dir(loaders.load_config(base, strict=False), base)
    except Exception:
        return base / "数据"


def _log_dir(cfg: dict | None, root: Path | None) -> Path:
    p = _data_dir(cfg, root) / "日志"
    p.mkdir(parents=True, exist_ok=True)
    return p


def alert_log_path(cfg: dict | None = None, root: Path | None = None) -> Path:
    return _log_dir(cfg, root) / "告警.log"


def watermark_path(cfg: dict | None = None, root: Path | None = None) -> Path:
    return _data_dir(cfg, root) / "告警已读水位.json"


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.is_file() or path.stat().st_size < _MAX_BYTES:
            return
        bak = path.with_suffix(path.suffix + ".1")
        if bak.exists():
            bak.unlink()
        path.replace(bak)
    except OSError as e:
        log.warning("alert log rotate failed: %s", e)


def append_alert(
    level: str,
    category: str,
    detail: str,
    *,
    cfg: dict | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """追加一条告警。返回写入的 dict。"""
    level = (level or "warning").lower()
    if level not in LEVELS:
        level = "warning"
    category = (category or "general").strip() or "general"
    detail = (detail or "").replace("\n", " ").strip()[:500]
    rec = {
        "time": _now_iso(),
        "level": level,
        "category": category,
        "detail": detail,
    }
    line = (
        f"{rec['time']} | {rec['level']} | {rec['category']} | {rec['detail']}\n"
    )
    with _LOCK:
        path = alert_log_path(cfg, root)
        _rotate_if_needed(path)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        except OSError as e:
            log.warning("append_alert failed: %s path=%s", e, path)
    return rec


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|", 3)]
    if len(parts) < 4:
        return None
    return {"time": parts[0], "level": parts[1], "category": parts[2], "detail": parts[3]}


def read_alerts(
    *,
    cfg: dict | None = None,
    root: Path | None = None,
    days: int = 7,
    limit: int = 200,
) -> list[dict[str, str]]:
    """读近 days 天告警（新在后）。"""
    path = alert_log_path(cfg, root)
    if not path.is_file():
        return []
    cutoff = datetime.now().astimezone() - timedelta(days=max(1, days))
    out: list[dict[str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in raw.splitlines():
        rec = _parse_line(line)
        if not rec:
            continue
        # time 格式 YYYY-mm-dd HH:MM:SS±zzzz 或无 tz
        try:
            ts = rec["time"]
            if len(ts) >= 19:
                dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                if dt.replace(tzinfo=None) < cutoff.replace(tzinfo=None):
                    continue
        except Exception:
            pass  # 解析失败则保留该行
        out.append(rec)
    if len(out) > limit:
        out = out[-limit:]
    return out


def get_watermark(cfg: dict | None = None, root: Path | None = None) -> str:
    p = watermark_path(cfg, root)
    if not p.is_file():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return str(d.get("read_until") or "")
    except (OSError, ValueError):
        return ""


def set_watermark(
    read_until: str | None = None,
    *,
    cfg: dict | None = None,
    root: Path | None = None,
) -> str:
    """标记已读到 read_until（默认=现在）。"""
    ts = read_until or _now_iso()
    p = watermark_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"read_until": ts, "updated_at": _now_iso()}
    try:
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("set_watermark failed: %s", e)
    return ts


def unread_alerts(
    *,
    cfg: dict | None = None,
    root: Path | None = None,
    days: int = 7,
) -> list[dict[str, str]]:
    """水位之后的告警。"""
    wm = get_watermark(cfg, root)
    all_a = read_alerts(cfg=cfg, root=root, days=days)
    if not wm:
        return all_a
    return [a for a in all_a if a.get("time", "") > wm]


def unread_summary(
    *,
    cfg: dict | None = None,
    root: Path | None = None,
    days: int = 7,
    recent: int = 3,
) -> dict[str, Any]:
    u = unread_alerts(cfg=cfg, root=root, days=days)
    tail = u[-recent:] if u else []
    return {
        "unread_count": len(u),
        "recent": [
            {"time": x.get("time"), "level": x.get("level"), "category": x.get("category"), "detail": x.get("detail")}
            for x in tail
        ],
    }
