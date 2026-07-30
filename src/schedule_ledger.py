# -*- coding: utf-8 -*-
"""持久调度账本（3.6.0 G2）。

唯一键 business_date + slot；状态 pending/running/success/failed/skipped_coalesced。
进程重启后仍可读；禁止只靠内存 set 作唯一真相源。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Literal

SlotStatus = Literal["pending", "running", "success", "failed", "skipped_coalesced"]

LEDGER_NAME = "schedule_ledger.json"
_LOCK = threading.RLock()

VALID = frozenset({"pending", "running", "success", "failed", "skipped_coalesced"})


def ledger_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / LEDGER_NAME


def _atomic_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".sched.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_ledger(data_dir: Path | str) -> dict[str, Any]:
    p = ledger_path(data_dir)
    if not p.is_file():
        return {"version": 1, "slots": {}, "meta": {}}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 损坏：隔离不覆盖
        bak = p.with_suffix(p.suffix + f".corrupt.{int(time.time())}")
        try:
            p.rename(bak)
        except OSError:
            pass
        return {"version": 1, "slots": {}, "meta": {"corrupt_saved": str(bak)}}
    if not isinstance(raw, dict):
        return {"version": 1, "slots": {}, "meta": {}}
    raw.setdefault("version", 1)
    raw.setdefault("slots", {})
    raw.setdefault("meta", {})
    return raw


def save_ledger(data_dir: Path | str, ledger: dict[str, Any]) -> Path:
    p = ledger_path(data_dir)
    with _LOCK:
        _atomic_write(p, ledger)
    return p


def slot_key(business_date: str, slot: str) -> str:
    return f"{business_date}|{slot}"


def get_slot(data_dir: Path | str, business_date: str, slot: str) -> dict[str, Any] | None:
    led = load_ledger(data_dir)
    return (led.get("slots") or {}).get(slot_key(business_date, slot))


def upsert_slot(
    data_dir: Path | str,
    *,
    business_date: str,
    slot: str,
    status: SlotStatus,
    trigger: str = "schedule",
    attempt: int | None = None,
    error: str = "",
    build_id: str = "",
) -> dict[str, Any]:
    if status not in VALID:
        raise ValueError(f"bad status {status}")
    with _LOCK:
        led = load_ledger(data_dir)
        slots = dict(led.get("slots") or {})
        k = slot_key(business_date, slot)
        prev = dict(slots.get(k) or {})
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        row = {
            **prev,
            "business_date": business_date,
            "slot": slot,
            "status": status,
            "trigger": trigger,
            "attempt": int(attempt if attempt is not None else (prev.get("attempt") or 0) + (1 if status == "running" else 0)),
            "error": (error or "")[:300],
            "build_id": build_id or prev.get("build_id") or "",
            "updated_at": now,
        }
        if status == "running":
            row["started_at"] = now
        if status in ("success", "failed", "skipped_coalesced"):
            row["finished_at"] = now
        if status == "success" and not row.get("build_id"):
            row["build_id"] = build_id or now
        slots[k] = row
        led["slots"] = slots
        led["meta"] = {
            **(led.get("meta") or {}),
            "last_update": now,
            "business_date": business_date,
        }
        save_ledger(data_dir, led)
        return row


def plan_catchup(
    *,
    business_date: str,
    planned_slots: list[str],
    now_hhmm: str,
    ledger_slots: dict[str, Any],
) -> tuple[str | None, list[str]]:
    """决定补跑：只补最新应跑时槽一次；更早未满足 → coalesced。

    返回 (slot_to_run | None, coalesced_slots)。
    """
    def mins(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    now_m = mins(now_hhmm)
    due = [s for s in planned_slots if mins(s) <= now_m]
    if not due:
        return None, []

    # 已有今日任意 success 覆盖全量时，后续可 satisfied
    any_success = False
    for s in planned_slots:
        st = (ledger_slots.get(slot_key(business_date, s)) or {}).get("status")
        if st == "success":
            any_success = True
            break

    # 最新 due 若已 success → 不跑
    latest = due[-1]
    st_latest = (ledger_slots.get(slot_key(business_date, latest)) or {}).get("status")
    if st_latest == "success":
        return None, []

    if any_success and st_latest != "failed":
        # 已有一次成功全量，其它 due 可 coalesced
        coalesced = [s for s in due[:-1] if (ledger_slots.get(slot_key(business_date, s)) or {}).get("status") != "success"]
        return None, coalesced

    coalesced = []
    for s in due[:-1]:
        st = (ledger_slots.get(slot_key(business_date, s)) or {}).get("status")
        if st != "success":
            coalesced.append(s)
    return latest, coalesced


def day_summary(data_dir: Path | str, business_date: str, planned: list[str]) -> dict[str, Any]:
    led = load_ledger(data_dir)
    slots = led.get("slots") or {}
    success, pending, failed, coalesced = [], [], [], []
    for s in planned:
        st = (slots.get(slot_key(business_date, s)) or {}).get("status")
        if st == "success":
            success.append(s)
        elif st == "failed":
            failed.append(s)
        elif st == "skipped_coalesced":
            coalesced.append(s)
        elif st in ("pending", "running", None):
            pending.append(s)
    return {
        "date": business_date,
        "planned": list(planned),
        "success": success,
        "pending": pending,
        "failed": failed,
        "coalesced": coalesced,
        "meta": led.get("meta") or {},
    }
