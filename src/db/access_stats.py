#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3.3.0 用户统计：访问/登录审计只读聚合（纯函数 + SQL）。

数据源：manual_配置变更 中 类别∈{访问,登录}。
主频次指标 = login_ok（登录成功）；看端明细不计入登录成功。
bu_bucket 由账号权限解析，多 BU 不拆行多计。
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

# 扫描保护：days=0 时仍限制行数，避免拖垮管理端
_MAX_SCAN_ROWS = 50_000

ACTION_LABELS: dict[str, str] = {
    "login_ok": "登录成功",
    "login_fail": "登录失败",
    "logout": "退出",
    "export": "导出",
    "detail_vm": "看端明细",
    "other_access": "其他访问",
}

_NOTE = "主指标=登录成功；明细不计入登录次数。"


def parse_action(category: str | None, summary: str | None) -> str | None:
    """摘要/类别 → action 码；非访问类返回 None（不进本页）。"""
    cat = str(category or "").strip()
    summ = str(summary or "")
    if cat not in ("访问", "登录"):
        return None
    # 旧 admin form 登录成功：类别=登录
    if cat == "登录":
        return "login_ok"
    if "登录成功" in summ:
        return "login_ok"
    if "登录失败" in summ:
        return "login_fail"
    if "退出" in summ:
        return "logout"
    if "导出" in summ:
        return "export"
    if "看端明细" in summ:
        return "detail_vm"
    return "other_access"


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def resolve_bu_bucket(account_row: dict | None) -> str:
    """账号行 → bu_bucket（首版不拆行多计）。"""
    if not account_row:
        return "未登记账号"
    perm = str(account_row.get("权限") or "").strip()
    if perm == "管理员":
        return "管理员"
    if perm == "整体":
        return "整体"
    if perm == "BU":
        raw = account_row.get("可见BU") or []
        if isinstance(raw, str):
            import re

            parts = [p.strip() for p in re.split(r"[、，,;；\n]", raw) if p.strip()]
        elif isinstance(raw, (list, tuple)):
            parts = [str(x).strip() for x in raw if str(x).strip()]
        else:
            parts = []
        # 去「整体」保留字
        parts = [p for p in parts if p != "整体"]
        return "、".join(parts) if parts else "BU"
    if perm:
        return perm
    return "其他"


def _now() -> datetime:
    return datetime.now()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def window_bounds(days: int, now: datetime | None = None) -> tuple[str | None, str, int]:
    """返回 (window_start|None, window_end, days_normalized)。days=0 → 无下界。"""
    now = now or _now()
    end = _fmt(now)
    try:
        d = int(days)
    except (TypeError, ValueError):
        d = 30
    if d not in (0, 7, 30, 90):
        d = 30
    if d == 0:
        return None, end, 0
    start_dt = now - timedelta(days=d)
    # 窗起点按日 00:00:00，便于「近 N 天」对齐
    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return _fmt(start_dt), end, d


