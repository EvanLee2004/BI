# -*- coding: utf-8 -*-
"""重点客户 VM packer（3.5.0 单源）。

Domain raw → 显示串 / 月序列 / 共同金额轴 / 作战台。
`packers.py` 仅 re-export 本模块公共函数，禁止双源复制。
"""
from __future__ import annotations

import datetime
from typing import Any

AMOUNT_AXIS_NAME = "月下单金额（万）"
AMOUNT_CHART_TITLE = "连续月下单金额（万）"
RHYTHM_DISCLAIMER = "各客户自身峰值=100，仅比较节奏，不比较金额"
RHYTHM_CHART_TITLE = "连续月下单节奏指数（自身峰值=100）"

def _kc_pct_disp(part: float, total: float) -> str:
    if not total:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def _kc_sales_pairs(it: dict) -> list[tuple[str, float]]:
    """domain sales[{name,fen}] → (name, fen) 列表；缺省回退 primary_sales。"""
    pairs: list[tuple[str, float]] = []
    raw_sales = it.get("sales")
    if isinstance(raw_sales, list):
        for s in raw_sales:
            if not isinstance(s, dict):
                continue
            n = str(s.get("name") or "").strip()
            if not n:
                continue
            try:
                fen = float(s.get("fen") or 0)
            except (TypeError, ValueError):
                fen = 0.0
            pairs.append((n, fen))
    if not pairs:
        primary = str(it.get("primary_sales") or "").strip()
        if primary:
            pairs = [(primary, float(it.get("ytd") or 0))]
    pairs.sort(key=lambda kv: (-kv[1], kv[0]))
    return pairs


def _kc_pack_sales(it: dict) -> tuple[list[dict[str, Any]], str, str]:
    """销售全量 → disp 列表（金额降序）+ sales_disp 兼容串 + primary_sales 兼容。"""
    import charts

    pairs = _kc_sales_pairs(it)
    mx = max((p[1] for p in pairs), default=0.0) or 1.0
    sales_out: list[dict[str, Any]] = [
        {
            "name": n,
            "amount_disp": charts.fmt_wan(fen) + "万",
            "wo": round(max(fen / mx * 100, 0), 1) if fen else 0.0,
        }
        for n, fen in pairs
    ]
    primary_sales = sales_out[0]["name"] if sales_out else ""
    parts = [f"{s['name']} {s['amount_disp']}" for s in sales_out]
    if len(parts) <= 3:
        sales_disp = " · ".join(parts)
    else:
        sales_disp = " · ".join(parts[:3]) + f" · 另有 {len(parts) - 3} 人"
    return sales_out, sales_disp, primary_sales


def _kc_trend_disp(trend: dict | None) -> dict[str, Any]:
    """domain trend → 最终显示串。"""
    import charts

    t = trend if isinstance(trend, dict) else {}
    peak_m = int(t.get("peak_month") or 0)
    peak_fen = float(t.get("peak_fen") or 0)
    avg_fen = float(t.get("avg_fen") or 0)
    n_complete = int(t.get("complete_month_count") or 0)
    recent = str(t.get("recent_trend") or "none")
    silent_n = int(t.get("consecutive_silent_complete") or 0)
    incomplete = int(t.get("incomplete_month") or 0)

    if peak_m and n_complete:
        peak_disp = f"{peak_m}月 {charts.fmt_wan(peak_fen)}万"
    else:
        peak_disp = "—"

    if n_complete:
        avg_disp = charts.fmt_wan(avg_fen) + "万"
    else:
        avg_disp = "—"

    trend_map = {
        "up": "上升",
        "down": "下降",
        "flat": "持平",
        "none": "无可比",
    }
    recent_label = trend_map.get(recent, "无可比")
    if n_complete < 2:
        recent_disp = "近两完整月：无可比"
    else:
        recent_disp = f"近两完整月：{recent_label}"

    if n_complete == 0:
        silent_disp = "连续完整静默月：—"
    else:
        silent_disp = f"连续完整静默月：{silent_n}"

    incomplete_hint = ""
    if 1 <= incomplete <= 12:
        incomplete_hint = f"{incomplete}月未完结"

    return {
        "peak_month": peak_m,
        "peak_disp": peak_disp,
        "avg_disp": avg_disp,
        "complete_month_count": n_complete,
        "recent_trend": recent,
        "recent_disp": recent_disp,
        "consecutive_silent_complete": silent_n,
        "silent_complete_disp": silent_disp,
        "incomplete_month": incomplete,
        "incomplete_hint": incomplete_hint,
    }


