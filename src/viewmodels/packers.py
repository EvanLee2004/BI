#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书50·B：各板块结构化显示字段（*_disp + 条宽数值），前端零金额运算。

与 render.* 同源口径；body_by_period HTML 仍由 build_*_views 产出（legacy/deprecated）。
"""

from __future__ import annotations

from typing import Any


def _wan(v) -> str:
    import charts

    return charts.fmt_wan(float(v or 0))


def _amt_disp(v) -> str:
    """利润表金额显示串：带符号万元。"""
    v = float(v or 0)
    sign = "−" if v < 0 else ""
    return sign + _wan(abs(v)) + "万"


def _abs_amt_disp(v) -> str:
    return _wan(abs(float(v or 0))) + "万"


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
        subs.append({"label": "交付收入(÷1.06)", "value_disp": charts.fmt_wan(p["revenue_net"]) + "万"})
        o = float(p.get("orders") or 0.0)
        if o > 0:
            subs.append({"label": "交付占下单", "value_disp": f"{val / o * 100:.0f}%"})
    elif pctkey == "gross_margin_pct":
        subs.append({"label": "毛利率", "value_disp": f"{p[pctkey]:.1f}%"})
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
        feet.append({"kind": "peak", "label": peak["label"], "value_disp": peak["value_disp"]})
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
    from render_widgets import KPI_CARDS, _kpi_period_label, _kpi_val, _prev_period_key

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
            cards.append(
                {
                    "label": label,
                    "period_tag": period_tag,
                    "value_disp": charts.fmt_wan(val),
                    "value_unit": "万",
                    "delta": _kpi_delta(val, prev, P, key, up_good, _kpi_val),
                    "subs": _kpi_subs(key, pctkey, p, val, charts),
                    "target": kpi_target_bar(tkey, pkey, p, budget),
                    "bu_orders": _kpi_bu_orders_rows(BUO.get(pkey), charts) if key == "orders" else [],
                    "feet": _kpi_feet(key, p, val, kpi_peak_for(summary, key), show_ar, charts),
                    "src": src,
                    "data_key": key,
                }
            )
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
                    "margin_disp": (f"{it.get('cost_pct'):.1f}%" if show_meta and it.get("cost_pct") is not None else ""),
                    "bar_w": max(2.0, rev / mx * 100) if rev else 0,
                }
            )
        others = rk.get("others")
        others_out = None
        if others:
            others_out = {
                "names": others.get("names"),
                "amt_disp": charts.fmt_wan(others.get("revenue") or 0) + "万",
                "margin_disp": (
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
                        "margin_disp": (
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
    import render

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
        fine_rows = render._fine_to_rows(FT.get(pkey) or {})
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
    import render

    meta = summary.get("meta") or {}
    year = int(meta.get("year") or 2026)
    yk = meta.get("year_key") or ""
    out: dict[str, dict[str, str]] = {}
    for k, months in (render._period_months_map(summary) or {}).items():
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


def pack_daily_defaults(summary: dict) -> dict[str, Any]:
    """按时间段查询默认日期与年。"""
    meta = summary.get("meta") or {}
    y = meta.get("year") or 2026
    return {
        "year": y,
        "default_start": f"{y}-01-01",
        "default_end": f"{y}-12-31",
        "year_key": meta.get("year_key") or f"{y}年",
    }
