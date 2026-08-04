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


# 3.7.12：展示维残差行（吃掉列表与期间费用 total 的差额；可解释、禁止双计）
EXPENSE_RESIDUAL_CATEGORY = "其他/未归类"
EXPENSE_RESIDUAL_PC = "公共剩余/未摊"


def _fen_int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _with_expense_residual(
    rows: list[tuple[str, int, list]],
    total_fen: int,
    residual_name: str,
) -> list[tuple[str, int, list]]:
    """列表金额（分）与 total 守恒：缺口/溢出并入 residual_name 一行。"""
    rows = [(str(n), _fen_int(v), list(f or [])) for n, v, f in (rows or [])]
    s = sum(v for _, v, _ in rows)
    gap = _fen_int(total_fen) - s
    if gap != 0:
        rows.append((residual_name, gap, []))
    return rows


def _bu_expense_pc_rows(bu_pages: dict | None, pkey: str) -> list[tuple[str, int, list]]:
    """整体「按利润中心」= 各业务 BU 同 period 的 periods[pk].expense.total（分摊后实际承担）。"""
    if not bu_pages:
        return []
    rows: list[tuple[str, int, list]] = []
    for name, page in (bu_pages or {}).items():
        if not isinstance(page, dict):
            continue
        bsum = page.get("summary") if isinstance(page.get("summary"), dict) else None
        if not bsum:
            continue
        p = (bsum.get("periods") or {}).get(pkey) or {}
        if not isinstance(p, dict):
            continue
        tot = _fen_int((p.get("expense") or {}).get("total"))
        label = str(page.get("name") or name or "").strip() or str(name)
        if not label:
            continue
        rows.append((label, tot, []))
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows


def pack_expense_views_by_period(
    summary: dict,
    *,
    is_bu: bool = False,
    bu_pages: dict | None = None,
) -> dict[str, dict[str, Any]]:
    """期间费用构成横条（大类环形已有 donut_by_period）。

    3.7.12：
    - 看端不再下发 by_dept（部门展示维删除；数据层 dept 仍可存）。
    - BU 页不下发 by_pc（前端也不显示该 tab）。
    - 整体 by_pc = 各 bu_pages[bu].summary.periods[pk].expense.total（分摊后 SSOT），
      与台账直记 by_pc 半截路径二选一，禁止双轨。
    - by_category / 整体 by_pc 与 periods[pk].expense.total **展示守恒**（残差单列）。
    """
    import charts
    from viewmodels.format import _fine_to_rows

    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    out: dict[str, dict[str, Any]] = {}
    sink = frozenset(
        {
            "未分类",
            "未标注明细类型",
            EXPENSE_RESIDUAL_CATEGORY,
            EXPENSE_RESIDUAL_PC,
        }
    )

    def hbar(rows, prefix):
        if not rows:
            return []
        ordered = [r for r in rows if r[0] not in sink] + [r for r in rows if r[0] in sink]
        mx = max((_fen_int(v) for _, v, _ in rows), default=1) or 1
        items = []
        for name, val, fine in ordered:
            val_i = _fen_int(val)
            w = max(2.0, (abs(val_i) / mx) * 100.0) if mx else 2.0
            fine_lines = [
                {"name": str(n), "amt_disp": charts.fmt_wan(a) + "万"} for n, a in (fine or [])
            ]
            items.append(
                {
                    "key": f"{prefix}:{name}",
                    "name": str(name),
                    "value": val_i,
                    "amt_disp": charts.fmt_wan(val_i) + "万",
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
        total_fen = _fen_int(e.get("total"))
        fine_raw = _fine_to_rows(FT.get(pkey) or {})
        fine_rows = _with_expense_residual(
            [(n, _fen_int(v), f) for n, v, f in (fine_raw or [])],
            total_fen,
            EXPENSE_RESIDUAL_CATEGORY,
        )
        if is_bu:
            pc_rows: list[tuple[str, int, list]] = []
        else:
            pc_rows = _with_expense_residual(
                _bu_expense_pc_rows(bu_pages, pkey),
                total_fen,
                EXPENSE_RESIDUAL_PC,
            )
        out[pkey] = {
            "total_disp": charts.fmt_wan(total_fen) + "万",
            "total": total_fen,
            "by_category": hbar(fine_rows, "fine"),
            "by_pc": hbar(pc_rows, "pc"),
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



# ---------------------------------------------------------------------------
# 重点客户 / 完整性：实现迁至 feature 模块（3.5.0）；此处仅兼容门面 re-export
# ---------------------------------------------------------------------------
from viewmodels.integrity import pack_data_integrity  # noqa: E402,F401
from viewmodels.key_customers import (  # noqa: E402,F401
    pack_key_customers,
    pack_key_customers_tier_items,
)

__all__ = (
    "pack_key_customers",
    "pack_key_customers_tier_items",
    "pack_data_integrity",
)
