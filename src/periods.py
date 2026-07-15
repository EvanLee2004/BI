#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周期矩阵（年 / 季度 / 月）与日期区间判定。未来月份/季度不生成（还没数据）。"""

from __future__ import annotations

import calendar
import datetime

import loaders


def all_period_ranges(today: datetime.date) -> dict[str, tuple[str, datetime.date, datetime.date, str]]:
    """{周期key: (label, start含, end含, 分组∈{年,季度,月})}。年=全年；季度=Q1~当前季；月=1月~当前月。"""
    year = today.year
    out: dict[str, tuple[str, datetime.date, datetime.date, str]] = {}
    out[f"{year}年"] = (f"{year}年", datetime.date(year, 1, 1), datetime.date(year, 12, 31), "年")
    cur_q = (today.month - 1) // 3 + 1
    for q in range(1, cur_q + 1):
        sm, em = (q - 1) * 3 + 1, q * 3
        out[f"{year}年Q{q}"] = (
            f"{year}年 Q{q}",
            datetime.date(year, sm, 1),
            datetime.date(year, em, calendar.monthrange(year, em)[1]),
            "季度",
        )
    for m in range(1, today.month + 1):
        out[f"{year}年{m}月"] = (
            f"{year}年{m}月",
            datetime.date(year, m, 1),
            datetime.date(year, m, calendar.monthrange(year, m)[1]),
            "月",
        )
    # 自定义月区间（日历选段用）：所有 m1<m2 连续段。费用/手填口径按月，区间只到月粒度（不做按天）。
    for m1 in range(1, today.month + 1):
        for m2 in range(m1 + 1, today.month + 1):
            out[f"{year}年{m1}-{m2}月"] = (
                f"{year}年{m1}~{m2}月",
                datetime.date(year, m1, 1),
                datetime.date(year, m2, calendar.monthrange(year, m2)[1]),
                "区间",
            )
    return out


def months_in(start: datetime.date, end: datetime.date, cap: datetime.date) -> list[tuple[int, int]]:
    """区间内、且不晚于 cap（当前月）的所有 (年,月)。用于把月度手填汇总到年/季度周期。"""
    out = []
    y, m = start.year, start.month
    while datetime.date(y, m, 1) <= min(end, cap):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def date_in_range(parts, start: datetime.date, end: datetime.date) -> bool:
    if not parts:
        return False
    try:
        d = datetime.date(parts[0], parts[1], parts[2])
    except ValueError:
        return False
    return start <= d <= end


def ledger_row_date(row: tuple, ledger_year: int, cols: dict) -> tuple[int, int, int] | None:
    """收单台账行日期：优先「收单日期」，退回「收单月份」(配 ledger_year)。"""
    c = cols["收单日期"]
    parts = loaders.parse_date_parts(row[c] if len(row) > c else None)
    if parts:
        return parts
    c = cols["收单月份"]
    m = row[c] if len(row) > c else None
    if m not in (None, ""):
        try:
            mm = int(str(m).strip())
        except ValueError:
            return None
        # 月份范围校验：越界（如"13"/"0"/误填）返 None → 体检按"日期解析不出"计数判黄，
        # 而非造出 (year,13,1) 这种无效日期被 date_in_range 静默剔除却不报警（与 loaders._valid_ymd 一致）。
        return (ledger_year, mm, 1) if 1 <= mm <= 12 else None
    return None