def _kc_status_disp(it: dict, *, gap_disp: str) -> str:
    """行状态：静默优先，其次临界/差额。"""
    if it.get("silent"):
        return "静默"
    if it.get("near_upgrade"):
        nxt = it.get("next_tier") or ""
        return "临界晋级" + (f"·距{nxt} {gap_disp}" if nxt and gap_disp else "")
    gap = it.get("gap_fen")
    nxt = it.get("next_tier")
    if gap is not None and nxt and int(gap) > 0 and gap_disp:
        return f"距{nxt}还差{gap_disp}"
    return ""


def _kc_month_status(month_i: int, year: int, today: datetime.date) -> str:
    """月点语义：actual | incomplete | missing（未来月不与实际 0 混）。"""
    year = int(year)
    month_i = int(month_i)
    if today.year < year:
        return "missing"
    if today.year > year:
        return "actual"
    if month_i > today.month:
        return "missing"
    if month_i == today.month:
        return "incomplete"
    return "actual"


def _fen_to_wan(fen: float | int | None) -> float | None:
    if fen is None:
        return None
    return round(float(fen) / 1_000_000.0, 4)


def _kc_pack_month_rows(
    months: list,
    *,
    year: int,
    today: datetime.date,
) -> list[dict[str, Any]]:
    """月序列：共同金额单位 value_wan + 状态；节奏指数仅自峰值归一。"""
    import charts

    vals = list(months or [0] * 12)
    if len(vals) < 12:
        vals = (vals + [0] * 12)[:12]
    # 节奏峰值：仅对非 missing 月取自峰值（含 0）
    rhythm_basis: list[float] = []
    for i, v in enumerate(vals, 1):
        st = _kc_month_status(i, year, today)
        if st == "missing":
            continue
        rhythm_basis.append(float(v or 0))
    mx_m = max(rhythm_basis, default=0.0) or 1.0

    rows: list[dict[str, Any]] = []
    for i, v in enumerate(vals, 1):
        st = _kc_month_status(i, year, today)
        if st == "missing":
            rows.append(
                {
                    "i": i,
                    "name": f"{i}月",
                    "value_fen": None,
                    "value_wan": None,
                    "value_disp": "—",
                    "order_disp": "—",
                    "status": "missing",
                    "rhythm_index": None,
                    # 3.4 兼容：金额图不得再用 wo；保留字段以免旧消费者崩
                    "wo": None,
                }
            )
            continue
        fv = float(v or 0)
        fen_i = int(round(fv))
        wan = _fen_to_wan(fen_i)
        disp = charts.fmt_wan(fv) + "万" if fv else "0万"
        rhythm = round(max(fv / mx_m * 100, 0), 1) if fv else 0.0
        rows.append(
            {
                "i": i,
                "name": f"{i}月",
                "value_fen": fen_i,
                "value_wan": wan,
                "value_disp": disp,
                "order_disp": disp,
                "status": st,
                "rhythm_index": rhythm,
                "wo": rhythm,  # 兼容 spark；金额模式禁止用它当 Y
            }
        )
    return rows


