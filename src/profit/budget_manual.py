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


import periods
import money

from .expense_period import compute_inhouse_cost, compute_ledger_expenses, manual_alloc_amounts_by_cat
from .tax_revenue import build_rankings_monthly, compute_orders, compute_profit_ranking, compute_ranking, compute_receipts, compute_revenue_cost


# pure-move funcs from _impl.py

def build_manual_monthly(cfg, manual_raw: dict, year: int, cur_month: int) -> dict[tuple[int, int], dict[str, float]]:
    """把手填表补成每月一份（1..cur_month）。
    default=zero（现行）：缺月/缺项 = 0，不再沿用上月（陆总当月必填）。
    default=prev：兼容旧配置，缺则取上月。"""
    items = cfg["manual_items"]
    filled: dict[tuple[int, int], dict[str, float]] = {}
    for m in range(1, cur_month + 1):
        key = f"{year}-{m:02d}"
        row = manual_raw.get(key, {})
        cur: dict[str, float] = {}
        prev = filled.get((year, m - 1), {})
        for it in items:
            name, dflt = it["name"], it.get("default", "zero")
            if name in row:
                cur[name] = row[name]
            elif dflt == "prev":
                cur[name] = prev.get(name, 0.0)
            else:
                cur[name] = 0.0
        filled[(year, m)] = cur
    return filled


def manual_missing_months(cfg, manual_raw: dict, year: int, cur_month: int) -> list[str]:
    """当月及之前：有任一「应填」手填项完全未录入的月份列表（用于体检/提示）。"""
    items = [it["name"] for it in cfg.get("manual_items") or []]
    if not items:
        return []
    miss = []
    for m in range(1, cur_month + 1):
        key = f"{year}-{m:02d}"
        row = manual_raw.get(key) or {}
        if not any(name in row for name in items):
            miss.append(key)
    return miss


def manual_for_period(cfg, filled, start, end, cur_date) -> dict[str, int]:
    """手填期间合计，单位：分。filled 值可以是元 float（旧）或分 int（库）。"""
    ms = periods.months_in(start, end, cur_date)
    out = {it["name"]: 0 for it in cfg["manual_items"]}
    for ym in ms:
        for k, v in filled.get(ym, {}).items():
            if k in out:
                out[k] += money.as_fen(v)
            else:
                # 配置外项目也累加（兼容后加项）
                out[k] = out.get(k, 0) + money.as_fen(v)
    return {k: int(v) for k, v in out.items()}


def build_period(
    cfg,
    cols_cfg,
    project_rows,
    order_rows,
    receipt_rows,
    inhouse_rows,
    ledger_rows,
    ledger_year,
    lcols,
    filled_manual,
    label,
    start,
    end,
    cur_date,
):
    vat = cfg["tax"]["vat_rate"]
    surtax_rate = cfg["tax"]["surtax_rate"]
    rc = compute_revenue_cost(project_rows, cols_cfg, start, end, vat)
    net = rc["revenue_net"]
    inhouse = compute_inhouse_cost(inhouse_rows, cols_cfg, cfg, start, end)
    man = manual_for_period(cfg, filled_manual, start, end, cur_date)

    prod_manual = (
        man["PM人力成本"]
        + man["VM人力成本"]
        + man["实际内部译员成本"]
        + man["税费损失"]
        + man["技术流量成本"]
        + man["其他（生产成本）"]
    )
    # 陆总0714·E1：直接成本增值税（手填·默认0）——从生产成本里减掉，得不含税成本；
    # "给未来留缺口"：现阶段她不填=0，业务系统能统计后再启用（旧 config 缺该项按 0，兼容旧测试）
    cost_vat = man.get("直接成本增值税", 0)
    production_cost = int(rc["system_direct_cost"] - inhouse + prod_manual - cost_vat)
    gross_profit = int(net - production_cost)

    led, led_count = compute_ledger_expenses(ledger_rows, ledger_year, start, end, cfg, lcols)
    # 任务书61·J：房租/物业费/装修费 台账已剔，手填分摊归回对应报表大类（未填=0）
    mac = manual_alloc_amounts_by_cat(man, cfg)
    sales_exp = int(man["营销人力成本"] + led["市场费用"] + mac.get("市场费用", 0))
    admin_exp = int(man["管理人力成本"] + led["管理费用"] + mac.get("管理费用", 0))
    fixed_exp = int(led["固定运营费用"] + mac.get("固定运营费用", 0))
    rd_exp = int(man["研发人力成本"] + led["技术服务费"] + mac.get("技术服务费", 0))
    fin_exp = int(led["财务费用"] + man["财务费用补充"] + mac.get("财务费用", 0))
    # 附加税费=不含税收入×增值税率×附加率；在元上 round(2) 再回分（与旧 float 口径一致）
    surtax = money.yuan_to_fen(round(money.fen_to_yuan(net) * vat * surtax_rate, 2)) or 0
    other_pl = int(man["其他损益"])
    period_expense = int(sales_exp + admin_exp + fixed_exp + rd_exp + fin_exp)
    pretax = int(gross_profit - period_expense - surtax + other_pl)

    orders_amt = compute_orders(order_rows, cols_cfg, start, end)
    receipts_amt = compute_receipts(receipt_rows, cols_cfg, start, end)
    # 回款/下单比 = 本期回款 ÷ 本期下单（资金回笼节奏，非当月回收率）；无下单 → None
    receipt_order_ratio = round(receipts_amt / orders_amt * 100, 2) if orders_amt else None

    out = {
        "label": label,
        "delivery_count": rc["delivery_count"],
        "revenue_gross": rc["revenue_gross"],
        "revenue_net": net,
        "vat": rc["vat"],
        "system_direct_cost": rc["system_direct_cost"],
        "inhouse_cost": inhouse,
        "production_cost": production_cost,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / net * 100, 2) if net else 0.0,
        "ledger_expenses": led,
        "ledger_count": led_count,
        "manual": man,
        "expense": {
            "营销费用": sales_exp,
            "管理费用": admin_exp,
            "固定运营费用": fixed_exp,
            "研发费用": rd_exp,
            "财务费用": fin_exp,
            "total": period_expense,
        },
        "surtax": surtax,
        "other_pl": other_pl,
        "pretax_profit": pretax,
        "pretax_margin_pct": round(pretax / net * 100, 2) if net else 0.0,
        "orders": orders_amt,
        "receipts": receipts_amt,
        "receipt_order_ratio_pct": receipt_order_ratio,
        # 板块④ 下单与回款（A6）：四维度=销售/客户 × 下单/回款；双血条同主体对比
        "rankings": {
            "orders_by_sales": compute_ranking(
                order_rows, "销售", cols_cfg["order_amount"], cols_cfg["order_date"], start, end
            ),
            "orders_by_customer": compute_ranking(
                order_rows, "客户", cols_cfg["order_amount"], cols_cfg["order_date"], start, end
            ),
            "receipts_by_sales": compute_ranking(
                receipt_rows, "销售", cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end
            ),
            "receipts_by_customer": compute_ranking(
                receipt_rows, "客户", cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end
            ),
        },
        # 板块③ 收入与毛利结构：确认收入/项目毛利 按客户、按销售（+集中度），确认口径
        "profit_rankings": {
            "revenue_by_customer": compute_profit_ranking(project_rows, "客户", cols_cfg, start, end, vat),
            "revenue_by_sales": compute_profit_ranking(project_rows, "销售", cols_cfg, start, end, vat),
        },
    }
    # 陆总#8：排名主体 1~12 月下单/回款（只挂排名出现的名字；年取期间起算年）
    try:
        y = int(str(start)[:4])
    except (TypeError, ValueError):
        y = 0
    if y:
        out["rankings_monthly"] = build_rankings_monthly(order_rows, receipt_rows, cols_cfg, y, out["rankings"])
    else:
        out["rankings_monthly"] = {"year": 0, "sales": {}, "customer": {}}
    return out


