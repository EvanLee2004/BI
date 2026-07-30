#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书50·B：各板块结构化显示字段（*_disp + 条宽数值），前端零金额运算。

与 domain 同源口径；3.2.0 起无 HTML 僵尸字段（body_by_period / svg_html 等已删）。
"""

from __future__ import annotations

from typing import Any


def _wan(v) -> str:
    import charts

    return charts.fmt_wan(float(v or 0))


def _kpi_bu_orders_rows(bu_list, charts) -> list[dict[str, Any]]:
    if not bu_list:
        return []
    max_amt = max((float(d.get("amount") or 0.0) for d in bu_list), default=0.0) or 1.0
    rows = []
    for d in bu_list:
        amt_v = float(d.get("amount") or 0.0)
        pct = d.get("pct")
        if pct is not None:
            w = min(max(float(pct), 0.0), 100.0)
            cls = "ok" if pct >= 100 else ("warn" if pct >= 80 else "low")
            badge = f"{pct:.0f}%"
            tip = f"年目标 {charts.fmt_wan(d['target'])}万 · 全年累计 {charts.fmt_wan(d.get('year_amount') or 0)}万"
        else:
            w = min(max(amt_v / max_amt * 100.0, 0.0), 100.0) if amt_v else 0.0
            cls = "soft"
            badge = "未设目标"
            tip = "该 BU 未填下单年目标；条长仅为部门间相对大小"
        rows.append(
            {
                "name": d["name"],
                "amount_disp": charts.fmt_wan(amt_v) + "万",
                "badge_disp": badge,
                "bar_w": w,
                "cls": cls,
                "tip": tip,
            }
        )
    return rows


def _kpi_delta(val: float, prev_key, P, key, up_good, _kpi_val) -> dict[str, Any]:
    delta = {"show": False, "cls": "", "text": ""}
    if prev_key is not None and prev_key in P and _kpi_val(P[prev_key], key):
        pv = float(_kpi_val(P[prev_key], key) or 0.0)
        if pv:
            d = (val - pv) / abs(pv) * 100
            good = (d >= 0) == up_good
            arrow = "▲" if d >= 0 else "▼"
            delta = {"show": True, "cls": "up" if good else "down", "text": f"{arrow}{abs(d):.1f}%"}
    return delta


def _kpi_subs(key, pctkey, p, val, charts) -> list[dict[str, str]]:
    subs: list[dict[str, str]] = []
    if key == "revenue_gross":
        # 2.7.5 口径 A：副行「不含税 · ÷1.06」；数值仍为后端已算 revenue_net
        subs.append({"label": "不含税 · ÷1.06", "value_disp": charts.fmt_wan(p["revenue_net"]) + "万"})
        o = float(p.get("orders") or 0.0)
        if o > 0:
            subs.append({"label": "交付占下单", "value_disp": f"{val / o * 100:.0f}%"})
    elif pctkey == "gross_margin_pct":
        # 2.2.4·B：大数字已是毛利率%，副信息改为毛利额
        subs.append({"label": "毛利额", "value_disp": charts.fmt_wan(val) + "万"})
    elif pctkey == "pretax_margin_pct":
        subs.append({"label": "利润率", "value_disp": f"{p[pctkey]:.1f}%"})
    if key == "receipts":
        r = p.get("receipt_order_ratio_pct")
        rtxt = f"{r:.1f}%" if r is not None else "—"
        subs = [{"label": "总回款/下单比", "value_disp": rtxt}]
    return subs


def _kpi_feet(key, p, val, peak, show_ar, charts) -> list[dict[str, str]]:
    feet: list[dict[str, str]] = []
    if peak:
        # 2.7.5 口径 A：交付金额峰值 Vue 前缀「全年峰值 · 」+ label → 「全年峰值 · {月} · 含税」
        plab = peak["label"]
        if key == "revenue_gross" and "含税" not in str(plab):
            plab = f"{plab} · 含税"
        feet.append({"kind": "peak", "label": plab, "value_disp": peak["value_disp"]})
    if key == "receipts" and show_ar:
        ar = float(p.get("revenue_gross") or 0.0) - val
        ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar))
        feet.append({"kind": "ar", "label": "已交付未回款", "value_disp": ar_s + "万"})
    return feet


def pack_kpi_cards_by_period(summary: dict, cfg: dict | None = None) -> dict[str, list[dict[str, Any]]]:
    """周期 → KPI 卡数组（主数/副标/峰值/目标条/BU 进度全为显示串）。

    任务书51·B2：峰值/目标条消费 domain.pl.structure 公共函数。
    """
    import charts
    from domain.pl.structure import kpi_peak_for, kpi_target_bar
    from viewmodels.format import KPI_CARDS, _kpi_period_label, _kpi_val, _prev_period_key

    cfg = cfg or {}
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    year = meta.get("year")
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    out: dict[str, list[dict[str, Any]]] = {}

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        prev = _prev_period_key(pkey, year) if year else None
        period_tag = _kpi_period_label(pkey, year) if year else pkey
        cards = []
        for label, key, src, up_good, pctkey, _color, tkey in KPI_CARDS:
            val = float(_kpi_val(p, key) or 0.0)
            # 2.2.4·B：毛利率卡大数字=毛利率%；key 仍 gross_profit（delta/peak/target 逻辑不断）
            if key == "gross_profit" and pctkey:
                headline = f"{float(p.get(pctkey) or 0.0):.1f}"
                unit = "%"
                # 2.3.0 count-up 中间帧用后端 number（展示用，非二次算账）
                anim_value = float(p.get(pctkey) or 0.0)
            else:
                headline = charts.fmt_wan(val)
                unit = "万"
                # val 为分；与 fmt_wan 同口径换算到「万」供中间帧插值
                try:
                    fen = int(val)
                except (TypeError, ValueError):
                    fen = 0
                anim_value = (fen / 100.0) / 10000.0
            card: dict[str, Any] = {
                "label": label,
                "period_tag": period_tag,
                "value": anim_value,
                "value_disp": headline,
                "value_unit": unit,
                "delta": _kpi_delta(val, prev, P, key, up_good, _kpi_val),
                "subs": _kpi_subs(key, pctkey, p, val, charts),
                "target": kpi_target_bar(tkey, pkey, p, budget),
                "bu_orders": _kpi_bu_orders_rows(BUO.get(pkey), charts) if key == "orders" else [],
                "feet": _kpi_feet(key, p, val, kpi_peak_for(summary, key), show_ar, charts),
                "src": src,
                "data_key": key,
            }
            # 2.7.5 口径 A：交付金额卡小字「含税」（整体+BU 同源 packers）
            if key == "revenue_gross":
                card["hint"] = "含税"
            cards.append(card)
        out[pkey] = cards
    return out


def pack_pl_by_period(summary: dict, *, is_bu: bool = False) -> dict[str, dict[str, Any]]:
    """周期 → {rows, details} 结构化利润表（任务书51·B2：消费 domain.pl.pl_structure）。"""
    from domain.pl.structure import pl_structure, structure_for_vm

    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    yk = meta.get("year_key") or ""
    unc = (meta.get("unclassified") or {}).get("expense") or {}
    unc_amt = float(unc.get("amount") or 0) if unc else 0.0
    alloc = meta.get("public_allocation") or {"enabled": False}
    out: dict[str, dict[str, Any]] = {}

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        unc_use = unc_amt if ((not is_bu) and unc_amt > 0 and pkey == yk) else None
        struct = pl_structure(
            p,
            FT.get(pkey) or {},
            is_bu=is_bu,
            unclassified_amt=unc_use,
            alloc_meta=alloc if is_bu else None,
        )
        out[pkey] = structure_for_vm(struct)
    return out


def pack_profit_rank_by_period(summary: dict, *, embed_full: bool = False) -> dict[str, dict[str, Any]]:
    """周期 → 收入/毛利结构双卡结构化数据。"""
    import charts

    P = summary.get("periods") or {}
    out: dict[str, dict[str, Any]] = {}

    def pack_side(rk, title, dim, show_meta=True):
        if not rk:
            return {
                "title": title,
                "dim": dim,
                "conc_disp": "",
                "items": [],
                "others": None,
                "empty": True,
                "full_items": [],
            }
        items_out = []
        items = rk.get("items") or []
        mx = max((float(it.get("revenue") or 0) for it in items), default=0) or 1
        for i, it in enumerate(items, 1):
            rev = float(it.get("revenue") or 0)
            items_out.append(
                {
                    "i": i,
                    "name": it.get("name") or "",
                    "revenue_disp": charts.fmt_wan(rev) + "万",
                    "cost_pct_disp": (f"{it.get('cost_pct'):.1f}%" if show_meta and it.get("cost_pct") is not None else ""),
                    "bar_w": max(2.0, rev / mx * 100) if rev else 0,
                }
            )
        others = rk.get("others")
        others_out = None
        if others:
            others_out = {
                "names": others.get("names"),
                "amt_disp": charts.fmt_wan(others.get("revenue") or 0) + "万",
                "cost_pct_disp": (
                    f"{others.get('cost_pct'):.1f}%" if show_meta and others.get("cost_pct") is not None else ""
                ),
            }
        full_out = []
        if embed_full and others:
            full_src = rk.get("full_items") or items
            fmx = max((float(it.get("revenue") or 0) for it in full_src), default=0) or 1
            for i, it in enumerate(full_src, 1):
                rev = float(it.get("revenue") or 0)
                full_out.append(
                    {
                        "i": i,
                        "name": it.get("name") or "",
                        "revenue_disp": charts.fmt_wan(rev) + "万",
                        "cost_pct_disp": (
                            f"{it.get('cost_pct'):.1f}%" if show_meta and it.get("cost_pct") is not None else ""
                        ),
                        "bar_w": max(2.0, rev / fmx * 100) if rev else 0,
                    }
                )
        c = rk.get("conc_pct")
        k = rk.get("conc_k", 5)
        conc = f"前{k}大占收入 {c:.1f}%" if c is not None else ""
        return {
            "title": title,
            "dim": dim,
            "conc_disp": conc,
            "items": items_out,
            "others": others_out,
            "empty": not items_out,
            "full_items": full_out,
            "show_meta": show_meta,
        }

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        pr = p.get("profit_rankings") or {}
        s, e = p.get("range", ("", ""))
        out[pkey] = {
            "start": s,
            "end": e,
            "customer": pack_side(pr.get("revenue_by_customer"), "收入 · 按客户", "customer", True),
            "sales": pack_side(pr.get("revenue_by_sales"), "收入 · 按销售", "sales", False),
        }
    return out


def pack_expense_views_by_period(summary: dict) -> dict[str, dict[str, Any]]:
    """期间费用构成：四态横条数据（大类环形已有 donut_by_period）。"""
    import charts
    from viewmodels.format import _fine_to_rows

    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    BP = summary.get("expense_by_profit_center") or {}
    BD = summary.get("expense_by_department") or {}
    out: dict[str, dict[str, Any]] = {}

    def hbar(rows, prefix):
        if rows is None:
            return []
        if not rows:
            return []
        sink = frozenset({"未分类", "未标注明细类型"})
        ordered = [r for r in rows if r[0] not in sink] + [r for r in rows if r[0] in sink]
        mx = max((v for _, v, _ in rows), default=1) or 1
        items = []
        for name, val, fine in ordered:
            w = max(2.0, val / mx * 100)
            fine_lines = [{"name": str(n), "amt_disp": charts.fmt_wan(a) + "万"} for n, a in (fine or [])]
            items.append(
                {
                    "key": f"{prefix}:{name}",
                    "name": str(name),
                    "amt_disp": charts.fmt_wan(val) + "万",
                    "bar_w": w,
                    "sink": name in sink,
                    "fine": fine_lines,
                }
            )
        return items

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        e = p.get("expense") or {}
        fine_rows = _fine_to_rows(FT.get(pkey) or {})
        out[pkey] = {
            "total_disp": charts.fmt_wan(e.get("total") or 0) + "万",
            "by_category": hbar(fine_rows, "fine"),
            "by_pc": hbar(BP.get(pkey), "pc") if BP.get(pkey) is not None else [],
            "by_dept": hbar(BD.get(pkey), "dept") if BD.get(pkey) is not None else [],
        }
    return out


def pack_axis_labels(values: list[float], n: int = 5) -> list[str]:
    """Y 轴刻度显示串列表（兼容旧字段）。"""
    ticks = pack_axis_ticks(values, n=n)
    return [t["label"] for t in ticks]


def pack_axis_ticks(values: list[float], n: int = 5) -> list[dict[str, Any]]:
    """Y 轴刻度：[{value, label}] 后端算好，前端 axisLabel 只查表。修复 000,000 bug。

    任务书51·B7：附 min/max/interval 元数据（写在首元素旁由 pack_axis_meta 取）。
    """
    import charts
    import math

    if not values:
        return [{"value": 0, "label": "0"}]
    mx = max(abs(float(v or 0)) for v in values) or 1.0
    raw = mx / max(n - 1, 1)
    if raw <= 0:
        return [{"value": 0, "label": "0"}]
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = math.ceil(raw / mag) * mag
    ticks = []
    v = 0.0
    for _ in range(n + 3):
        lab = charts.fmt_wan(v) if v else "0"
        # 万元单位标注（0 除外）
        if v:
            lab = lab + "万" if not lab.endswith("万") else lab
        ticks.append({"value": v, "label": lab})
        v += step
        if v > mx * 1.05 + step * 0.01:
            break
    return ticks


def pack_axis_meta(values: list[float], n: int = 5) -> dict[str, Any]:
    """任务书51·B7：Y 轴 min/max/interval + ticks，前端禁止最近刻度扫描。"""
    ticks = pack_axis_ticks(values, n=n)
    if not ticks:
        return {"min": 0, "max": 0, "interval": 0, "ticks": []}
    mn = float(ticks[0]["value"])
    mx = float(ticks[-1]["value"])
    interval = float(ticks[1]["value"] - ticks[0]["value"]) if len(ticks) >= 2 else 0.0
    return {"min": mn, "max": mx, "interval": interval, "ticks": ticks}


def pack_period_month_ranges(summary: dict) -> dict[str, dict[str, str]]:
    """任务书51·B6：周期 key → {month_from, month_to}（YYYY-MM），前端只赋值。

    年 key → 空串（不筛月，与旧 Ledger 行为一致）；季/月/区间 → 起止月。
    """
    from viewmodels.format import _period_months_map

    meta = summary.get("meta") or {}
    year = int(meta.get("year") or 2026)
    yk = meta.get("year_key") or ""
    out: dict[str, dict[str, str]] = {}
    for k, months in (_period_months_map(summary) or {}).items():
        if not k:
            continue
        # 全年：不限月
        if k == yk or (str(k).endswith("年") and "Q" not in str(k) and "月" not in str(k)):
            out[k] = {"month_from": "", "month_to": ""}
            continue
        if not months:
            out[k] = {"month_from": "", "month_to": ""}
            continue
        a, b = int(months[0]), int(months[-1])
        out[k] = {
            "month_from": f"{year}-{a:02d}",
            "month_to": f"{year}-{b:02d}",
        }
    return out


def _chart_month_max_from_meta(meta: dict) -> int:
    """任务书61·C-2：当前系统月上界（1–12），尊重 period_pin 驱动的 today。"""
    for key in ("current_month_key", "current_month_label"):
        s = str(meta.get(key) or "")
        if "年" in s and "月" in s:
            try:
                part = s.split("年", 1)[1].replace("月", "").strip()
                if part.isdigit():
                    m = int(part)
                    if 1 <= m <= 12:
                        return m
            except (IndexError, ValueError):
                pass
    return 12


def pack_daily_defaults(summary: dict) -> dict[str, Any]:
    """按时间段查询默认日期与年。任务书61：default_end 落到当前系统月（便于前端裁未来空月）。"""
    meta = summary.get("meta") or {}
    y = meta.get("year") or 2026
    m = _chart_month_max_from_meta(meta)
    # 月末日：简单用 28+ 即可（仅作区间默认上界，非账期口径）
    import calendar

    last = calendar.monthrange(int(y), int(m))[1]
    return {
        "year": y,
        "default_start": f"{y}-01-01",
        "default_end": f"{y}-{int(m):02d}-{last:02d}",
        "year_key": meta.get("year_key") or f"{y}年",
        "chart_month_max": int(m),
    }


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


def _kc_pack_item(it: dict, *, tier_max: float, year: int, monthly: dict) -> dict[str, Any]:
    """单客户行显示串 + 写入 monthly[mkey]。3.4.2 含 sales[]；3.4.3 含 gap/趋势。"""
    import charts

    name = str(it.get("name") or "")
    ytd = float(it.get("ytd") or 0)
    months = list(it.get("months") or [0] * 12)
    if len(months) < 12:
        months = (months + [0] * 12)[:12]
    sales_out, sales_disp, primary_sales = _kc_pack_sales(it)
    mkey = f"kc:{year}:{name}"
    mx_m = max((float(v) for v in months), default=0) or 1.0
    month_rows = []
    for i, v in enumerate(months, 1):
        fv = float(v or 0)
        month_rows.append(
            {
                "i": i,
                "name": f"{i}月",
                "order_disp": charts.fmt_wan(fv) + "万",
                "wo": round(max(fv / mx_m * 100, 0), 1) if fv else 0.0,
            }
        )
    monthly[mkey] = month_rows
    wo = round(max(ytd / tier_max * 100, 0), 1) if ytd and tier_max else 0.0
    tier_id = str(it.get("tier") or "").strip().upper()
    gap_raw = it.get("gap_fen")
    gap_fen = int(gap_raw) if gap_raw is not None else None
    gap_disp = ""
    if gap_fen is not None and gap_fen > 0:
        gap_disp = charts.fmt_wan(float(gap_fen)) + "万"
    near = bool(it.get("near_upgrade"))
    trend = _kc_trend_disp(it.get("trend") if isinstance(it.get("trend"), dict) else None)
    # spark：完整 12 月 wo 列表（轻量，非 ECharts）
    spark = [float(r["wo"] or 0) for r in month_rows]
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


def pack_key_customers(raw: dict | None, *, embed_full: bool = False) -> dict[str, Any]:
    """summary['key_customers'] → VM 显示串（六档 + 结构条 + 作战台 + monthly）。

    embed_full=True：导出/离线 snapshot 强制展开 C/D/E items。
    在线首包：S/A/B 全量 items；C/D/E lazy=true 且 items=[]。
    3.4.2：help_lines 去主销售；item.sales[] 全量 disp。
    3.4.3：summary_cards / structure_bars / pools；默认 default_open=S/A/B。
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
                _kc_pack_item(it, tier_max=tier_max, year=year, monthly=monthly)
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
        "empty": total_count == 0,
        "totals": {
            "count": total_count,
            "amount_disp": total_amt_disp,
        },
    }


def pack_key_customers_tier_items(
    raw: dict | None, tier: str
) -> dict[str, Any]:
    """懒加载单档：items + monthly 显示串齐。"""
    from domain.key_customers.compute import TIER_ORDER, TIER_RANGE_DISP

    tier = (tier or "").strip().upper()
    if tier not in TIER_ORDER:
        raise ValueError("tier 须为 S|A|B|C|D|E")
    packed = pack_key_customers(raw, embed_full=True)
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
    }