def _kc_pack_item(
    it: dict,
    *,
    tier_max: float,
    year: int,
    monthly: dict,
    today: datetime.date,
) -> dict[str, Any]:
    """单客户行显示串 + 写入 monthly[mkey]。3.5.0 月点含 value_wan/status。"""
    import charts

    name = str(it.get("name") or "")
    ytd = float(it.get("ytd") or 0)
    months = list(it.get("months") or [0] * 12)
    if len(months) < 12:
        months = (months + [0] * 12)[:12]
    sales_out, sales_disp, primary_sales = _kc_pack_sales(it)
    mkey = f"kc:{year}:{name}"
    month_rows = _kc_pack_month_rows(months, year=year, today=today)
    monthly[mkey] = month_rows
    # 行级 wo：档内金额进度条（非折线金额）
    wo = round(max(ytd / tier_max * 100, 0), 1) if ytd and tier_max else 0.0
    tier_id = str(it.get("tier") or "").strip().upper()
    gap_raw = it.get("gap_fen")
    gap_fen = int(gap_raw) if gap_raw is not None else None
    gap_disp = ""
    if gap_fen is not None and gap_fen > 0:
        gap_disp = charts.fmt_wan(float(gap_fen)) + "万"
    near = bool(it.get("near_upgrade"))
    trend = _kc_trend_disp(it.get("trend") if isinstance(it.get("trend"), dict) else None)
    # spark：节奏指数 0–100（轻量条），金额比较请用 monthly.value_wan
    spark = [
        float(r["rhythm_index"]) if r.get("rhythm_index") is not None else 0.0
        for r in month_rows
    ]
    return {
        "name": name,
        "ytd_disp": charts.fmt_wan(ytd) + "万",
        "sales_disp": sales_disp,
        "sales": sales_out,
        "primary_sales": primary_sales,  # 兼容；3.4.2 UI 不消费
        "silent": bool(it.get("silent")),
        "mkey": mkey,
        "wo": wo,
        "tier": tier_id,
        "pool": str(it.get("pool") or ""),
        "gap_fen": gap_fen,
        "gap_disp": gap_disp,
        "near_upgrade": near,
        "next_tier": it.get("next_tier"),
        "status_disp": _kc_status_disp(it, gap_disp=gap_disp),
        "trend": trend,
        "spark_wo": spark,
        "spark_rhythm": spark,
        # 排序辅助（前端只比较这些整数，不算业务）
        "ytd_fen": int(ytd),
        "tier_rank": {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5}.get(tier_id, 9),
    }


