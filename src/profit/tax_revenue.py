#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit._impl 原 profit.py 正文（54.4·E 搬家）。经营利润计算：年/季/月全周期矩阵，算到「税前利润」。全部在 Python 算完，前端不做任何金额运算。

口径（陆总 2026-07-03 定稿 + 2026-07 完善）：
- 收入(不含税) = Σ交付额/本币 ÷ (1+税率)，按整单交付日期。
- 生产成本 = 系统直接成本(项目成本) − 系统内部译员成本(in-house本币结算) + 手填6项(PM/VM/实际内部译员/税费损失/技术流量/其他)。
- 毛利(管理/完整) = 收入 − 生产成本。 结构板块「项目直接毛利」= 收入 − 项目成本（未含内译/手填）。
- 营销费用 = 营销人力成本(手填) + 市场费用(台账)；管理费用 = 管理人力成本(手填) + 管理费用(台账)；
  固定运营费用(台账)；研发费用 = 研发人力成本(手填) + 技术服务费(台账)；
  财务费用 = 财务费用(台账) + 财务费用补充(手填)。
- 附加税费 = 增值税额 × 附加税率（管理估算·非税务实缴；增值税=不含税收入×6%，附加=×12%）。
- 其他损益(手填，默认0)。
- 税前利润 = 毛利 − 营销 − 管理 − 固定运营 − 研发 − 财务 − 附加税费 + 其他损益。
- 手填项：某月没填 → 0（不再沿用上月）；年/季 = 期间内各月之和。
- 回款/下单比 = 本期回款 ÷ 本期下单（资金节奏，非当月回收率）。
- BU 页费用：台账「利润归属中心」直记本 BU + 公共池×分摊比例（可选）；手填可按 BU 范围。
"""

from __future__ import annotations


import loaders
import periods
import money


# pure-move funcs from _impl.py

def split_tax(gross_fen: int, vat_rate: float) -> dict[str, int]:
    """增值税拆分。入参/出参均为**分**。

    任务书66·A：在分上 Decimal 除法 + ROUND_HALF_UP（弃 fen→元 float→round→分）。
    net = gross / (1+vat_rate)；vat = gross - net（守恒）。
    """
    if not gross_fen:
        return {"revenue_gross": 0, "revenue_net": 0, "vat": 0}
    from decimal import Decimal

    g = int(gross_fen)
    net = money.divide_fen(g, Decimal(1) + Decimal(str(vat_rate)))
    return {
        "revenue_gross": g,
        "revenue_net": net,
        "vat": g - net,
    }


def compute_revenue_cost(project_rows, cols_cfg, start, end, vat_rate):
    dcol, rcol, ccol = cols_cfg["project_delivery_date"], cols_cfg["project_revenue"], cols_cfg["project_cost"]
    matched = [r for r in project_rows if periods.date_in_range(loaders.parse_date_parts(r.get(dcol)), start, end)]
    gross = sum(money.as_fen(r.get(rcol)) for r in matched)
    cost = sum(money.as_fen(r.get(ccol)) for r in matched)
    tax = split_tax(gross, vat_rate)
    return {**tax, "delivery_count": len(matched), "system_direct_cost": int(cost)}


def _sum_amount_in_period(rows, amount_col, date_col, start, end, extra=None):
    tot = 0
    for r in rows:
        if extra and not extra(r):
            continue
        if periods.date_in_range(loaders.parse_date_parts(r.get(date_col)), start, end):
            tot += money.as_fen(r.get(amount_col))
    return int(tot)


def compute_orders(order_rows, cols_cfg, start, end):
    return _sum_amount_in_period(order_rows, cols_cfg["order_amount"], cols_cfg["order_date"], start, end)


def compute_receipts(receipt_rows, cols_cfg, start, end):
    return _sum_amount_in_period(receipt_rows, cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end)


def compute_name_month_totals(rows, name_col, amount_col, date_col, year: int, names) -> dict[str, list[float]]:
    """主体 × 1~12 月金额矩阵（纯数）。只汇总 names 内主体、且日期年=year 的行。
    返回 {name: [m1..m12]}，缺月为 0.0；amount 已 round(2)。
    陆总#8：排名行点开看各月下单/回款——在 build_period 预算，views 挂显示串。"""
    want = {str(n) for n in (names or []) if n}
    if not want:
        return {}
    acc: dict[str, list[float]] = {n: [0.0] * 12 for n in want}
    for r in rows or []:
        d = loaders.parse_date_parts(r.get(date_col))
        if not d or int(d[0]) != int(year):
            continue
        m = int(d[1])
        if m < 1 or m > 12:
            continue
        n = str(r.get(name_col) or "").strip()
        if n not in want:
            continue
        acc[n][m - 1] += money.as_fen(r.get(amount_col))
    return {n: [round(v, 2) for v in vals] for n, vals in acc.items()}


