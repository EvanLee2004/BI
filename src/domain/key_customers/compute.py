#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重点客户分析 · 纯函数（3.4.0）。

自然年 · 下单预估本币 · 六档 S–E；无 HTTP / 无 fmt。
金额全程 int 分；ytd>0 才进档；空名归 unfilled、不进饼分母。
"""
from __future__ import annotations

import datetime
from typing import Any

import loaders
import money
import periods

# 档位阈值（分）：1 万 = 10_000 元 = 1_000_000 分
# S≥200 · A[80,200) · B[30,80) · C[10,30) · D[3,10) · E(0,3) 万
TIER_ORDER: tuple[str, ...] = ("S", "A", "B", "C", "D", "E")
# (id, lower_inclusive_fen) 降序判定
_TIER_FLOORS: tuple[tuple[str, int], ...] = (
    ("S", 200_000_000),
    ("A", 80_000_000),
    ("B", 30_000_000),
    ("C", 10_000_000),
    ("D", 3_000_000),
    ("E", 1),  # ytd>=1 分且 <3 万
)
TIER_RANGE_DISP: dict[str, str] = {
    "S": "≥200万",
    "A": "[80,200)万",
    "B": "[30,80)万",
    "C": "[10,30)万",
    "D": "[3,10)万",
    "E": "(0,3)万",
}
# 3.4.1 策略 A：六档默认全折叠（禁止 SAB 无限制同开撑成长列表墙）
DEFAULT_OPEN_TIERS: frozenset[str] = frozenset()
LAZY_TIERS: frozenset[str] = frozenset({"C", "D", "E"})
EMPTY_LABEL = "（未填）"

# 展示用帮助文案常量（VM packer 下发；禁止前端硬编码业务口径）
HELP_LINE_METRIC = "按自然年下单预估本币分级 · 每年清零 · 不随月/季标签重算等级"
HELP_LINE_SILENT = "静默：近 2 个已过去完整自然月下单预估为 0（当前月不计入）；年累计仍可很大。"
HELP_LINE_SALES = "主销售：该客户本年下单预估最多的销售（非唯一绑定；多人显示 +N）。"
HELP_LINES: tuple[str, ...] = (HELP_LINE_METRIC, HELP_LINE_SILENT, HELP_LINE_SALES)
SALES_COL_LABEL = "主销售"
SALES_COL_TIP = "本年下单预估最多的销售，非唯一绑定"
SILENT_TIP = "近 2 个已过去完整自然月下单预估为 0（当前月不计入）"


def grade_ytd_fen(ytd: int) -> str | None:
    """年累计下单预估（分）→ 档位；ytd<=0 返回 None。"""
    try:
        v = int(ytd)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    for tid, floor in _TIER_FLOORS:
        if v >= floor:
            return tid
    return None


def _elapsed_months(year: int, today: datetime.date) -> list[int]:
    """已过去完整自然月（1-based）。当年：1..today.month-1；历史年：1..12；未来年：空。"""
    if today.year > year:
        return list(range(1, 13))
    if today.year < year:
        return []
    if today.month <= 1:
        return []
    return list(range(1, today.month))


def is_silent(months: list[int], year: int, today: datetime.date) -> bool:
    """连续 2 个已过去完整自然月下单=0 → True；不足 2 个已过去月 → False。"""
    elapsed = _elapsed_months(year, today)
    if len(elapsed) < 2:
        return False
    m1, m2 = elapsed[-2], elapsed[-1]
    vals = list(months or [0] * 12)
    if len(vals) < 12:
        vals = (vals + [0] * 12)[:12]
    return int(vals[m1 - 1] or 0) == 0 and int(vals[m2 - 1] or 0) == 0


def _accumulate_rows(
    order_rows: list | None,
    amount_col: str,
    date_col: str,
    start: datetime.date,
    end: datetime.date,
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, dict[str, int]], int, int]:
    """扫行 → ytd / months / sales_amt / unfilled_amt / unfilled_count。"""
    ytd: dict[str, int] = {}
    months: dict[str, list[int]] = {}
    sales_amt: dict[str, dict[str, int]] = {}
    unfilled_amt = 0
    unfilled_count = 0
    for r in order_rows or []:
        parts = loaders.parse_date_parts(r.get(date_col))
        if not periods.date_in_range(parts, start, end):
            continue
        name = str(r.get("客户") or "").strip()
        fen = int(money.as_fen(r.get(amount_col)))
        if not name:
            if fen:
                unfilled_amt += fen
                unfilled_count += 1
            continue
        ytd[name] = ytd.get(name, 0) + fen
        mlist = months.setdefault(name, [0] * 12)
        if parts:
            m = int(parts[1])
            if 1 <= m <= 12:
                mlist[m - 1] += fen
        sales = str(r.get("销售") or "").strip() or EMPTY_LABEL
        sa = sales_amt.setdefault(name, {})
        sa[sales] = sa.get(sales, 0) + fen
    return ytd, months, sales_amt, unfilled_amt, unfilled_count


def _item_for_name(
    name: str,
    amt: int,
    months: dict[str, list[int]],
    sales_amt: dict[str, dict[str, int]],
    year: int,
    today: datetime.date,
) -> dict[str, Any]:
    mlist = months.get(name) or [0] * 12
    sa = sales_amt.get(name) or {}
    ranked_sales = sorted(sa.items(), key=lambda kv: (-kv[1], kv[0]))
    primary = ranked_sales[0][0] if ranked_sales else ""
    extra = max(0, len(ranked_sales) - 1)
    return {
        "name": name,
        "ytd": int(amt),
        "months": [int(x) for x in mlist],
        "primary_sales": primary,
        "sales_extra": int(extra),
        "silent": is_silent(mlist, year, today),
    }


def _build_tiers(
    ytd: dict[str, int],
    months: dict[str, list[int]],
    sales_amt: dict[str, dict[str, int]],
    year: int,
    today: datetime.date,
) -> dict[str, dict[str, Any]]:
    tiers: dict[str, dict[str, Any]] = {
        tid: {"items": [], "amount": 0, "count": 0} for tid in TIER_ORDER
    }
    for name, amt in ytd.items():
        if amt <= 0:
            continue
        tid = grade_ytd_fen(amt)
        if not tid:
            continue
        tiers[tid]["items"].append(
            _item_for_name(name, amt, months, sales_amt, year, today)
        )
    for tid in TIER_ORDER:
        items = tiers[tid]["items"]
        items.sort(key=lambda it: (-int(it["ytd"]), str(it["name"])))
        tiers[tid]["amount"] = int(sum(int(it["ytd"]) for it in items))
        tiers[tid]["count"] = len(items)
    return tiers


def compute_key_customers(
    order_rows: list | None,
    year: int,
    cols_cfg: dict | None,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """聚合 + 分级 + 静默 + 饼图原料。

    返回 summary["key_customers"] 原始结构（分）：
      year, metric, currency, tiers{S..E: items/amount/count}, totals, unfilled
    """
    today = today or datetime.date.today()
    year = int(year)
    cols = cols_cfg or {}
    amount_col = cols.get("order_amount") or "下单预估额"
    date_col = cols.get("order_date") or "下单日期"
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)

    ytd, months, sales_amt, unfilled_amt, unfilled_count = _accumulate_rows(
        order_rows, amount_col, date_col, start, end
    )
    tiers = _build_tiers(ytd, months, sales_amt, year, today)
    total_amount = int(sum(tiers[t]["amount"] for t in TIER_ORDER))
    total_count = int(sum(tiers[t]["count"] for t in TIER_ORDER))
    return {
        "year": year,
        "metric": "order_est",
        "currency": "CNY_fen",
        "tiers": tiers,
        "totals": {"amount": total_amount, "count": total_count},
        "unfilled": (
            {"amount": int(unfilled_amt), "count": int(unfilled_count)}
            if unfilled_amt or unfilled_count
            else None
        ),
    }


__all__ = [
    "TIER_ORDER",
    "TIER_RANGE_DISP",
    "DEFAULT_OPEN_TIERS",
    "LAZY_TIERS",
    "HELP_LINES",
    "HELP_LINE_METRIC",
    "HELP_LINE_SILENT",
    "HELP_LINE_SALES",
    "SALES_COL_LABEL",
    "SALES_COL_TIP",
    "SILENT_TIP",
    "grade_ytd_fen",
    "is_silent",
    "compute_key_customers",
]