def _kc_empty_shell() -> dict[str, Any]:
    from domain.key_customers.compute import (
        DEFAULT_POOL,
        HELP_LINE_METRIC,
        HELP_LINES,
        NEAR_TIP,
        PANEL_TITLE,
        POOL_HINTS,
        POOL_LABELS,
        POOL_ORDER,
        POOL_TIERS,
        SALES_COL_LABEL,
        SALES_COL_TIP,
        SILENT_TIP,
    )

    help_lines = list(HELP_LINES)
    return {
        "year": 0,
        "year_label": "",
        "panel_title": PANEL_TITLE,
        "caption": HELP_LINE_METRIC,
        "help_lines": help_lines,
        "sales_col_label": SALES_COL_LABEL,
        "sales_col_tip": SALES_COL_TIP,
        "silent_tip": SILENT_TIP,
        "near_tip": NEAR_TIP,
        "metric_label": "下单预估（本币）",
        "default_pool": DEFAULT_POOL,
        "pools": [
            {
                "id": pid,
                "label": POOL_LABELS[pid],
                "hint": POOL_HINTS[pid],
                "tiers": list(POOL_TIERS[pid]),
                "count": 0,
                "amount_disp": "0万",
            }
            for pid in POOL_ORDER
        ],
        "summary_cards": {
            "total": {
                "label": "全部客户 / 年累计",
                "count": 0,
                "count_disp": "0户",
                "amount_disp": "0万",
                "value_disp": "0户 · 0万",
            },
            "focus_contrib": {
                "label": "重点客户贡献",
                "pct_disp": "0.0%",
                "amount_disp": "0万",
                "value_disp": "0.0%",
                "tip": "S+A+B 年度金额占全体",
            },
            "silent_focus": {
                "label": "需跟进重点客",
                "count": 0,
                "count_disp": "0户",
                "value_disp": "0户",
                "tip": "仅 S/A/B 中静默客户",
            },
            "near_upgrade": {
                "label": "临界晋级客户",
                "count": 0,
                "count_disp": "0户",
                "value_disp": "0户",
                "tip": NEAR_TIP,
            },
        },
        "structure_bars": {
            "count": {"label": "客户数结构", "segments": []},
            "amount": {"label": "金额结构", "segments": []},
        },
        "tiers": [],
        "pie_count": {"labels": [], "values": [], "values_disp": [], "pct_disp": []},
        "pie_amount": {"labels": [], "values": [], "values_disp": [], "pct_disp": []},
        "monthly": {},
        "amount_axis": {
            "unit": "万",
            "name": AMOUNT_AXIS_NAME,
            "min": 0,
            "max": 0,
            "interval": 0,
            "ticks": [{"value": 0, "label": "0"}],
        },
        "chart": {
            "default_mode": "amount",
            "amount_title": AMOUNT_CHART_TITLE,
            "rhythm_title": RHYTHM_CHART_TITLE,
            "rhythm_disclaimer": RHYTHM_DISCLAIMER,
            "y_axis_name_amount": AMOUNT_AXIS_NAME,
        },
        "as_of": "",
        "empty": True,
        "totals": {"count": 0, "amount_disp": "0万"},
        "compare_max": 3,
        "guide_text": "从左侧客户池选择客户，或点行动队列开始跟进",
    }


def _kc_resolve_war_desk(raw: dict, tiers_raw: dict) -> tuple[float, int, int]:
    """→ focus_amount, silent_focus_count, near_upgrade_count。"""
    from domain.key_customers.compute import TIER_ORDER

    wd = raw.get("war_desk") if isinstance(raw.get("war_desk"), dict) else None
    if wd:
        focus_amount = float(wd.get("focus_amount") or 0)
        return (
            focus_amount,
            int(wd.get("silent_focus_count") or 0),
            int(wd.get("near_upgrade_count") or 0),
        )
    near_count = 0
    silent_focus = 0
    for tid in TIER_ORDER:
        for it in (tiers_raw.get(tid) or {}).get("items") or []:
            if it.get("near_upgrade"):
                near_count += 1
            if tid in ("S", "A", "B") and it.get("silent"):
                silent_focus += 1
    focus_amount = sum(
        float((tiers_raw.get(t) or {}).get("amount") or 0) for t in ("S", "A", "B")
    )
    return focus_amount, silent_focus, near_count


def _kc_action_queues(all_items: list[dict[str, Any]]) -> dict[str, list]:
    def _tier_rank_key(x: dict) -> int:
        tr = x.get("tier_rank")
        return int(tr) if tr is not None else 9

    def _ytd_key(x: dict) -> int:
        y = x.get("ytd_fen")
        return int(y) if y is not None else 0

    def _q_row(it: dict) -> dict[str, Any]:
        return {
            "name": it.get("name"),
            "mkey": it.get("mkey"),
            "tier": it.get("tier"),
            "ytd_disp": it.get("ytd_disp"),
            "status_disp": it.get("status_disp"),
            "silent": bool(it.get("silent")),
            "near_upgrade": bool(it.get("near_upgrade")),
            "gap_disp": it.get("gap_disp") or "",
        }

    silent_q = sorted(
        [it for it in all_items if it.get("silent") and it.get("tier") in ("S", "A", "B")],
        key=lambda x: (_tier_rank_key(x), -_ytd_key(x), str(x.get("name") or "")),
    )
    near_q = sorted(
        [it for it in all_items if it.get("near_upgrade")],
        key=lambda x: (
            int(x.get("gap_fen") if x.get("gap_fen") is not None else 10**18),
            -_ytd_key(x),
            str(x.get("name") or ""),
        ),
    )
    return {
        "silent": [_q_row(it) for it in silent_q[:8]],
        "near": [_q_row(it) for it in near_q[:8]],
    }


