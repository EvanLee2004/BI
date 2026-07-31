#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重点客户分析 · 纯函数（3.4.0～3.4.3）。

自然年 · 下单预估本币 · 六档 S–E；无 HTTP / 无 fmt。
金额全程 int 分；ytd>0 才进档；空名归 unfilled、不进饼分母。
3.4.2：sales 全量列表暴露；静默口径不变。
3.4.3：作战台派生——重点贡献、需跟进、临界晋级、三经营池、月趋势摘要。
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
TIER_FLOOR_FEN: dict[str, int] = {tid: floor for tid, floor in _TIER_FLOORS}
# 上一级：A→S … E→D；S 无上一级
_NEXT_TIER: dict[str, tuple[str, int]] = {
    "A": ("S", 200_000_000),
    "B": ("A", 80_000_000),
    "C": ("B", 30_000_000),
    "D": ("C", 10_000_000),
    "E": ("D", 3_000_000),
}
# 临界：距上一级下限差额 <= 上一级下限 × 10% 且 >0（整数分，阈值 = floor//10）
NEAR_GAP_RATIO_NUM = 1
NEAR_GAP_RATIO_DEN = 10

TIER_RANGE_DISP: dict[str, str] = {
    "S": "≥200万",
    "A": "[80,200)万",
    "B": "[30,80)万",
    "C": "[10,30)万",
    "D": "[3,10)万",
    "E": "(0,3)万",
}
# 3.4.3：默认重点池 S/A/B 可直接有 items；C/D/E 仍 lazy
DEFAULT_OPEN_TIERS: frozenset[str] = frozenset({"S", "A", "B"})
LAZY_TIERS: frozenset[str] = frozenset({"C", "D", "E"})
FOCUS_TIERS: frozenset[str] = frozenset({"S", "A", "B"})
NURTURE_TIERS: frozenset[str] = frozenset({"C", "D"})
LONGTAIL_TIERS: frozenset[str] = frozenset({"E"})
POOL_ORDER: tuple[str, ...] = ("focus", "nurture", "longtail")
POOL_TIERS: dict[str, tuple[str, ...]] = {
    "focus": ("S", "A", "B"),
    "nurture": ("C", "D"),
    "longtail": ("E",),
}
POOL_LABELS: dict[str, str] = {
    "focus": "重点客户",
    "nurture": "培育客户",
    "longtail": "长尾客户",
}
POOL_HINTS: dict[str, str] = {
    "focus": "S/A/B",
    "nurture": "C/D",
    "longtail": "E",
}
DEFAULT_POOL = "focus"
EMPTY_LABEL = "（未填）"

# 展示用帮助文案常量（VM packer 下发；禁止前端硬编码业务口径）
# 3.6.1：sec 标题「重点客户下单情况追踪」；panel 同文，禁止与 sec 矛盾
PANEL_TITLE = "重点客户下单情况追踪"
HELP_LINE_METRIC = "自然年 · 下单预估本币 · 每年清零 · 不随月/季重算等级"
# 分级行：阈值只改 TIER_RANGE_DISP 即变（SSOT）；Vue 只渲染 VM 串
HELP_LINE_TIERS = (
    "分级（自然年下单预估本币）："
    + " · ".join(
        f"{tid}{TIER_RANGE_DISP[tid].removesuffix('万')}" for tid in TIER_ORDER
    )
    + "万"
)
HELP_LINE_SILENT = (
    "静默：近 2 个已过去完整自然月下单预估为 0（当前月不计入）；"
    "故当月有单仍可能静默"
)
HELP_LINE_CLICK = "点击客户查看 1～12 月连续下单；可加入最多 5 客比较"
HELP_LINE_NEAR = (
    "临界晋级：距上一级门槛不超过 10%，仅作销售跟进提示，不改变客户等级"
)
# 兼容旧名：不再含「主销售」
HELP_LINE_SALES = HELP_LINE_CLICK
HELP_LINES: tuple[str, ...] = (
    HELP_LINE_METRIC,
    HELP_LINE_TIERS,
    HELP_LINE_SILENT,
    HELP_LINE_NEAR,
    HELP_LINE_CLICK,
)
SALES_COL_LABEL = "销售"
SALES_COL_TIP = "本年各销售下单预估金额（降序）"
SILENT_TIP = "近 2 个已过去完整自然月下单预估为 0（当前月不计入）；当月有单仍可能静默"
NEAR_TIP = HELP_LINE_NEAR
TIER_RANK: dict[str, int] = {tid: i for i, tid in enumerate(TIER_ORDER)}


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


