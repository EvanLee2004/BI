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


def pack_kpi_cards_by_period(summary: dict, cfg: dict | None = None) -> dict[str, list[dict[str, Any]]]:
    """周期 → KPI 卡数组（主数/副标/峰值/目标条/BU 进度全为显示串）。"""
    import charts
    from render_widgets import KPI_CARDS, _kpi_period_label, _kpi_val, _prev_period_key

    cfg = cfg or {}
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    year = meta.get("year")
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    out: dict[str, list[dict[str, Any]]] = {}

    def peak_for(key: str) -> dict[str, str] | None:
        if not month_keys:
            return None
        best_v, best_mk = None, None
        for mk in month_keys:
            if mk not in P:
                continue
            v = float(_kpi_val(P[mk], key) or 0.0)
            if best_v is None or v > best_v:
                best_v, best_mk = v, mk
        if best_v is None:
            return None
        if best_v == 0.0 and all(float(_kpi_val(P.get(mk) or {}, key) or 0.0) == 0.0 for mk in month_keys):
            return None
        lab = (
            best_mk.replace(f"{year}年", "")
            if isinstance(best_mk, str) and best_mk.startswith(f"{year}年")
            else str(best_mk)
        )
        return {"label": lab, "value_disp": charts.fmt_wan(best_v) + "万"}

    def target_bar(tkey, pkey, p) -> dict[str, Any] | None:
        if not budget or not tkey:
            return None
        use_h1 = ("1-6" in pkey) or pkey.endswith("1-6月") or ("1~6" in pkey)
        item, label = None, "年目标"
        if use_h1 and budget.get(f"{tkey}_h1"):
            item = budget[f"{tkey}_h1"]
            label = "H1目标"
        if item is None:
            item = budget.get(tkey)
            label = "年目标"
        if not item:
            return {"empty": True, "label": label}
        tgt, done, pct = item.get("target"), item.get("done"), item.get("pct")
        if tkey in ("margin", "pretax_margin"):
            if use_h1 and item.get("done") is not None:
                cur = item["done"]
            else:
                cur = p.get("gross_margin_pct" if tkey == "margin" else "pretax_margin_pct")
            cur_s = f"{cur:.1f}%" if cur is not None else "—"
            if pct is not None and pct > 999:
                pct_s = ">999% · 目标待校准"
            else:
                pct_s = f"{pct:.0f}%" if pct is not None else "—"
            w = min(max(pct or 0, 0), 100)
            cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
            return {
                "empty": False,
                "kind": "margin",
                "label": label,
                "tgt_disp": str(tgt),
                "cur_disp": cur_s,
                "pct_disp": pct_s,
                "bar_w": w,
                "cls": cls,
            }
        if done is None:
            done = _kpi_val(p, {"order": "orders", "receipt": "receipts"}.get(tkey, "orders"))
            pct = (done / tgt * 100.0) if tgt else None
        if pct is not None and pct > 999:
            pct_s = ">999% · 目标待校准"
        else:
            pct_s = f"{pct:.1f}%" if pct is not None else "—"
        w = min(max(pct or 0, 0), 100)
        cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
        return {
            "empty": False,
            "kind": "amount",
            "label": label,
            "tgt_disp": charts.fmt_wan(tgt) + "万",
            "done_disp": charts.fmt_wan(done) + "万",
            "pct_disp": pct_s,
            "bar_w": w,
            "cls": cls,
        }

    def bu_orders_rows(bu_list) -> list[dict[str, Any]]:
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

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        prev = _prev_period_key(pkey, year) if year else None
        period_tag = _kpi_period_label(pkey, year) if year else pkey
        cards = []
        for label, key, src, up_good, pctkey, _color, tkey in KPI_CARDS:
            val = float(_kpi_val(p, key) or 0.0)
            delta = {"show": False, "cls": "", "text": ""}
            if prev is not None and prev in P and _kpi_val(P[prev], key):
                pv = float(_kpi_val(P[prev], key) or 0.0)
                if pv:
                    d = (val - pv) / abs(pv) * 100
                    good = (d >= 0) == up_good
                    arrow = "▲" if d >= 0 else "▼"
                    delta = {
                        "show": True,
                        "cls": "up" if good else "down",
                        "text": f"{arrow}{abs(d):.1f}%",
                    }
            subs = []
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
            peak = peak_for(key)
            feet = []
            if peak:
                feet.append({"kind": "peak", "label": peak["label"], "value_disp": peak["value_disp"]})
            if key == "receipts" and show_ar:
                ar = float(p.get("revenue_gross") or 0.0) - val
                ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar))
                feet.append({"kind": "ar", "label": "已交付未回款", "value_disp": ar_s + "万"})
            cards.append(
                {
                    "label": label,
                    "period_tag": period_tag,
                    "value_disp": charts.fmt_wan(val),
                    "value_unit": "万",
                    "delta": delta,
                    "subs": subs,
                    "target": target_bar(tkey, pkey, p),
                    "bu_orders": bu_orders_rows(BUO.get(pkey)) if key == "orders" else [],
                    "feet": feet,
                    "src": src,
                    "data_key": key,
                }
            )
        out[pkey] = cards
    return out