def _kc_amount_axis_from_monthly(monthly: dict[str, list]) -> dict[str, Any]:
    """从已打包 monthly 生成共享金额轴（万）。"""
    from viewmodels.packers import pack_axis_meta

    fen_vals: list[float] = [0.0]
    for rows in monthly.values():
        for r in rows:
            vf = r.get("value_fen")
            if vf is not None:
                fen_vals.append(float(vf))
    axis_meta = pack_axis_meta(fen_vals)
    amount_axis: dict[str, Any] = {
        "unit": "万",
        "name": AMOUNT_AXIS_NAME,
        "min": float(axis_meta.get("min") or 0),
        "max": float(axis_meta.get("max") or 0),
        "interval": float(axis_meta.get("interval") or 0),
        "ticks": list(axis_meta.get("ticks") or []),
    }
    wan_ticks = []
    for t in amount_axis["ticks"]:
        try:
            tv = float(t.get("value") or 0)
        except (TypeError, ValueError):
            tv = 0.0
        wan_ticks.append(
            {
                "value": _fen_to_wan(tv) or 0.0,
                "label": t.get("label") or "0",
            }
        )
    amount_axis["ticks"] = wan_ticks
    amount_axis["min"] = 0.0
    amount_axis["max"] = max((float(t["value"]) for t in wan_ticks), default=0.0)
    if len(wan_ticks) >= 2:
        amount_axis["interval"] = float(wan_ticks[1]["value"] - wan_ticks[0]["value"])
    else:
        amount_axis["interval"] = amount_axis["max"] or 0.0
    return amount_axis