def pool_for_tier(tier_id: str) -> str:
    """六档 → 经营池 id。"""
    tid = (tier_id or "").strip().upper()
    if tid in FOCUS_TIERS:
        return "focus"
    if tid in NURTURE_TIERS:
        return "nurture"
    if tid in LONGTAIL_TIERS:
        return "longtail"
    return "longtail"


def next_tier_floor(tier_id: str) -> tuple[str, int] | None:
    """当前档上一级 (id, floor_fen)；S 或未知 → None。"""
    tid = (tier_id or "").strip().upper()
    return _NEXT_TIER.get(tid)


def gap_to_next_fen(ytd: int, tier_id: str) -> int | None:
    """距上一级下限差额（分）；S 无上一级返回 None；已达/超（不应发生）返回 0。"""
    nxt = next_tier_floor(tier_id)
    if nxt is None:
        return None
    try:
        v = int(ytd)
    except (TypeError, ValueError):
        return None
    floor = int(nxt[1])
    return max(0, floor - v)


def near_gap_threshold_fen(tier_id: str) -> int | None:
    """上一级下限 × 10%（整数分）。"""
    nxt = next_tier_floor(tier_id)
    if nxt is None:
        return None
    return int(nxt[1]) * NEAR_GAP_RATIO_NUM // NEAR_GAP_RATIO_DEN


def is_near_upgrade(ytd: int, tier_id: str) -> bool:
    """临界晋级：0 < gap <= 上一级下限×10%；达门槛已升档故不算。

    边界：正好 10% 算；超过 1 分不算。
    """
    tid = (tier_id or "").strip().upper()
    if tid == "S" or tid not in _NEXT_TIER:
        return False
    gap = gap_to_next_fen(ytd, tid)
    thr = near_gap_threshold_fen(tid)
    if gap is None or thr is None:
        return False
    return 0 < int(gap) <= int(thr)


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


def _normalize_months12(months: list[int] | None) -> list[int]:
    vals = list(months or [0] * 12)
    if len(vals) < 12:
        vals = (vals + [0] * 12)[:12]
    return [int(x or 0) for x in vals[:12]]


def _incomplete_month(year: int, today: datetime.date) -> int:
    if today.year == year and 1 <= today.month <= 12:
        return int(today.month)
    return 0


def _peak_and_total(vals: list[int], elapsed: list[int]) -> tuple[int, int, int]:
    peak_m = elapsed[0]
    peak_v = int(vals[peak_m - 1])
    total = 0
    for m in elapsed:
        v = int(vals[m - 1])
        total += v
        if v > peak_v:
            peak_v = v
            peak_m = m
    return int(peak_m), int(peak_v), int(total)


def _recent_trend_code(vals: list[int], elapsed: list[int]) -> str:
    if len(elapsed) < 2:
        return "none"
    a = int(vals[elapsed[-2] - 1])
    b = int(vals[elapsed[-1] - 1])
    if b > a:
        return "up"
    if b < a:
        return "down"
    return "flat"


def _consecutive_silent_complete(vals: list[int], elapsed: list[int]) -> int:
    silent_n = 0
    for m in reversed(elapsed):
        if int(vals[m - 1]) == 0:
            silent_n += 1
        else:
            break
    return int(silent_n)


