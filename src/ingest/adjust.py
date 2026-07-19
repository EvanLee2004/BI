#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调整记录重放 + 过期校验（03 详细设计 二·4 / 02 核心决策 #1）。

SQL 一律经 db_write（任务书43·业务层零裸 SQL）；本模块只保留过期校验与套用逻辑。
"""

from __future__ import annotations

import sqlite3

import loaders
import money
import schema
from db_write import (
    count_locator_matches,
    list_active_adjustments,
    mark_adjustment_expired,
    select_field_by_locator,
    select_ledger_date_parts,
    soft_delete_by_locator,
    update_field_by_locator,
)

_AMOUNT_FIELDS = money.AMOUNT_FIELD_NAMES
_LEDGER_DATE_FIELDS = {"收单日期", "收单月份"}


def _ledger_ym(收单日期, 收单月份, ledger_year: int) -> str | None:
    parts = loaders.parse_date_parts(收单日期)
    if parts:
        return f"{parts[0]:04d}-{parts[1]:02d}"
    if 收单月份 not in (None, ""):
        try:
            return f"{ledger_year:04d}-{int(str(收单月份).strip()):02d}"
        except ValueError:
            return None
    return None


def _values_match(current, 原值: str, 字段: str = "") -> bool:  # noqa: C901
    if 原值 is None:
        原值 = ""
    os_ = str(原值).strip()
    if 字段 in _AMOUNT_FIELDS:
        if current is None:
            return os_ == ""
        try:
            cur_fen = int(current)
        except (ValueError, TypeError):
            return False
        if os_ == "":
            return False
        try:
            if "." not in os_ and "e" not in os_.lower():
                if int(float(os_)) == cur_fen:
                    return True
            yuan_fen = money.yuan_to_fen(os_)
            if yuan_fen is not None and yuan_fen == cur_fen:
                return True
        except (ValueError, TypeError):
            return False
        return False
    cs = "" if current is None else str(current).strip()
    try:
        return abs(float(cs) - float(os_)) < 1e-6
    except (ValueError, TypeError):
        return cs == os_


def _cast(字段: str, 新值: str):
    if 字段 in _AMOUNT_FIELDS:
        s = "" if 新值 is None else str(新值).strip()
        if s == "":
            return 0
        if "." not in s and "e" not in s.lower():
            try:
                return int(float(s))
            except (ValueError, TypeError):
                pass
        fen = money.yuan_to_fen(loaders.parse_amount(新值))
        return 0 if fen is None else fen
    return 新值


def apply_adjustments(conn: sqlite3.Connection, now: str) -> dict:
    """重放全部生效调整。返回 {applied, expired, removed, skipped, missing}。"""
    applied = expired = removed = skipped = missing = 0
    rows = list_active_adjustments(conn)
    for aid, 目标表, 定位键, 字段, 原值, 新值, 类型 in rows:
        if 目标表 not in schema.STD_TABLE_NAMES:
            skipped += 1
            continue
        match_rows = count_locator_matches(conn, 目标表, 定位键)
        if not match_rows:
            missing += 1
            continue
        if len(match_rows) > 1:
            mark_adjustment_expired(conn, aid)
            expired += 1
            continue

        if 类型 == "剔除":
            removed += soft_delete_by_locator(conn, 目标表, 定位键)
            continue

        if 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
            skipped += 1
            continue
        current = select_field_by_locator(conn, 目标表, 字段, 定位键)
        if not _values_match(current, 原值, 字段):
            mark_adjustment_expired(conn, aid)
            expired += 1
            continue
        update_field_by_locator(conn, 目标表, 字段, _cast(字段, 新值), 定位键)
        if schema.PERIOD_DATE_FIELD.get(目标表) == 字段:
            parts = loaders.parse_date_parts(新值)
            ym = f"{parts[0]:04d}-{parts[1]:02d}" if parts else None
            update_field_by_locator(conn, 目标表, "归属月", ym, 定位键)
        elif 目标表 == "std_费用明细" and 字段 in _LEDGER_DATE_FIELDS:
            d, m = select_ledger_date_parts(conn, 定位键)
            ym = _ledger_ym(d, m, int(now[:4]))
            update_field_by_locator(conn, 目标表, "归属月", ym, 定位键)
        applied += 1
    conn.commit()
    return {"applied": applied, "expired": expired, "removed": removed, "skipped": skipped, "missing": missing}
