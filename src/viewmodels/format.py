#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON/VM 显示与格式化辅助（2.7.9 G4：自 HTML 装运层迁出，业务路径不依赖该层）。

纯函数、无 I/O、不依赖 render*.py。HTML 侧可 re-export 保持兼容。
"""

from __future__ import annotations

import copy

import charts

# ---------- KPI 卡元数据（原 render_widgets）----------
# (标签, 取值键, 来源, 涨为好, 附率键, 趋势线色, 目标键)
KPI_CARDS = [
    ("下单", "orders", "智云·下单预估额", True, None, "var(--purple)", "order"),
    ("交付金额", "revenue_gross", "智云直接抓·含税 · 确认口径÷1.06见脚注", True, None, "var(--blue)", None),
    ("毛利率", "gross_profit", "完整口径·交付收入−生产成本", True, "gross_margin_pct", "var(--orange)", "margin"),
    (
        "税前利润",
        "pretax_profit",
        "毛利−各项费用−附加税±其他",
        True,
        "pretax_margin_pct",
        "var(--pos)",
        "pretax_margin",
    ),
    ("回款", "receipts", "智云·回款(到账)", True, None, "var(--teal)", "receipt"),
]


def _esc(s) -> str:
    """HTML 转义（与 charts.esc / 原 render._esc 同口径）。"""
    return charts.esc(s)


def _kpi_val(p, key):
    """KPI 取值：一律取 period 已算好的字段（不做派生聚合）。"""
    return p[key]


def _prev_period_key(pkey, year):
    """环比的上一同粒度周期 key：年→无；季→上季；月→上月。"""
    yk = f"{year}年"
    if pkey == yk:
        return None
    if "Q" in pkey:
        q = int(pkey.split("Q")[1])
        return f"{yk}Q{q - 1}" if q > 1 else None
    mpart = pkey.split("年")[1].replace("月", "")
    if "-" in mpart:
        return None
    m = int(mpart)
    return f"{yk}{m - 1}月" if m > 1 else None


def _kpi_period_label(pkey, year):
    """基本情况卡头旁的时段角标。"""
    yk = f"{year}年"
    if pkey == yk:
        return yk
    if isinstance(pkey, str) and pkey.startswith(yk):
        rest = pkey[len(yk) :]
        return rest or yk
    return str(pkey or yk)


def _rank_amt(v) -> str:
    """排名金额显示：负数用全角负号 + 万。"""
    return ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"


def _months_for_period_key(key: str, year_key: str) -> list[int]:
    """单个周期 key → 月份列表。"""
    if not key or key == year_key or (key.endswith("年") and "Q" not in key and "月" not in key):
        return list(range(1, 13))
    try:
        rest = key.split("年", 1)[1]
    except IndexError:
        return list(range(1, 13))
    if rest.startswith("Q"):
        q = int(rest[1:])
        sm = (q - 1) * 3 + 1
        return [sm, sm + 1, sm + 2]
    if rest.endswith("月"):
        body = rest[:-1]
        if "-" in body:
            a, b = body.split("-", 1)
            return list(range(int(a), int(b) + 1))
        return [int(body)]
    return list(range(1, 13))


def _period_months_map(summary) -> dict[str, list[int]]:
    """周期 key → 应高亮的月份列表。"""
    meta = summary.get("meta") or {}
    yk = meta.get("year_key") or ""
    groups = meta.get("tab_groups") or {}
    keys = [yk] + list(groups.get("季度") or []) + list(groups.get("月") or []) + list(groups.get("区间") or [])
    seen, ordered = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            ordered.append(k)
    return {k: _months_for_period_key(k, yk) for k in ordered}


def _fine_to_rows(fine_k):
    """{大类:[(细类,金额)…]} → 按类别横条行 [(细类,合计,[(大类,金额)…])…]。"""
    if not fine_k:
        return []
    agg: dict[str, float] = {}
    src: dict[str, list] = {}
    for cat, pairs in fine_k.items():
        for name, amt in pairs or []:
            agg[name] = agg.get(name, 0.0) + float(amt)
            src.setdefault(name, []).append((cat, float(amt)))
    rows = [(n, round(v, 2), sorted(src[n], key=lambda x: -x[1])) for n, v in agg.items()]
    rows.sort(key=lambda r: -r[1])
    return rows


def _merge_dual_rank(o_rk, r_rk, top=10):
    """合并下单/回款排名为双血条主体列表。金额与宽度后端算好。"""
    o_map = {it["name"]: it for it in (o_rk or {}).get("full_items") or (o_rk or {}).get("items") or []}
    r_map = {it["name"]: it for it in (r_rk or {}).get("full_items") or (r_rk or {}).get("items") or []}
    names = []
    seen = set()
    for src in (o_rk or {}).get("full_items") or (o_rk or {}).get("items") or []:
        n = src["name"]
        if n and n not in seen and n != "（未填）":
            seen.add(n)
            names.append(n)
    for src in (r_rk or {}).get("full_items") or (r_rk or {}).get("items") or []:
        n = src["name"]
        if n and n not in seen and n != "（未填）":
            seen.add(n)
            names.append(n)

    def score(n):
        return float((o_map.get(n) or {}).get("amount") or 0)

    names.sort(key=score, reverse=True)
    full = []
    for n in names:
        oa = float((o_map.get(n) or {}).get("amount") or 0)
        ra = float((r_map.get(n) or {}).get("amount") or 0)
        full.append({"name": n, "order": oa, "receipt": ra, "order_disp": _rank_amt(oa), "receipt_disp": _rank_amt(ra)})
    items = full[:top]
    rest = full[top:]
    others = None
    if rest:
        others = {
            "names": len(rest),
            "order": round(sum(x["order"] for x in rest), 2),
            "receipt": round(sum(x["receipt"] for x in rest), 2),
            "order_disp": _rank_amt(sum(x["order"] for x in rest)),
            "receipt_disp": _rank_amt(sum(x["receipt"] for x in rest)),
        }
    mx = max((max(x["order"], x["receipt"]) for x in full), default=0) or 1
    for x in items:
        x["wo"] = max(x["order"] / mx * 100, 0)
        x["wr"] = max(x["receipt"] / mx * 100, 0)
    return {"items": items, "others": others, "full_items": full, "mx": mx}


def monthly_mkey(year, dim: str, name: str) -> str:
    """页面级月度字典键：年|维|主体。"""
    label = "销售" if dim == "sales" else "客户"
    try:
        y = int(year or 0)
    except (TypeError, ValueError):
        y = 0
    return f"{y}|{label}|{name}"


def _monthly_dual_rows(name: str, series: dict | None) -> list[dict]:
    """主体 1~12 月双血条显示串。"""
    _ = name
    series = series or {}
    o = list(series.get("order") or [0.0] * 12)
    r = list(series.get("receipt") or [0.0] * 12)
    while len(o) < 12:
        o.append(0.0)
    while len(r) < 12:
        r.append(0.0)
    o, r = o[:12], r[:12]
    mx = max([max(float(o[i]), float(r[i])) for i in range(12)] + [0.0]) or 1.0
    out = []
    for i in range(12):
        oa, ra = float(o[i] or 0), float(r[i] or 0)
        out.append(
            {
                "i": i + 1,
                "name": f"{i + 1}月",
                "order": oa,
                "receipt": ra,
                "order_disp": _rank_amt(oa),
                "receipt_disp": _rank_amt(ra),
                "wo": round(max(oa / mx * 100, 0), 1),
                "wr": round(max(ra / mx * 100, 0), 1),
            }
        )
    return out


def _json_num(v) -> float | int:
    """JSON 数：整值出 int。"""
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return 0
    if f == int(f):
        return int(f)
    return round(f, 1)


def compact_monthly_display(monthly) -> list[dict]:
    """入库/页面级字典用紧凑显示串。"""
    rows = []
    for m in monthly or []:
        rows.append(
            {
                "i": _json_num(m.get("i")),
                "name": m.get("name"),
                "wo": _json_num(m.get("wo")),
                "wr": _json_num(m.get("wr")),
                "order_disp": m.get("order_disp") or _rank_amt(m.get("order") or 0),
                "receipt_disp": m.get("receipt_disp") or _rank_amt(m.get("receipt") or 0),
            }
        )
    return rows


def attach_monthly_to_dual(
    dual: dict,
    monthly_dim: dict | None,
    *,
    year: int = 0,
    dim: str = "sales",
    store: dict | None = None,
) -> dict:
    """rankings_monthly 某维归一：items 只挂 mkey；完整 12 月显示串写入 store。"""
    monthly_dim = monthly_dim or {}
    if store is None:
        store = {}

    def _one(it: dict) -> None:
        name = it.get("name") or ""
        mkey = monthly_mkey(year, dim, name)
        it["mkey"] = mkey
        it.pop("monthly", None)
        if mkey not in store:
            full = _monthly_dual_rows(name, monthly_dim.get(name))
            store[mkey] = compact_monthly_display(full)

    for it in dual.get("items") or []:
        _one(it)
    for it in dual.get("full_items") or []:
        _one(it)
    return dual


def dual_rankings_from_daily(rankings: dict, top: int = 10) -> dict:
    """日查四维单血条 → 双血条两卡就绪结构。"""
    dual_s = _merge_dual_rank(rankings.get("orders_by_sales"), rankings.get("receipts_by_sales"), top=top)
    dual_c = _merge_dual_rank(rankings.get("orders_by_customer"), rankings.get("receipts_by_customer"), top=top)

    def pack(dual, title, dim):
        items = []
        for i, it in enumerate(dual.get("items") or [], 1):
            items.append(
                {
                    "i": i,
                    "name": it["name"],
                    "wo": round(it.get("wo") or 0, 1),
                    "wr": round(it.get("wr") or 0, 1),
                    "order_disp": it.get("order_disp") or _rank_amt(it.get("order") or 0),
                    "receipt_disp": it.get("receipt_disp") or _rank_amt(it.get("receipt") or 0),
                    "mkey": "",
                }
            )
        others = dual.get("others")
        others_out = None
        if others:
            others_out = {
                "names": others["names"],
                "amt": (
                    f"下单{others.get('order_disp') or _rank_amt(others.get('order') or 0)}"
                    f" / 回款{others.get('receipt_disp') or _rank_amt(others.get('receipt') or 0)}"
                ),
                "count": others["names"],
            }
        full_out = []
        full_src = dual.get("full_items") or dual.get("items") or []
        mx = dual.get("mx") or 1 or 1
        for i, it in enumerate(full_src, 1):
            oa = float(it.get("order") or 0)
            ra = float(it.get("receipt") or 0)
            full_out.append(
                {
                    "i": i,
                    "name": it["name"],
                    "wo": round(max(oa / mx * 100, 0), 1),
                    "wr": round(max(ra / mx * 100, 0), 1),
                    "order_disp": it.get("order_disp") or _rank_amt(oa),
                    "receipt_disp": it.get("receipt_disp") or _rank_amt(ra),
                    "mkey": "",
                }
            )
        return {
            "title": title,
            "dim": dim,
            "items": items,
            "others": others_out,
            "empty": not items,
            "embed_full": bool(others),
            "full_items": full_out if others else [],
        }

    return {
        "sales": pack(dual_s, "下单/回款 · 按销售", "sales"),
        "customer": pack(dual_c, "下单/回款 · 按客户", "customer"),
        "monthly_drill": False,
    }


def expense_monthly_from_period_ledgers(summary: dict) -> dict:
    """从各月周期 ledger_expenses 拼 1~12 矩阵。"""
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    cats: list[str] = []
    by_m: dict[int, dict[str, float]] = {m: {} for m in range(1, 13)}
    for k in month_keys:
        try:
            rest = k.split("年", 1)[1]
            m = int(rest.replace("月", "").split("-")[0]) if rest.endswith("月") else 0
        except (IndexError, ValueError):
            m = 0
        if m < 1 or m > 12:
            continue
        led = (P.get(k) or {}).get("ledger_expenses") or {}
        for c, v in led.items():
            if not c:
                continue
            if c not in cats:
                cats.append(c)
            by_m[m][c] = round(float(v or 0), 2)
    months = []
    for m in range(1, 13):
        bc = {c: float(by_m[m].get(c) or 0) for c in cats}
        months.append({"m": m, "total": round(sum(bc.values()), 2), "by_cat": bc})
    return {"categories": cats, "months": months, "salary_merged": False, "note": ""}


def apply_expense_salary_hide(raw: dict | None, hide_salary: bool) -> dict | None:
    """整体页：隐工资 → 并入「其他」（仅显示层副本）。"""
    if not raw:
        return raw
    if not hide_salary or "工资" not in (raw.get("categories") or []):
        return raw
    out = copy.deepcopy(raw)
    cats = [c for c in out.get("categories") or [] if c != "工资"]
    if "其他" not in cats:
        cats.append("其他")
    for m in out.get("months") or []:
        bc = dict(m.get("by_cat") or {})
        sal = float(bc.pop("工资", 0) or 0)
        if sal:
            bc["其他"] = round(float(bc.get("其他") or 0) + sal, 2)
        m["by_cat"] = bc
        m["total"] = round(sum(float(bc.get(c) or 0) for c in cats), 2)
    out["categories"] = cats
    out["salary_merged"] = True
    out["note"] = "工资大类已并入「其他」（全端隐藏，不单列）"
    return out


# 公开别名（无下划线，供外部清晰引用）
esc = _esc
rank_amt = _rank_amt
merge_dual_rank = _merge_dual_rank
period_months_map = _period_months_map
fine_to_rows = _fine_to_rows
kpi_val = _kpi_val
prev_period_key = _prev_period_key
kpi_period_label = _kpi_period_label

__all__ = [
    "KPI_CARDS",
    "_esc",
    "esc",
    "_kpi_val",
    "kpi_val",
    "_prev_period_key",
    "prev_period_key",
    "_kpi_period_label",
    "kpi_period_label",
    "_rank_amt",
    "rank_amt",
    "_period_months_map",
    "period_months_map",
    "_months_for_period_key",
    "_fine_to_rows",
    "fine_to_rows",
    "_merge_dual_rank",
    "merge_dual_rank",
    "monthly_mkey",
    "_monthly_dual_rows",
    "compact_monthly_display",
    "attach_monthly_to_dual",
    "dual_rankings_from_daily",
    "expense_monthly_from_period_ledgers",
    "apply_expense_salary_hide",
]