def pack_key_customers(
    raw: dict | None,
    *,
    embed_full: bool = False,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """summary['key_customers'] → VM 显示串（六档 + 结构条 + 作战台 + monthly）。

    embed_full=True：导出/离线 snapshot 强制展开 C/D/E items。
    在线首包：S/A/B 全量 items；C/D/E lazy=true 且 items=[]。
    3.4.2：help_lines 去主销售；item.sales[] 全量 disp。
    3.4.3：summary_cards / structure_bars / pools；默认 default_open=S/A/B。
    3.5.0：月点 value_fen/value_wan/status + 共享 amount_axis；默认金额模式。
    保留 pie_* 兼容旧消费者；主 UI 改用 structure_bars。
    """
    import charts
    from domain.key_customers.compute import (
        DEFAULT_OPEN_TIERS,
        DEFAULT_POOL,
        HELP_LINE_METRIC,
        HELP_LINES,
        LAZY_TIERS,
        NEAR_TIP,
        PANEL_TITLE,
        POOL_HINTS,
        POOL_LABELS,
        POOL_ORDER,
        POOL_TIERS,
        SALES_COL_LABEL,
        SALES_COL_TIP,
        SILENT_TIP,
        TIER_ORDER,
        TIER_RANGE_DISP,
    )
    if not raw or not isinstance(raw, dict):
        return _kc_empty_shell()
    help_lines = list(HELP_LINES)
    today = today or datetime.date.today()

    year = int(raw.get("year") or 0)
    totals = raw.get("totals") or {}
    total_count = int(totals.get("count") or 0)
    total_amount = float(totals.get("amount") or 0)
    tiers_raw = raw.get("tiers") or {}
    monthly: dict[str, list] = {}
    tiers_out: list[dict[str, Any]] = []
    pie_labels: list[str] = []
    pie_counts: list[int] = []
    pie_counts_disp: list[str] = []
    pie_count_pct: list[str] = []
    pie_amts: list[float] = []  # 万元
    pie_amts_disp: list[str] = []
    pie_amt_pct: list[str] = []
    seg_count: list[dict[str, Any]] = []
    seg_amount: list[dict[str, Any]] = []
    all_items_for_action: list[dict[str, Any]] = []

    for tid in TIER_ORDER:
        blk = tiers_raw.get(tid) or {}
        items_src = list(blk.get("items") or [])
        count = int(blk.get("count") if blk.get("count") is not None else len(items_src))
        amount = float(blk.get("amount") or 0)
        lazy = (tid in LAZY_TIERS) and (not embed_full)
        tier_max = max((float(it.get("ytd") or 0) for it in items_src), default=0) or 1.0
        if lazy:
            items_out: list[dict[str, Any]] = []
        else:
            items_out = [
                _kc_pack_item(
                    it, tier_max=tier_max, year=year, monthly=monthly, today=today
                )
                for it in items_src
            ]
            all_items_for_action.extend(items_out)
        amt_disp = charts.fmt_wan(amount) + "万"
        pct_c = _kc_pct_disp(float(count), float(total_count))
        pct_a = _kc_pct_disp(amount, total_amount)
        # 布局百分比 wo：前端只渲染，不算比例
        wo_c = round(float(count) / float(total_count) * 100, 2) if total_count else 0.0
        wo_a = round(amount / total_amount * 100, 2) if total_amount else 0.0
        tiers_out.append(
            {
                "id": tid,
                "label": tid,
                "range_disp": TIER_RANGE_DISP.get(tid, ""),
                "count": count,
                "count_disp": f"{count}户",
                "amount_disp": amt_disp,
                "pct_count_disp": pct_c,
                "pct_amount_disp": pct_a,
                "default_open": tid in DEFAULT_OPEN_TIERS,
                "lazy": lazy,
                "items": items_out,
            }
        )
        pie_labels.append(tid)
        pie_counts.append(count)
        pie_counts_disp.append(str(count))
        pie_count_pct.append(pct_c)
        wan = amount / 1_000_000.0  # 分 → 万
        pie_amts.append(round(wan, 4))
        pie_amts_disp.append(charts.fmt_wan(amount) + "万")
        pie_amt_pct.append(pct_a)
        seg_count.append(
            {
                "id": tid,
                "label": tid,
                "count": count,
                "count_disp": f"{count}户",
                "amount_disp": amt_disp,
                "pct_disp": pct_c,
                "wo": wo_c,
            }
        )
        seg_amount.append(
            {
                "id": tid,
                "label": tid,
                "count": count,
                "count_disp": f"{count}户",
                "amount_disp": amt_disp,
                "pct_disp": pct_a,
                "wo": wo_a,
            }
        )

    focus_amount, silent_focus, near_count = _kc_resolve_war_desk(raw, tiers_raw)
    focus_pct = _kc_pct_disp(focus_amount, total_amount)
    focus_amt_disp = charts.fmt_wan(focus_amount) + "万"
    total_amt_disp = charts.fmt_wan(total_amount) + "万"

    pools_out = []
    for pid in POOL_ORDER:
        tids = POOL_TIERS[pid]
        p_count = sum(int((tiers_raw.get(t) or {}).get("count") or 0) for t in tids)
        p_amt = sum(float((tiers_raw.get(t) or {}).get("amount") or 0) for t in tids)
        pools_out.append(
            {
                "id": pid,
                "label": POOL_LABELS[pid],
                "hint": POOL_HINTS[pid],
                "tiers": list(tids),
                "count": p_count,
                "count_disp": f"{p_count}户",
                "amount_disp": charts.fmt_wan(p_amt) + "万",
            }
        )

    action_queues = _kc_action_queues(all_items_for_action)
    amount_axis = _kc_amount_axis_from_monthly(monthly)
    chart = {
        "default_mode": "amount",
        "amount_title": AMOUNT_CHART_TITLE,
        "rhythm_title": RHYTHM_CHART_TITLE,
        "rhythm_disclaimer": RHYTHM_DISCLAIMER,
        "y_axis_name_amount": AMOUNT_AXIS_NAME,
    }

    return {
        "year": year,
        "year_label": f"{year}年" if year else "",
        "panel_title": PANEL_TITLE,
        "caption": HELP_LINE_METRIC,
        "help_lines": help_lines,
        "sales_col_label": SALES_COL_LABEL,
        "sales_col_tip": SALES_COL_TIP,
        "silent_tip": SILENT_TIP,
        "near_tip": NEAR_TIP,
        "metric_label": "下单预估（本币）",
        "default_pool": DEFAULT_POOL,
        "compare_max": 3,
        "guide_text": "从左侧客户池选择客户，或点行动队列开始跟进",
        "pools": pools_out,
        "summary_cards": {
            "total": {
                "label": "全部客户 / 年累计",
                "count": total_count,
                "count_disp": f"{total_count}户",
                "amount_disp": total_amt_disp,
                "value_disp": f"{total_count}户 · {total_amt_disp}",
            },
            "focus_contrib": {
                "label": "重点客户贡献",
                "pct_disp": focus_pct,
                "amount_disp": focus_amt_disp,
                "value_disp": focus_pct,
                "tip": "S+A+B 年度金额占全体",
            },
            "silent_focus": {
                "label": "需跟进重点客",
                "count": silent_focus,
                "count_disp": f"{silent_focus}户",
                "value_disp": f"{silent_focus}户",
                "tip": "仅 S/A/B 中静默客户",
            },
            "near_upgrade": {
                "label": "临界晋级客户",
                "count": near_count,
                "count_disp": f"{near_count}户",
                "value_disp": f"{near_count}户",
                "tip": NEAR_TIP,
            },
        },
        "structure_bars": {
            "count": {"label": "客户数结构", "segments": seg_count},
            "amount": {"label": "金额结构", "segments": seg_amount},
        },
        "action_queues": action_queues,
        "tiers": tiers_out,
        "pie_count": {
            "labels": pie_labels,
            "values": pie_counts,
            "values_disp": pie_counts_disp,
            "pct_disp": pie_count_pct,
        },
        "pie_amount": {
            "labels": pie_labels,
            "values": pie_amts,
            "values_disp": pie_amts_disp,
            "pct_disp": pie_amt_pct,
        },
        "monthly": monthly,
        "amount_axis": amount_axis,
        "chart": chart,
        "as_of": today.isoformat(),
        "empty": total_count == 0,
        "totals": {
            "count": total_count,
            "amount_disp": total_amt_disp,
        },
    }


def pack_key_customers_tier_items(
    raw: dict | None,
    tier: str,
    *,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """懒加载单档：items + monthly 显示串齐。"""
    from domain.key_customers.compute import TIER_ORDER, TIER_RANGE_DISP

    tier = (tier or "").strip().upper()
    if tier not in TIER_ORDER:
        raise ValueError("tier 须为 S|A|B|C|D|E")
    packed = pack_key_customers(raw, embed_full=True, today=today)
    by = {t["id"]: t for t in packed.get("tiers") or []}
    blk = by.get(tier) or {}
    items = list(blk.get("items") or [])
    mkeys = {it.get("mkey") for it in items if it.get("mkey")}
    monthly = {k: v for k, v in (packed.get("monthly") or {}).items() if k in mkeys}
    return {
        "tier": tier,
        "year": packed.get("year") or 0,
        "range_disp": TIER_RANGE_DISP.get(tier, ""),
        "items": items,
        "count": len(items),
        "monthly": monthly,
        "amount_axis": packed.get("amount_axis") or {},
        "chart": packed.get("chart") or {},
    }