def _ranking_entity_names(*rks) -> list[str]:
    """从若干 ranking 结果取主体名单（full_items 优先；排除未填）。保序去重。"""
    names: list[str] = []
    seen: set[str] = set()
    for rk in rks:
        for it in (rk or {}).get("full_items") or (rk or {}).get("items") or []:
            n = str(it.get("name") or "").strip()
            if not n or n == "（未填）" or n in seen:
                continue
            seen.add(n)
            names.append(n)
    return names


def build_rankings_monthly(order_rows, receipt_rows, cols_cfg, year: int, rankings: dict) -> dict:
    """排名主体（销售/客户）全年 1~12 月下单+回款矩阵。只挂出现在排名里的名字（top+其余全量）。"""
    rk = rankings or {}
    sales_names = _ranking_entity_names(rk.get("orders_by_sales"), rk.get("receipts_by_sales"))
    cust_names = _ranking_entity_names(rk.get("orders_by_customer"), rk.get("receipts_by_customer"))
    o_col, o_date = cols_cfg["order_amount"], cols_cfg["order_date"]
    r_col, r_date = cols_cfg["receipt_amount"], cols_cfg["receipt_date"]
    so = compute_name_month_totals(order_rows, "销售", o_col, o_date, year, sales_names)
    sr = compute_name_month_totals(receipt_rows, "销售", r_col, r_date, year, sales_names)
    co = compute_name_month_totals(order_rows, "客户", o_col, o_date, year, cust_names)
    cr = compute_name_month_totals(receipt_rows, "客户", r_col, r_date, year, cust_names)

    def pack(names, o_map, r_map):
        out = {}
        for n in names:
            out[n] = {
                "order": o_map.get(n) or [0.0] * 12,
                "receipt": r_map.get(n) or [0.0] * 12,
            }
        return out

    return {
        "year": int(year),
        "sales": pack(sales_names, so, sr),
        "customer": pack(cust_names, co, cr),
    }


def compute_ranking(rows, name_col, amount_col, date_col, start, end, top=10, empty_label="（未填）", name_of=None):
    """按 name_col 汇总期内金额并降序排名。返回 {items:[{name,amount,count}…前top], others:{names,amount,count}|None,
    unfilled:{amount,count}|None, total}。count=笔数；amount 已 round(2)。
    名字为空归"（未填）"→ 单拆 unfilled 固定置底展示（不参与前top排位，但计入 total=守恒：各组合计==总额）。
    name_of=可选 callable(row)->str：派生分组名（如 销售→BU 映射·陆总0714）；返回空串归 empty_label。"""
    agg: dict[str, list] = {}
    for r in rows:
        if not periods.date_in_range(loaders.parse_date_parts(r.get(date_col)), start, end):
            continue
        raw_name = name_of(r) if name_of else r.get(name_col)
        name = str(raw_name or "").strip() or empty_label
        a = agg.setdefault(name, [0.0, 0])
        a[0] += money.as_fen(r.get(amount_col))
        a[1] += 1
    total = round(sum(v[0] for v in agg.values()), 2)
    uf = agg.pop(empty_label, None)
    unfilled = {"amount": round(uf[0], 2), "count": uf[1]} if uf else None
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])
    full_items = [{"name": n, "amount": round(v[0], 2), "count": v[1]} for n, v in ranked]
    items = full_items[:top]
    rest = ranked[top:]
    others = (
        {"names": len(rest), "amount": round(sum(v[0] for _, v in rest), 2), "count": sum(v[1] for _, v in rest)}
        if rest
        else None
    )
    # full_items：完整排序（供 BU 页「其余」本地展开，不调全公司 /api/daily·铁律12）
    return {"items": items, "others": others, "unfilled": unfilled, "total": total, "full_items": full_items}