def _acct_map(accounts: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in accounts or []:
        name = str(a.get("账号") or "").strip()
        if name:
            out[name] = a
    return out


def _fetch_rows(
    conn: sqlite3.Connection,
    window_start: str | None,
    *,
    limit: int = _MAX_SCAN_ROWS,
) -> list[tuple]:
    cols = "id, 时间, 操作账号, 类别, 摘要"
    limit = max(1, min(_MAX_SCAN_ROWS, int(limit)))
    if window_start:
        return conn.execute(
            f"SELECT {cols} FROM manual_配置变更 "
            "WHERE 类别 IN ('访问','登录') AND 时间 >= ? "
            "ORDER BY id DESC LIMIT ?",
            (window_start, limit),
        ).fetchall()
    return conn.execute(
        f"SELECT {cols} FROM manual_配置变更 "
        "WHERE 类别 IN ('访问','登录') "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def _row_to_event(
    row: tuple,
    acct_by: dict[str, dict],
) -> dict[str, Any] | None:
    rid, t, account, cat, summary = row
    action = parse_action(cat, summary)
    if action is None:
        return None
    acc = str(account or "").strip()
    ar = acct_by.get(acc)
    return {
        "id": int(rid),
        "time": str(t or ""),
        "account": acc,
        "action": action,
        "label": action_label(action),
        "summary": str(summary or ""),
        "bu_bucket": resolve_bu_bucket(ar),
        "_display_name": str((ar or {}).get("显示名") or acc),
        "_perm": str((ar or {}).get("权限") or ""),
    }


def aggregate_user_stats(  # noqa: C901  # 单次扫表聚 KPI+三维，拆函数可读性不升
    conn: sqlite3.Connection,
    accounts: list[dict],
    *,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """聚合 KPI / 三维 / 日趋势。accounts = load_accounts 结果。"""
    window_start, window_end, days_n = window_bounds(days, now=now)
    acct_by = _acct_map(accounts)
    raw = _fetch_rows(conn, window_start)

    events: list[dict[str, Any]] = []
    for r in raw:
        ev = _row_to_event(r, acct_by)
        if ev:
            events.append(ev)

    kpi = {
        "login_ok": 0,
        "login_fail": 0,
        "active_accounts": 0,
        "detail_vm": 0,
        "export": 0,
        "logout": 0,
    }
    action_counts: dict[str, int] = defaultdict(int)
    # account → counters
    by_acc: dict[str, dict[str, Any]] = {}
    by_bu: dict[str, dict[str, Any]] = {}
    daily: dict[str, int] = defaultdict(int)
    login_ok_accounts: set[str] = set()

    for ev in events:
        act = ev["action"]
        action_counts[act] += 1
        acc = ev["account"] or "?"
        bucket = ev["bu_bucket"]

        if act == "login_ok":
            kpi["login_ok"] += 1
            login_ok_accounts.add(acc)
            day = (ev["time"] or "")[:10]
            if day:
                daily[day] += 1
        elif act == "login_fail":
            kpi["login_fail"] += 1
        elif act == "detail_vm":
            kpi["detail_vm"] += 1
        elif act == "export":
            kpi["export"] += 1
        elif act == "logout":
            kpi["logout"] += 1

        if acc not in by_acc:
            by_acc[acc] = {
                "account": acc,
                "display_name": ev["_display_name"],
                "perm_label": ev["_perm"] or "未登记",
                "bu_bucket": bucket,
                "login_ok": 0,
                "login_fail": 0,
                "detail_vm": 0,
                "export": 0,
                "last_login_ok": "",
            }
        row_a = by_acc[acc]
        if act == "login_ok":
            row_a["login_ok"] += 1
            t = ev["time"]
            if t and (not row_a["last_login_ok"] or t > row_a["last_login_ok"]):
                row_a["last_login_ok"] = t
        elif act == "login_fail":
            row_a["login_fail"] += 1
        elif act == "detail_vm":
            row_a["detail_vm"] += 1
        elif act == "export":
            row_a["export"] += 1

        if bucket not in by_bu:
            by_bu[bucket] = {
                "bu_bucket": bucket,
                "login_ok": 0,
                "login_fail": 0,
                "active_accounts": 0,
                "_login_ok_accs": set(),
            }
        row_b = by_bu[bucket]
        if act == "login_ok":
            row_b["login_ok"] += 1
            row_b["_login_ok_accs"].add(acc)
        elif act == "login_fail":
            row_b["login_fail"] += 1

    kpi["active_accounts"] = len(login_ok_accounts)

    by_account = sorted(by_acc.values(), key=lambda x: (-int(x["login_ok"]), x["account"]))
    bu_list = []
    for b in by_bu.values():
        bu_list.append(
            {
                "bu_bucket": b["bu_bucket"],
                "login_ok": int(b["login_ok"]),
                "login_fail": int(b["login_fail"]),
                "active_accounts": len(b["_login_ok_accs"]),
            }
        )
    bu_list.sort(key=lambda x: (-x["login_ok"], x["bu_bucket"]))

    total_actions = sum(action_counts.values()) or 0
    by_action = []
    for act, cnt in sorted(action_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        pct = round(100.0 * cnt / total_actions, 1) if total_actions else 0.0
        by_action.append(
            {
                "action": act,
                "label": action_label(act),
                "count": int(cnt),
                "pct": pct,
            }
        )

    daily_login_ok = [
        {"date": d, "count": int(daily[d])} for d in sorted(daily.keys())
    ]

    return {
        "days": days_n,
        "window_start": window_start or "",
        "window_end": window_end,
        "kpi": kpi,
        "by_account": by_account,
        "by_bu": bu_list,
        "by_action": by_action,
        "daily_login_ok": daily_login_ok,
        "note": _NOTE,
    }


def list_access_events(
    conn: sqlite3.Connection,
    accounts: list[dict],
    *,
    days: int = 30,
    action: str | None = None,
    account: str | None = None,
    limit: int = 200,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """分页明细（倒序）。"""
    window_start, _window_end, _days_n = window_bounds(days, now=now)
    acct_by = _acct_map(accounts)
    raw = _fetch_rows(conn, window_start)

    action_f = (action or "").strip() or None
    account_f = (account or "").strip() or None
    items_all: list[dict[str, Any]] = []
    for r in raw:
        ev = _row_to_event(r, acct_by)
        if not ev:
            continue
        if action_f and ev["action"] != action_f:
            continue
        if account_f and account_f not in ev["account"]:
            continue
        items_all.append(
            {
                "id": ev["id"],
                "time": ev["time"],
                "account": ev["account"],
                "action": ev["action"],
                "label": ev["label"],
                "summary": ev["summary"],
                "bu_bucket": ev["bu_bucket"],
            }
        )

    total = len(items_all)
    try:
        lim = max(1, min(1000, int(limit)))
    except (TypeError, ValueError):
        lim = 200
    try:
        off = max(0, int(offset))
    except (TypeError, ValueError):
        off = 0
    page = items_all[off : off + lim]
    return {"total": total, "items": page}


__all__ = [
    "ACTION_LABELS",
    "parse_action",
    "action_label",
    "resolve_bu_bucket",
    "window_bounds",
    "aggregate_user_stats",
    "list_access_events",
]