def _month_num(period_key: str) -> int:
    """从「2026年3月」取月号；取不到 → 99（排到后面）。"""
    try:
        part = period_key.split("年", 1)[1].replace("月", "")
        if "-" in part:
            return 99
        return int(part)
    except (IndexError, ValueError):
        return 99


def build_budget_block(budget_raw, year, year_period, h1_period=None) -> dict | None:
    """业务目标完成块：{目标/累计/完成率}×下单+回款+毛利率+税前利润率（年 + 可选 H1）。
    没填任何目标 → None（KPI 下不显示进度条；部门费用预算卡与此无关）。
    完成率分母=0 或指标没填 → 对应项为 None。
    A4：新增 pretax_margin / pretax_margin_h1（存储键 税前利润率年目标/H1）。"""
    y = (budget_raw or {}).get(str(year)) or {}
    order_t, receipt_t = y.get("下单年预算"), y.get("回款年预算")
    margin_t = y.get("毛利率年目标")  # 百分数，如 35 表示 35%
    pretax_t = y.get("税前利润率年目标")
    h1_order, h1_receipt = y.get("下单H1目标"), y.get("回款H1目标")
    h1_margin = y.get("毛利率H1目标")
    h1_pretax = y.get("税前利润率H1目标")
    if all(v is None for v in (order_t, receipt_t, margin_t, pretax_t, h1_order, h1_receipt, h1_margin, h1_pretax)):
        return None

    def _item(target, done):
        if target is None:
            return None
        return {
            "target": float(target),
            "done": done,
            "pct": (done / target * 100.0) if target and done is not None else None,
        }

    def _margin_item(target, actual_pct):
        if target is None:
            return None
        ap = actual_pct if actual_pct is not None else 0.0
        return {"target": float(target), "done": ap, "pct": (ap / target * 100.0) if target else None}

    h1 = h1_period or {}
    return {
        "year": year,
        "order": _item(order_t, year_period["orders"]),
        "receipt": _item(receipt_t, year_period["receipts"]),
        "margin": _margin_item(margin_t, year_period.get("gross_margin_pct") or 0.0),
        "pretax_margin": _margin_item(pretax_t, year_period.get("pretax_margin_pct") or 0.0),
        "order_h1": _item(h1_order, h1.get("orders")),
        "receipt_h1": _item(h1_receipt, h1.get("receipts")),
        "margin_h1": _margin_item(h1_margin, h1.get("gross_margin_pct")),
        "pretax_margin_h1": _margin_item(h1_pretax, h1.get("pretax_margin_pct")),
    }