def compute_profit_ranking(
    project_rows, name_col, cols_cfg, start, end, vat_rate, top=10, conc_k=5, empty_label="（未填）"
):
    """按 name_col（客户/销售）汇总期内**确认收入与项目毛利**并按收入降序排名（收入结构板块用）。
    口径：收入(不含税)=Σ交付额÷(1+vat)；毛利=收入−Σ项目成本（**项目直接毛利**，未含内部译员/手填调整，
    故各组毛利之和与利润表总毛利有差异——footer 已注明）；毛利率=毛利÷收入。
    返回 {items:[{name,revenue,profit,margin_pct,count}…前top], others:{names,revenue,profit,margin_pct,count}|None,
          unfilled:{…}|None, total_revenue, total_profit, conc_k, conc_pct(前 conc_k 大占收入%)}。
    名字空→"（未填）"置底（不参与前 top 排位、计入 total=守恒）。纯函数、只吃行，前端零运算（铁律2 在 render 里成串）。"""
    dcol, rcol, ccol = cols_cfg["project_delivery_date"], cols_cfg["project_revenue"], cols_cfg["project_cost"]
    agg: dict[str, list] = {}  # name -> [Σ含税交付额分, Σ项目成本分, 笔数]
    for r in project_rows:
        if not periods.date_in_range(loaders.parse_date_parts(r.get(dcol)), start, end):
            continue
        name = str(r.get(name_col) or "").strip() or empty_label
        a = agg.setdefault(name, [0, 0, 0])
        a[0] += money.as_fen(r.get(rcol))
        a[1] += money.as_fen(r.get(ccol))
        a[2] += 1

    def _row(name, g):
        rev = split_tax(int(g[0]), vat_rate)["revenue_net"]  # 分
        prof = int(rev - g[1])
        return {
            "name": name,
            "revenue": rev,
            "profit": prof,
            "margin_pct": round(prof / rev * 100, 1) if rev else None,
            # 系统成本率=Σ项目成本÷收入（陆总0714：业务侧习惯看成本率，展示层用它替代"项目毛利率"）
            "cost_pct": round(g[1] / rev * 100, 1) if rev else None,
            "count": g[2],
        }

    def _agg_row(name, gs):  # 合并多组（其余/合计）后再算率，避免率的加权错误
        tot = [sum(x[0] for x in gs), sum(x[1] for x in gs), sum(x[2] for x in gs)]
        return _row(name, tot)

    total_rev = split_tax(int(sum(g[0] for g in agg.values())), vat_rate)["revenue_net"]
    total_prof = int(sum(split_tax(int(g[0]), vat_rate)["revenue_net"] - g[1] for g in agg.values()))
    uf = agg.pop(empty_label, None)
    unfilled = _row(empty_label, uf) if uf else None
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])  # 按含税交付额降序＝按收入降序（div 恒正）
    full_items = [_row(n, g) for n, g in ranked]
    items = full_items[:top]
    rest = [g for _, g in ranked[top:]]
    others = _agg_row(f"其余 {len(rest)} 个", rest) if rest else None
    if others:
        others["names"] = len(rest)
    # 集中度=前 conc_k 大不含税收入 / 总不含税收入（分/分）
    conc_rev = sum(split_tax(int(g[0]), vat_rate)["revenue_net"] for _, g in ranked[:conc_k])
    conc_pct = round(conc_rev / total_rev * 100, 1) if total_rev else None
    # full_items：完整排序（供 BU 页「其余」本地展开，不调 /api/profit_ranking·铁律12）
    return {
        "items": items,
        "others": others,
        "unfilled": unfilled,
        "total_revenue": total_rev,
        "total_profit": total_prof,
        "conc_k": conc_k,
        "conc_pct": conc_pct,
        "full_items": full_items,
    }