def month_trend_summary(
    months: list[int] | None,
    year: int,
    today: datetime.date,
) -> dict[str, Any]:
    """完整自然月上的趋势摘要（分）；当前未完结月不计入峰值/均/升降。

    返回：
      peak_month, peak_fen, avg_fen, complete_month_count,
      recent_trend (up|down|flat|none), consecutive_silent_complete,
      incomplete_month (1-12|0)
    """
    vals = _normalize_months12(months)
    elapsed = _elapsed_months(year, today)
    incomplete = _incomplete_month(year, today)
    if not elapsed:
        return {
            "peak_month": 0,
            "peak_fen": 0,
            "avg_fen": 0,
            "complete_month_count": 0,
            "recent_trend": "none",
            "consecutive_silent_complete": 0,
            "incomplete_month": incomplete,
        }
    peak_m, peak_v, total = _peak_and_total(vals, elapsed)
    n = len(elapsed)
    return {
        "peak_month": peak_m,
        "peak_fen": peak_v,
        "avg_fen": int(total // n) if n else 0,
        "complete_month_count": int(n),
        "recent_trend": _recent_trend_code(vals, elapsed),
        "consecutive_silent_complete": _consecutive_silent_complete(vals, elapsed),
        "incomplete_month": int(incomplete),
    }


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
    tier_id: str,
) -> dict[str, Any]:
    mlist = months.get(name) or [0] * 12
    sa = sales_amt.get(name) or {}
    # 金额降序，同额按名稳定序
    ranked_sales = sorted(sa.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    primary = ranked_sales[0][0] if ranked_sales else ""
    extra = max(0, len(ranked_sales) - 1)
    sales_list = [{"name": str(n), "fen": int(f)} for n, f in ranked_sales]
    gap = gap_to_next_fen(amt, tier_id)
    near = is_near_upgrade(amt, tier_id)
    nxt = next_tier_floor(tier_id)
    trend = month_trend_summary(mlist, year, today)
    return {
        "name": name,
        "ytd": int(amt),
        "tier": tier_id,
        "pool": pool_for_tier(tier_id),
        "months": [int(x) for x in mlist],
        "primary_sales": primary,  # 兼容字段；3.4.2 UI 不消费
        "sales_extra": int(extra),
        "sales": sales_list,  # 3.4.2：全量销售（分）；packer 出 amount_disp/wo
        "silent": is_silent(mlist, year, today),
        "gap_fen": gap,
        "near_upgrade": bool(near),
        "next_tier": nxt[0] if nxt else None,
        "next_floor_fen": int(nxt[1]) if nxt else None,
        "trend": trend,
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
            _item_for_name(name, amt, months, sales_amt, year, today, tid)
        )
    for tid in TIER_ORDER:
        items = tiers[tid]["items"]
        items.sort(key=lambda it: (-int(it["ytd"]), str(it["name"])))
        tiers[tid]["amount"] = int(sum(int(it["ytd"]) for it in items))
        tiers[tid]["count"] = len(items)
    return tiers


def _war_desk_raw(tiers: dict[str, dict[str, Any]], total_amount: int) -> dict[str, Any]:
    """作战台汇总原料（分 / 计数）；显示串由 packer 生成。"""
    focus_amount = int(sum(int(tiers[t]["amount"]) for t in ("S", "A", "B")))
    silent_focus = 0
    near_count = 0
    for tid in TIER_ORDER:
        for it in tiers[tid]["items"]:
            if tid in FOCUS_TIERS and it.get("silent"):
                silent_focus += 1
            if it.get("near_upgrade"):
                near_count += 1
    return {
        "focus_amount": focus_amount,
        "focus_amount_part": focus_amount,
        "total_amount": int(total_amount),
        "silent_focus_count": int(silent_focus),
        "near_upgrade_count": int(near_count),
    }


def compute_key_customers(
    order_rows: list | None,
    year: int,
    cols_cfg: dict | None,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """聚合 + 分级 + 静默 + 饼/结构条原料 + 作战台派生。

    返回 summary["key_customers"] 原始结构（分）：
      year, metric, currency, tiers{S..E: items/amount/count}, totals, unfilled, war_desk
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
        "war_desk": _war_desk_raw(tiers, total_amount),
    }


__all__ = [
    "TIER_ORDER",
    "TIER_RANGE_DISP",
    "TIER_FLOOR_FEN",
    "DEFAULT_OPEN_TIERS",
    "LAZY_TIERS",
    "FOCUS_TIERS",
    "NURTURE_TIERS",
    "LONGTAIL_TIERS",
    "POOL_ORDER",
    "POOL_TIERS",
    "POOL_LABELS",
    "POOL_HINTS",
    "DEFAULT_POOL",
    "PANEL_TITLE",
    "HELP_LINES",
    "HELP_LINE_METRIC",
    "HELP_LINE_TIERS",
    "HELP_LINE_SILENT",
    "HELP_LINE_SALES",
    "HELP_LINE_CLICK",
    "HELP_LINE_NEAR",
    "SALES_COL_LABEL",
    "SALES_COL_TIP",
    "SILENT_TIP",
    "NEAR_TIP",
    "TIER_RANK",
    "grade_ytd_fen",
    "pool_for_tier",
    "next_tier_floor",
    "gap_to_next_fen",
    "near_gap_threshold_fen",
    "is_near_upgrade",
    "is_silent",
    "month_trend_summary",
    "compute_key_customers",
]