def _fine_pairs(fine_pairs, limit=8) -> list[dict[str, Any]]:
    pairs = sorted(fine_pairs or [], key=lambda x: -x[1])
    lines = []
    for n, a in pairs[:limit]:
        lines.append({"name": str(n), "amt_disp": _abs_amt_disp(a), "sub": True, "kind": ""})
    rest = pairs[limit:]
    if rest:
        lines.append(
            {
                "name": f"其他{len(rest)}项",
                "amt_disp": _abs_amt_disp(sum(a for _, a in rest)),
                "sub": True,
                "kind": "",
            }
        )
    return lines


def pack_pl_by_period(summary: dict, *, is_bu: bool = False) -> dict[str, dict[str, Any]]:
    """周期 → {rows, details} 结构化利润表。"""
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    yk = meta.get("year_key") or ""
    unc = (meta.get("unclassified") or {}).get("expense") or {}
    unc_amt = float(unc.get("amount") or 0) if unc else 0.0
    out: dict[str, dict[str, Any]] = {}

    def line(name, impact, *, kind="", formula="", open_key=None, total=False, grand=False, is_pct=False, pct=None):
        if is_pct:
            txt = f"{pct:.1f}%" if pct is not None else "—"
            return {
                "name": name,
                "amt_disp": txt,
                "kind": kind,
                "formula": formula,
                "open_key": None,
                "total": False,
                "grand": False,
                "is_pct": True,
            }
        return {
            "name": name,
            "amt_disp": _amt_disp(impact),
            "kind": kind,
            "formula": formula,
            "open_key": open_key,
            "total": total,
            "grand": grand,
            "is_pct": False,
        }

    def dline(name, impact, kind="", sub=False):
        return {"name": name, "amt_disp": _abs_amt_disp(impact), "kind": kind, "sub": sub}

    for pkey, p in P.items():
        if not isinstance(p, dict):
            continue
        e = p.get("expense") or {}
        man = p.get("manual") or {}
        led = p.get("ledger_expenses") or {}
        fine = FT.get(pkey) or {}
        rows = []
        details: dict[str, dict[str, Any]] = {}

        rows.append(line("交付收入（不含税）", p.get("revenue_net"), kind="system", formula="交付金额÷1.06"))
        rows.append(line("交付成本（生产成本）", -float(p.get("production_cost") or 0), open_key="cost"))
        rows.append(line("管理毛利", p.get("gross_profit"), total=True))

        prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
        cost_lines = [
            dline("系统直接成本", p.get("system_direct_cost"), "system"),
            dline("系统内部译员", abs(float(p.get("inhouse_cost") or 0)), "system"),
            dline("直接成本增值税", man.get("直接成本增值税", 0.0), "manual"),
        ]
        for n in prod_manual:
            cost_lines.append(dline(n, man.get(n, 0.0), "manual"))
        details["cost"] = {"title": "交付成本（生产成本）构成", "lines": cost_lines}

        if is_bu:
            alloc = meta.get("public_allocation") or {"enabled": False}
            alloc_added = p.get("alloc_added") or {}
            groups = (
                ("sales", "营销费用", "营销人力成本", "市场费用"),
                ("admin", "管理费用", "管理人力成本", "管理费用"),
                ("fixed", "固定运营费用", None, "固定运营费用"),
                ("rd", "研发费用", "研发人力成本", "技术服务费"),
                ("fin", "财务费用", None, "财务费用"),
            )
            for cat_key, nm, man_key, led_cat in groups:
                v = float(e.get(nm) or 0)
                rows.append(line(nm, -v, open_key=cat_key))
                alloc_amt = float(alloc_added.get(led_cat) or 0.0)
                direct_amt = round(float(led.get(led_cat) or 0.0) - alloc_amt, 2)
                lines = []
                if man_key:
                    lines.append(dline(man_key, man.get(man_key, 0), "manual"))
                lines.append(dline(led_cat, direct_amt, "ledger"))
                lines.extend(_fine_pairs(fine.get(led_cat)))
                if nm == "财务费用":
                    lines.append(dline("财务费用补充", man.get("财务费用补充", 0), "manual"))
                if alloc_amt > 0.005:
                    lines.append(dline("分摊自公共", alloc_amt, "ledger"))
                details[cat_key] = {"title": f"{nm}构成", "lines": lines}
        else:
            # 整体页
            rows.append(line("营销费用", -float(e.get("营销费用") or 0), open_key="sales"))
            rows.append(line("管理费用", -float(e.get("管理费用") or 0), open_key="admin"))
            rows.append(line("固定运营费用", -float(e.get("固定运营费用") or 0), open_key="fixed"))
            rows.append(line("研发费用", -float(e.get("研发费用") or 0), open_key="rd"))
            rows.append(line("财务费用", -float(e.get("财务费用") or 0), open_key="fin"))

            def led_block(title_led, amount, fine_key, extra_before=None, extra_after=None):
                lines = list(extra_before or [])
                lines.append(dline(title_led, amount, "ledger"))
                lines.extend(_fine_pairs(fine.get(fine_key)))
                lines.extend(extra_after or [])
                return lines

            details["sales"] = {
                "title": "营销费用构成",
                "lines": led_block(
                    "市场费用",
                    led.get("市场费用", 0),
                    "市场费用",
                    extra_before=[dline("营销人力成本", man.get("营销人力成本", 0), "manual")],
                ),
            }
            details["admin"] = {
                "title": "管理费用构成",
                "lines": led_block(
                    "管理费用",
                    led.get("管理费用", 0),
                    "管理费用",
                    extra_before=[dline("管理人力成本", man.get("管理人力成本", 0), "manual")],
                ),
            }
            details["fixed"] = {
                "title": "固定运营费用构成",
                "lines": led_block("固定运营费用明细", led.get("固定运营费用", 0), "固定运营费用"),
            }
            details["rd"] = {
                "title": "研发费用构成",
                "lines": led_block(
                    "技术服务费",
                    led.get("技术服务费", 0),
                    "技术服务费",
                    extra_before=[dline("研发人力成本", man.get("研发人力成本", 0), "manual")],
                ),
            }
            details["fin"] = {
                "title": "财务费用构成",
                "lines": led_block(
                    "财务费用",
                    led.get("财务费用", 0),
                    "财务费用",
                    extra_after=[dline("财务费用补充", man.get("财务费用补充", 0), "manual")],
                ),
            }

        rows.append(line("附加税费", -float(p.get("surtax") or 0), kind="system", formula="净收入×6%×12%"))
        rows.append(line("其他损益", p.get("other_pl"), kind="manual"))
        if (not is_bu) and unc_amt > 0 and pkey == yk:
            rows.append(line("未计入费用（台账未填大类）", -unc_amt, kind="ledger"))
        rows.append(
            line(
                "税前利润",
                p.get("pretax_profit"),
                grand=True,
                formula="管理毛利−期间费用−附加税±其他",
            )
        )
        rows.append(
            line(
                "税前利润率",
                0,
                is_pct=True,
                pct=p.get("pretax_margin_pct"),
                formula="税前利润÷交付收入",
            )
        )
        out[pkey] = {"rows": rows, "details": details}
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
    """Y 轴刻度：[{value, label}] 后端算好，前端 axisLabel 只查表。修复 000,000 bug。"""
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
