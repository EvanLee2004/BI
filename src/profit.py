#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营利润计算：年/季/月全周期矩阵，算到「税前利润」。全部在 Python 算完，前端不做任何金额运算。

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

import datetime
from collections import defaultdict
from typing import Any

import loaders
import columns
import periods


def split_tax(gross: float, vat_rate: float) -> dict[str, float]:
    net = gross / (1 + vat_rate) if gross else 0.0
    return {"revenue_gross": round(gross, 2), "revenue_net": round(net, 2), "vat": round(gross - net, 2)}


# ---------- 收入 / 成本 ----------
def compute_revenue_cost(project_rows, cols_cfg, start, end, vat_rate):
    dcol, rcol, ccol = cols_cfg["project_delivery_date"], cols_cfg["project_revenue"], cols_cfg["project_cost"]
    matched = [r for r in project_rows if periods.date_in_range(loaders.parse_date_parts(r.get(dcol)), start, end)]
    gross = sum(loaders.parse_amount(r.get(rcol)) for r in matched)
    cost = sum(loaders.parse_amount(r.get(ccol)) for r in matched)
    tax = split_tax(gross, vat_rate)
    return {**tax, "delivery_count": len(matched), "system_direct_cost": round(cost, 2)}


def _sum_amount_in_period(rows, amount_col, date_col, start, end, extra=None):
    tot = 0.0
    for r in rows:
        if extra and not extra(r):
            continue
        if periods.date_in_range(loaders.parse_date_parts(r.get(date_col)), start, end):
            tot += loaders.parse_amount(r.get(amount_col))
    return round(tot, 2)


def compute_orders(order_rows, cols_cfg, start, end):
    return _sum_amount_in_period(order_rows, cols_cfg["order_amount"], cols_cfg["order_date"], start, end)


def compute_receipts(receipt_rows, cols_cfg, start, end):
    return _sum_amount_in_period(receipt_rows, cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end)


def compute_ranking(rows, name_col, amount_col, date_col, start, end, top=10, empty_label="（未填）",
                    name_of=None):
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
        a[0] += loaders.parse_amount(r.get(amount_col))
        a[1] += 1
    total = round(sum(v[0] for v in agg.values()), 2)
    uf = agg.pop(empty_label, None)
    unfilled = {"amount": round(uf[0], 2), "count": uf[1]} if uf else None
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])
    full_items = [{"name": n, "amount": round(v[0], 2), "count": v[1]} for n, v in ranked]
    items = full_items[:top]
    rest = ranked[top:]
    others = ({"names": len(rest), "amount": round(sum(v[0] for _, v in rest), 2),
               "count": sum(v[1] for _, v in rest)} if rest else None)
    # full_items：完整排序（供 BU 页「其余」本地展开，不调全公司 /api/daily·铁律12）
    return {"items": items, "others": others, "unfilled": unfilled, "total": total,
            "full_items": full_items}


def compute_profit_ranking(project_rows, name_col, cols_cfg, start, end, vat_rate,
                           top=10, conc_k=5, empty_label="（未填）"):
    """按 name_col（客户/销售）汇总期内**确认收入与项目毛利**并按收入降序排名（收入结构板块用）。
    口径：收入(不含税)=Σ交付额÷(1+vat)；毛利=收入−Σ项目成本（**项目直接毛利**，未含内部译员/手填调整，
    故各组毛利之和与利润表总毛利有差异——footer 已注明）；毛利率=毛利÷收入。
    返回 {items:[{name,revenue,profit,margin_pct,count}…前top], others:{names,revenue,profit,margin_pct,count}|None,
          unfilled:{…}|None, total_revenue, total_profit, conc_k, conc_pct(前 conc_k 大占收入%)}。
    名字空→"（未填）"置底（不参与前 top 排位、计入 total=守恒）。纯函数、只吃行，前端零运算（铁律2 在 render 里成串）。"""
    dcol, rcol, ccol = cols_cfg["project_delivery_date"], cols_cfg["project_revenue"], cols_cfg["project_cost"]
    div = 1.0 + vat_rate
    agg: dict[str, list] = {}   # name -> [Σ含税交付额, Σ项目成本, 笔数]
    for r in project_rows:
        if not periods.date_in_range(loaders.parse_date_parts(r.get(dcol)), start, end):
            continue
        name = str(r.get(name_col) or "").strip() or empty_label
        a = agg.setdefault(name, [0.0, 0.0, 0])
        a[0] += loaders.parse_amount(r.get(rcol))
        a[1] += loaders.parse_amount(r.get(ccol))
        a[2] += 1

    def _row(name, g):
        rev = g[0] / div
        prof = rev - g[1]
        return {"name": name, "revenue": round(rev, 2), "profit": round(prof, 2),
                "margin_pct": round(prof / rev * 100, 1) if rev else None,
                # 系统成本率=Σ项目成本÷收入（陆总0714：业务侧习惯看成本率，展示层用它替代"项目毛利率"）
                "cost_pct": round(g[1] / rev * 100, 1) if rev else None, "count": g[2]}

    def _agg_row(name, gs):   # 合并多组（其余/合计）后再算率，避免率的加权错误
        tot = [sum(x[0] for x in gs), sum(x[1] for x in gs), sum(x[2] for x in gs)]
        return _row(name, tot)

    total_rev = round(sum(g[0] for g in agg.values()) / div, 2)
    total_prof = round(sum(g[0] / div - g[1] for g in agg.values()), 2)
    uf = agg.pop(empty_label, None)
    unfilled = _row(empty_label, uf) if uf else None
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])   # 按含税交付额降序＝按收入降序（div 恒正）
    full_items = [_row(n, g) for n, g in ranked]
    items = full_items[:top]
    rest = [g for _, g in ranked[top:]]
    others = _agg_row(f"其余 {len(rest)} 个", rest) if rest else None
    if others:
        others["names"] = len(rest)
    # 集中度=前 conc_k 大（按含税交付额=收入）占总收入；从完整排序列取，稳健于 top<conc_k
    conc_rev = sum(g[0] for _, g in ranked[:conc_k]) / div
    conc_pct = round(conc_rev / total_rev * 100, 1) if total_rev else None
    # full_items：完整排序（供 BU 页「其余」本地展开，不调 /api/profit_ranking·铁律12）
    return {"items": items, "others": others, "unfilled": unfilled,
            "total_revenue": total_rev, "total_profit": total_prof,
            "conc_k": conc_k, "conc_pct": conc_pct, "full_items": full_items}


def compute_daily(order_rows, receipt_rows, cols_cfg, start, end, top=10, sales_to_bu=None):
    """按天明细（/api/daily 实时算·纯函数只吃行数据）：任意日期区间 → 逐日下单/回款合计 + 期内排名。
    days 只含有业务发生的日（稀疏），升序；totals 与逐日合计守恒（测试守卫 ∑days==compute_orders/receipts）。
    只做下单/回款——费用/手填按月，切不出按天利润（2026-07-10 拍板口径）。
    sales_to_bu={销售名:BU名} 有值时额外算 rankings.orders_by_bu（与全年预渲染「下单·按BU」同口径）。"""
    days: dict[str, list] = {}   # day -> [下单额, 下单笔数, 回款额, 回款笔数]

    def _acc(rows, amount_col, date_col, ai, ci):
        for r in rows:
            d = loaders.parse_date_parts(r.get(date_col))
            if not periods.date_in_range(d, start, end):
                continue
            slot = days.setdefault(f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}", [0.0, 0, 0.0, 0])
            slot[ai] += loaders.parse_amount(r.get(amount_col))
            slot[ci] += 1

    _acc(order_rows, cols_cfg["order_amount"], cols_cfg["order_date"], 0, 1)
    _acc(receipt_rows, cols_cfg["receipt_amount"], cols_cfg["receipt_date"], 2, 3)
    out_days = [{"day": k, "orders": round(v[0], 2), "orders_count": v[1],
                 "receipts": round(v[2], 2), "receipts_count": v[3]}
                for k, v in sorted(days.items())]
    totals = {"orders": round(sum(v[0] for v in days.values()), 2),
              "orders_count": sum(v[1] for v in days.values()),
              "receipts": round(sum(v[2] for v in days.values()), 2),
              "receipts_count": sum(v[3] for v in days.values())}
    rankings = {
        "orders_by_sales": compute_ranking(order_rows, "销售", cols_cfg["order_amount"],
                                           cols_cfg["order_date"], start, end, top),
        "orders_by_customer": compute_ranking(order_rows, "客户", cols_cfg["order_amount"],
                                              cols_cfg["order_date"], start, end, top),
        "receipts_by_sales": compute_ranking(receipt_rows, "销售", cols_cfg["receipt_amount"],
                                             cols_cfg["receipt_date"], start, end, top),
        "receipts_by_customer": compute_ranking(receipt_rows, "客户", cols_cfg["receipt_amount"],
                                                cols_cfg["receipt_date"], start, end, top),
    }
    if sales_to_bu:
        smap = {str(k).strip(): v for k, v in sales_to_bu.items() if str(k).strip()}

        def _bu_of(row):
            return smap.get(str(row.get("销售") or "").strip(), "")

        rankings["orders_by_bu"] = compute_ranking(
            order_rows, "销售", cols_cfg["order_amount"], cols_cfg["order_date"], start, end, top,
            empty_label="（未归属）", name_of=_bu_of)
    return {"days": out_days, "totals": totals, "rankings": rankings}


def compute_inhouse_cost(inhouse_rows, cols_cfg, cfg, start, end):
    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    tcol = cols_cfg["inhouse_type"]
    return _sum_amount_in_period(
        inhouse_rows, cols_cfg["inhouse_amount"], cols_cfg["inhouse_date"], start, end,
        extra=lambda r: kw in str(r.get(tcol, "")).upper(),
    )


# ---------- 费用去税（陆总 0714·按费用类别手填去税率） ----------
def detax_ledger_rows(ledger_header, ledger_rows, detax_rates):
    """按「预算明细费用类型」的手填去税率，把台账每行含税额换成不含税额（真实进项抵减后费用）。
    detax_rates={费用类别:税率%}；**空/None → 原样返回**（默认0=不去税，页面数字一分不变·回归红线中性）。
    不含税额 = 含税额 / (1 + 税率/100)；只改金额列、不改行数（体检/守恒不受影响）。
    在源头统一去税一次 → 大类/细类/按BU/公共池分摊全部一致，不会两处真相（守恒自动成立）。"""
    if not detax_rates or not ledger_header:
        return ledger_rows
    lcols = columns.resolve_ledger_columns(ledger_header)
    c_amt, c_fine = lcols.get("含税金额"), lcols.get("预算明细费用类型")
    if c_amt is None or c_fine is None:
        return ledger_rows
    out = []
    for row in ledger_rows:
        fine_raw = row[c_fine] if len(row) > c_fine else None
        fine = str(fine_raw).strip() if fine_raw not in (None, "") else ""
        r = detax_rates.get(fine)
        if r and float(r) > 0 and len(row) > c_amt:
            amt = loaders.parse_amount(row[c_amt])
            if amt:
                lst = list(row)
                lst[c_amt] = amt / (1.0 + float(r) / 100.0)  # 不逐行 round，末端再统一 round，避免累积误差
                row = tuple(lst)
        out.append(row)
    return out


# ---------- 台账费用 ----------
def compute_ledger_expenses(ledger_rows, ledger_year, start, end, cfg, lcols):
    included = cfg["expense_categories_included"]
    by_cat = defaultdict(float)
    count = 0
    c_amt = lcols["含税金额"]
    for row in ledger_rows:
        amt = loaders.parse_amount(row[c_amt] if len(row) > c_amt else None)
        if amt == 0.0:
            continue
        if not periods.date_in_range(periods.ledger_row_date(row, ledger_year, lcols), start, end):
            continue
        cat = columns.classify_expense_category(row, cfg, lcols)[0]
        if cat not in included:
            continue
        by_cat[cat] += amt
        count += 1
    return {cat: round(by_cat.get(cat, 0.0), 2) for cat in included}, count


def compute_expenses_by_fine_type(ledger_rows, ledger_year, start, end, cfg, lcols):
    """台账费用按报表大类 → 预算明细费用类型 细分（下钻一层，供利润表台账行展开）。"""
    included = set(cfg["expense_categories_included"])
    fine_label = cfg["unclassified_label_fine_type"]
    c_amt, c_fine = lcols["含税金额"], lcols["预算明细费用类型"]
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in ledger_rows:
        amt = loaders.parse_amount(row[c_amt] if len(row) > c_amt else None)
        if amt == 0.0:
            continue
        if not periods.date_in_range(periods.ledger_row_date(row, ledger_year, lcols), start, end):
            continue
        cat = columns.classify_expense_category(row, cfg, lcols)[0]
        if cat not in included:
            continue
        fine_raw = row[c_fine] if len(row) > c_fine else None
        fine = str(fine_raw).strip() if fine_raw not in (None, "") else fine_label
        out[cat][fine] += amt
    return {c: sorted(d.items(), key=lambda x: -x[1]) for c, d in out.items()}


EXPENSE_GROUP_UNFILLED = "未分类"  # 分组列没填的行的展示名（部门/利润中心视角共用）


def compute_expenses_by_group(ledger_rows, ledger_year, start, end, cfg, lcols, group_field):
    """白名单内费用按台账某列分组（预算归属部门/业务BU 两个视角共用）+ 组内细类嵌套。
    返回 [(组名, 合计, [(细类, 金额), ...按金额降序]), ...按合计降序]；
    台账没有该列 → None（前端降级提示"台账无此列"）。
    口径与 compute_ledger_expenses 完全一致（白名单8大类内、含税、同期间）——守恒：各组合计==期间费用合计。"""
    c_grp = lcols.get(group_field)
    if c_grp is None:
        return None
    included = set(cfg["expense_categories_included"])
    fine_label = cfg["unclassified_label_fine_type"]
    c_amt, c_fine = lcols["含税金额"], lcols["预算明细费用类型"]
    agg: dict[str, float] = defaultdict(float)
    fine: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in ledger_rows:
        amt = loaders.parse_amount(row[c_amt] if len(row) > c_amt else None)
        if amt == 0.0:
            continue
        if not periods.date_in_range(periods.ledger_row_date(row, ledger_year, lcols), start, end):
            continue
        if columns.classify_expense_category(row, cfg, lcols)[0] not in included:
            continue
        grp_raw = row[c_grp] if len(row) > c_grp else None
        grp = str(grp_raw).strip() if grp_raw not in (None, "") else EXPENSE_GROUP_UNFILLED
        fine_raw = row[c_fine] if len(row) > c_fine else None
        f = str(fine_raw).strip() if fine_raw not in (None, "") else fine_label
        agg[grp] += amt
        fine[grp][f] += amt
    return [(g, round(v, 2), sorted(fine[g].items(), key=lambda x: -x[1]))
            for g, v in sorted(agg.items(), key=lambda x: -x[1])]


def build_dept_budget_block(dept_budget_raw, dept_rows_year, year):
    """部门费用预算执行：{年预算(手填) vs 已用(台账白名单内年累计·含特批)}。
    dept_budget_raw={年份:{部门:金额}}；dept_rows_year=compute_expenses_by_group 全年结果（可为 None）。
    没填任何部门预算 → 仍返回空壳 {year, rows:[]}（页面渲染空态卡，与回款左右对称；迭代18 拍板）。
    只列有预算的部门（执行卡本意=管控）。"""
    budgets = (dept_budget_raw or {}).get(str(year)) or {}
    used = {g: v for g, v, _ in (dept_rows_year or [])}
    rows = []
    for dept, target in budgets.items():
        u = used.get(dept, 0.0)
        rows.append({"dept": dept, "target": target, "used": round(u, 2),
                     "pct": (u / target * 100.0) if target else None})
    rows.sort(key=lambda r: (r["pct"] is None, -(r["pct"] or 0)))
    return {"year": year, "rows": rows}


# ---------- 手填（月度填充 + 按周期汇总） ----------
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


def manual_for_period(cfg, filled, start, end, cur_date) -> dict[str, float]:
    ms = periods.months_in(start, end, cur_date)
    out = {it["name"]: 0.0 for it in cfg["manual_items"]}
    for ym in ms:
        for k, v in filled.get(ym, {}).items():
            out[k] += v
    return {k: round(v, 2) for k, v in out.items()}


# ---------- 组装单周期利润表 ----------
def build_period(cfg, cols_cfg, project_rows, order_rows, receipt_rows, inhouse_rows,
                 ledger_rows, ledger_year, lcols, filled_manual, label, start, end, cur_date):
    vat = cfg["tax"]["vat_rate"]
    surtax_rate = cfg["tax"]["surtax_rate"]
    rc = compute_revenue_cost(project_rows, cols_cfg, start, end, vat)
    net = rc["revenue_net"]
    inhouse = compute_inhouse_cost(inhouse_rows, cols_cfg, cfg, start, end)
    man = manual_for_period(cfg, filled_manual, start, end, cur_date)

    prod_manual = man["PM人力成本"] + man["VM人力成本"] + man["实际内部译员成本"] + man["税费损失"] + man["技术流量成本"] + man["其他（生产成本）"]
    # 陆总0714·E1：直接成本增值税（手填·默认0）——从生产成本里减掉，得不含税成本；
    # "给未来留缺口"：现阶段她不填=0，业务系统能统计后再启用（旧 config 缺该项按 0，兼容旧测试）
    cost_vat = man.get("直接成本增值税", 0.0)
    production_cost = round(rc["system_direct_cost"] - inhouse + prod_manual - cost_vat, 2)
    gross_profit = round(net - production_cost, 2)

    led, led_count = compute_ledger_expenses(ledger_rows, ledger_year, start, end, cfg, lcols)
    sales_exp = round(man["营销人力成本"] + led["市场费用"], 2)
    admin_exp = round(man["管理人力成本"] + led["管理费用"], 2)
    fixed_exp = round(led["固定运营费用"], 2)
    rd_exp = round(man["研发人力成本"] + led["技术服务费"], 2)
    fin_exp = round(led["财务费用"] + man["财务费用补充"], 2)
    surtax = round(net * vat * surtax_rate, 2)
    other_pl = round(man["其他损益"], 2)
    period_expense = round(sales_exp + admin_exp + fixed_exp + rd_exp + fin_exp, 2)
    pretax = round(gross_profit - period_expense - surtax + other_pl, 2)

    orders_amt = compute_orders(order_rows, cols_cfg, start, end)
    receipts_amt = compute_receipts(receipt_rows, cols_cfg, start, end)
    # 回款/下单比 = 本期回款 ÷ 本期下单（资金回笼节奏，非当月回收率）；无下单 → None
    receipt_order_ratio = round(receipts_amt / orders_amt * 100, 2) if orders_amt else None

    return {
        "label": label,
        "delivery_count": rc["delivery_count"],
        "revenue_gross": rc["revenue_gross"], "revenue_net": net, "vat": rc["vat"],
        "system_direct_cost": rc["system_direct_cost"], "inhouse_cost": inhouse,
        "production_cost": production_cost,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / net * 100, 2) if net else 0.0,
        "ledger_expenses": led, "ledger_count": led_count,
        "manual": man,
        "expense": {
            "营销费用": sales_exp, "管理费用": admin_exp, "固定运营费用": fixed_exp,
            "研发费用": rd_exp, "财务费用": fin_exp, "total": period_expense,
        },
        "surtax": surtax, "other_pl": other_pl,
        "pretax_profit": pretax,
        "pretax_margin_pct": round(pretax / net * 100, 2) if net else 0.0,
        "orders": orders_amt,
        "receipts": receipts_amt,
        "receipt_order_ratio_pct": receipt_order_ratio,
        # 板块④ 下单与回款（A6）：四维度=销售/客户 × 下单/回款；双血条同主体对比
        "rankings": {
            "orders_by_sales": compute_ranking(order_rows, "销售", cols_cfg["order_amount"],
                                               cols_cfg["order_date"], start, end),
            "orders_by_customer": compute_ranking(order_rows, "客户", cols_cfg["order_amount"],
                                                  cols_cfg["order_date"], start, end),
            "receipts_by_sales": compute_ranking(receipt_rows, "销售", cols_cfg["receipt_amount"],
                                                 cols_cfg["receipt_date"], start, end),
            "receipts_by_customer": compute_ranking(receipt_rows, "客户", cols_cfg["receipt_amount"],
                                                    cols_cfg["receipt_date"], start, end),
        },
        # 板块③ 收入与毛利结构：确认收入/项目毛利 按客户、按销售（+集中度），确认口径
        "profit_rankings": {
            "revenue_by_customer": compute_profit_ranking(project_rows, "客户", cols_cfg, start, end, vat),
            "revenue_by_sales": compute_profit_ranking(project_rows, "销售", cols_cfg, start, end, vat),
        },
    }


# ---------- 顶层 ----------
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
    if all(v is None for v in (order_t, receipt_t, margin_t, pretax_t,
                               h1_order, h1_receipt, h1_margin, h1_pretax)):
        return None

    def _item(target, done):
        if target is None:
            return None
        return {"target": float(target), "done": done,
                "pct": (done / target * 100.0) if target and done is not None else None}

    def _margin_item(target, actual_pct):
        if target is None:
            return None
        ap = actual_pct if actual_pct is not None else 0.0
        return {"target": float(target), "done": ap,
                "pct": (ap / target * 100.0) if target else None}

    h1 = h1_period or {}
    return {"year": year,
            "order": _item(order_t, year_period["orders"]),
            "receipt": _item(receipt_t, year_period["receipts"]),
            "margin": _margin_item(margin_t, year_period.get("gross_margin_pct") or 0.0),
            "pretax_margin": _margin_item(pretax_t, year_period.get("pretax_margin_pct") or 0.0),
            "order_h1": _item(h1_order, h1.get("orders")),
            "receipt_h1": _item(h1_receipt, h1.get("receipts")),
            "margin_h1": _margin_item(h1_margin, h1.get("gross_margin_pct")),
            "pretax_margin_h1": _margin_item(h1_pretax, h1.get("pretax_margin_pct"))}


def build_summary(cfg, project_rows, order_rows, receipt_rows, inhouse_rows,
                  ledger_header, ledger_rows, ledger_year, today, manual_raw=None,
                  budget_raw=None, dept_budget_raw=None, detax_rates=None):
    cols_cfg = cfg["columns"]
    lcols = columns.resolve_ledger_columns(ledger_header)
    ledger_rows = detax_ledger_rows(ledger_header, ledger_rows, detax_rates)  # 费用去税（默认空=恒等）
    ranges = periods.all_period_ranges(today)
    # manual_raw 由调用方注入（run.py 从库读 db.load_manual）；不传则回退读手填 xlsx（现有测试路径）
    if manual_raw is None:
        manual_raw = load_manual_safe(cfg)
    filled_manual = build_manual_monthly(cfg, manual_raw, today.year, today.month)

    P: dict[str, Any] = {}
    fine: dict[str, Any] = {}
    by_dept: dict[str, Any] = {}
    by_pc: dict[str, Any] = {}
    tab_groups = {"年": [], "季度": [], "月": [], "区间": []}
    for key, (label, start, end, group) in ranges.items():
        P[key] = build_period(cfg, cols_cfg, project_rows, order_rows, receipt_rows, inhouse_rows,
                              ledger_rows, ledger_year, lcols, filled_manual, label, start, end, today)
        P[key]["range"] = (start.isoformat(), end.isoformat())   # 排名卡「其余」点开全量明细要带的区间
        fine[key] = compute_expenses_by_fine_type(ledger_rows, ledger_year, start, end, cfg, lcols)
        by_dept[key] = compute_expenses_by_group(ledger_rows, ledger_year, start, end, cfg, lcols, "预算归属部门")
        by_pc[key] = compute_expenses_by_group(ledger_rows, ledger_year, start, end, cfg, lcols, "业务BU")
        tab_groups[group].append(key)

    year_key = f"{today.year}年"
    cur_month_key = f"{today.year}年{today.month}月"
    month_keys = tab_groups["月"]
    trend = [(P[k]["label"].replace(f"{today.year}年", ""), P[k]["revenue_net"], P[k]["production_cost"],
              P[k]["gross_margin_pct"]) for k in month_keys]
    receipt_monthly = [(P[k]["label"].replace(f"{today.year}年", ""), P[k]["receipts"]) for k in month_keys]
    # 回款柱图叠加"每月回款/下单比"用：逐月 (标签, 回款, 下单, 回款/下单比%)；率为 None 表示当月无下单
    receipt_order_monthly = [(P[k]["label"].replace(f"{today.year}年", ""), P[k]["receipts"],
                             P[k]["orders"], P[k]["receipt_order_ratio_pct"]) for k in month_keys]

    unclassified = columns.build_unclassified_summary(
        ledger_rows, cfg, lcols,
        amount_filter=lambda r: periods.date_in_range(
            periods.ledger_row_date(r, ledger_year, lcols),
            datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31)),
    )
    health = _data_health(cfg, cols_cfg, project_rows, order_rows, receipt_rows, inhouse_rows,
                          ledger_rows, ledger_year, lcols, P, today, unclassified, month_keys, manual_raw)
    # H1=1–6 月：优先用合成区间；没有则按月累加（绝不用 Q1 冒充 H1）
    h1_key = f"{today.year}年1-6月"
    h1_period = P.get(h1_key)
    if h1_period is None and month_keys:
        h1_ms = [k for k in month_keys if k in P and _month_num(k) <= 6]
        if h1_ms:
            g = sum(P[k]["gross_profit"] for k in h1_ms)
            n = sum(P[k]["revenue_net"] for k in h1_ms)
            h1_period = {
                "orders": sum(P[k]["orders"] for k in h1_ms),
                "receipts": sum(P[k]["receipts"] for k in h1_ms),
                "gross_margin_pct": round(g / n * 100, 2) if n else 0.0,
            }
    return {
        "meta": {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "year": today.year, "year_key": year_key, "current_month_key": cur_month_key,
            "current_month_label": P[cur_month_key]["label"],
            "ledger_sheet_used": str(ledger_year), "tab_groups": tab_groups,
            "budget": build_budget_block(budget_raw, today.year, P[year_key], h1_period),
            "dept_budget": build_dept_budget_block(dept_budget_raw, by_dept.get(year_key), today.year),
            "unclassified": unclassified,
            "health": health,
        },
        "periods": P, "expense_fine_type": fine,
        "expense_by_department": by_dept, "expense_by_profit_center": by_pc,
        "trend": trend, "receipt_monthly": receipt_monthly,
        "receipt_order_monthly": receipt_order_monthly,
    }


# ---------- BU 分页（迭代 14 · 陆总 2026-07-12 拍板：按销售人员归属 BU 拆） ----------
def filter_rows_by_sales(rows, sales_set, col="销售"):
    """按「销售」列过滤行（纯函数）。sales_set=该 BU 销售名单集合；名字比对去首尾空白。
    四源行结构通用（收入明细/下单/回款/内部译员的读回 dict 都带「销售」键）。"""
    s = {str(x).strip() for x in sales_set if str(x).strip()}
    return [r for r in rows if str(r.get(col) or "").strip() in s]


def compute_unassigned_orders_by_period(order_rows, assigned_set, cols_cfg, today):
    """A3 整体页「未归属」提示：每周期未归属销售（不在任何 BU 名单）的下单金额。
    assigned_set=已归属销售名集合（去空白）；未归属=str(销售).strip() 不在其中（含销售空的行——
    它们同样进不了任何 BU 页，是「各 BU 合计 < 全公司」差额的组成，故一并计入以精确解释差额）。
    返回 {周期key: 金额}，周期集合与 build_summary 的 periods 完全一致（前端预渲染按周期切）。
    口径与 BU 页过滤共用同一规范化（filter_rows_by_sales 亦 str().strip()）——界面/过滤一把尺。"""
    s = {str(x).strip() for x in assigned_set if str(x).strip()}
    unassigned = [r for r in order_rows if str(r.get("销售") or "").strip() not in s]
    ranges = periods.all_period_ranges(today)
    return {key: compute_orders(unassigned, cols_cfg, start, end)
            for key, (label, start, end, group) in ranges.items()}


# 空台账表头（与 db.LEDGER_STD_COLS 同序）
_BU_EMPTY_LEDGER_HEADER = ["收单月份", "收单日期", "含税金额", "业务BU",
                           "对应报表大类", "预算明细费用类型", "预算归属部门"]

# 台账 5 类 → 利润表费用行
_LEDGER_TO_EXPENSE = {
    "市场费用": "营销费用",
    "管理费用": "管理费用",
    "固定运营费用": "固定运营费用",
    "技术服务费": "研发费用",
    "财务费用": "财务费用",
}

# 利润归属中心 → 业务 BU 名归一（台账写法多样）
_PC_TO_BU = {
    "数据": "数据", "数据部门": "数据", "数据BU": "数据",
    "游戏": "游戏", "游戏部门": "游戏", "游戏BU": "游戏",
    "营销": "营销", "传统营销": "营销", "营销中心": "营销", "语言": "营销",
}
_PUBLIC_PC = {"公共", "集团", "财务", "财务部", "公司", "全公司", "总部"}


def normalize_profit_center(raw) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s in _PUBLIC_PC:
        return "公共"
    return _PC_TO_BU.get(s, s)


def scan_unknown_profit_centers(ledger_rows, ledger_year, lcols, cfg, bu_names,
                                year: int | None = None) -> list[dict]:
    """扫描全年台账白名单费用行的「利润归属中心」归一结果，收集未知名清单。

    返回 [{name, count, amount}, ...] 按金额降序。
    未知 = 非空、归一后既不是「公共」、也不等于任一已配 BU 名。
    空归属中心不进此清单（另有未分类提示）。不改任何算数，只体检。
    """
    if not bu_names or not ledger_rows or not lcols:
        return []
    known = {"公共"} | {str(b).strip() for b in bu_names if str(b).strip()}
    included = set(cfg.get("expense_categories_included") or [])
    c_amt = lcols["含税金额"]
    c_pc = lcols["业务BU"]
    y = int(year if year is not None else ledger_year)
    start, end = datetime.date(y, 1, 1), datetime.date(y, 12, 31)
    # raw 原文聚合（便于对照台账改名）
    stats: dict[str, list] = defaultdict(lambda: [0, 0.0])  # count, amount
    for row in ledger_rows:
        if not row:
            continue
        amt = loaders.parse_amount(row[c_amt] if len(row) > c_amt else None)
        if amt == 0.0:
            continue
        if not periods.date_in_range(periods.ledger_row_date(row, ledger_year, lcols), start, end):
            continue
        cat = columns.classify_expense_category(row, cfg, lcols)[0]
        if cat not in included:
            continue
        raw = str(row[c_pc] if len(row) > c_pc else "").strip()
        if not raw:
            continue
        pc = normalize_profit_center(raw)
        if pc in known:
            continue
        stats[raw][0] += 1
        stats[raw][1] += amt
    out = [{"name": n, "count": c, "amount": round(a, 2)}
           for n, (c, a) in stats.items()]
    out.sort(key=lambda x: (-x["amount"], x["name"]))
    return out


def unknown_pc_warnings(items: list[dict]) -> list[str]:
    """把未知归属中心清单编成体检警告文案（金额服务端算好）。"""
    warns = []
    for it in items or []:
        name = str(it.get("name") or "")
        n = int(it.get("count") or 0)
        amt = float(it.get("amount") or 0)
        if not name or n <= 0:
            continue
        warns.append(
            f"台账 {n} 笔费用的利润归属中心『{name}』不在 BU 名单"
            f"（¥{amt/1e4:.1f} 万）——不进任何 BU 直记也不进公共池，请到设置核对 BU 名或修正台账"
        )
    return warns


def filter_ledger_rows_by_pc(header, rows, want: set[str]) -> list:
    """按利润归属中心(业务BU列)过滤台账行。want 为归一后中心名集合，如 {\"数据\"} 或 {\"公共\"}。"""
    if not rows or not header:
        return []
    try:
        idx = list(header).index("业务BU")
    except ValueError:
        return []
    want_n = {normalize_profit_center(x) for x in want if str(x).strip()}
    out = []
    for row in rows:
        if not row or len(row) <= idx:
            continue
        pc = normalize_profit_center(row[idx])
        if pc in want_n:
            out.append(row)
    return out


def build_bu_summary(cfg, project_rows, order_rows, receipt_rows, inhouse_rows, today, sales_set,
                     *, company_ledger_by_period=None, alloc_ratio_pct=None, alloc_enabled=False,
                     budget_raw=None, ledger_header=None, ledger_rows=None, ledger_year=None,
                     manual_raw=None, bu_name: str | None = None, detax_rates=None):
    """单 BU summary：智云四源按销售过滤；台账按利润归属中心直记本 BU；
    公共池（利润归属中心=公共）× 分摊比例叠加（可选）；手填可按 BU 范围注入。
    兼容旧测：不传 ledger → 空台账；company_ledger_by_period 视为「公共池」费用字典。"""
    lh = list(ledger_header) if ledger_header is not None else list(_BU_EMPTY_LEDGER_HEADER)
    lr = list(ledger_rows) if ledger_rows is not None else []
    ly = ledger_year if ledger_year is not None else today.year
    man = manual_raw if manual_raw is not None else {}
    s = build_summary(
        cfg,
        filter_rows_by_sales(project_rows, sales_set),
        filter_rows_by_sales(order_rows, sales_set),
        filter_rows_by_sales(receipt_rows, sales_set),
        filter_rows_by_sales(inhouse_rows, sales_set),
        lh, lr, ly, today,
        manual_raw=man, budget_raw=budget_raw, dept_budget_raw=None, detax_rates=detax_rates)
    if bu_name:
        s.setdefault("meta", {})["bu_name"] = bu_name
    if alloc_enabled and alloc_ratio_pct is not None and company_ledger_by_period:
        apply_public_expense_allocation(s, company_ledger_by_period, float(alloc_ratio_pct))
    else:
        s.setdefault("meta", {})["public_allocation"] = {
            "enabled": False, "ratio_pct": None, "ratio_disp": ""}
    return s


def apply_public_expense_allocation(summary: dict, company_ledger_by_period: dict,
                                    ratio_pct: float) -> None:
    """就地：把「公共池」台账 5 类 × 比例 **叠加** 进 BU 已有直记费用（不覆盖直记）。
    company_ledger_by_period 应为公共归属中心的费用；若传入全公司（旧测），则按比例拆全额——
    与「仅公共池」在无直记时数值等价。手填不摊；附加税按 BU 自身收入。"""
    factor = float(ratio_pct) / 100.0
    P = summary.get("periods") or {}
    for key, p in P.items():
        led_src = company_ledger_by_period.get(key) or {}
        man = p.get("manual") or {}
        led = dict(p.get("ledger_expenses") or {})
        for cat in _LEDGER_TO_EXPENSE:
            add = round(float(led_src.get(cat) or 0.0) * factor, 2)
            led[cat] = round(float(led.get(cat) or 0.0) + add, 2)
        sales_exp = round(float(man.get("营销人力成本") or 0) + float(led.get("市场费用") or 0), 2)
        admin_exp = round(float(man.get("管理人力成本") or 0) + float(led.get("管理费用") or 0), 2)
        fixed_exp = round(float(led.get("固定运营费用") or 0), 2)
        rd_exp = round(float(man.get("研发人力成本") or 0) + float(led.get("技术服务费") or 0), 2)
        fin_exp = round(float(led.get("财务费用") or 0) + float(man.get("财务费用补充") or 0), 2)
        total = round(sales_exp + admin_exp + fixed_exp + rd_exp + fin_exp, 2)
        p["ledger_expenses"] = led
        p["expense"] = {
            "营销费用": sales_exp, "管理费用": admin_exp, "固定运营费用": fixed_exp,
            "研发费用": rd_exp, "财务费用": fin_exp, "total": total,
        }
        p["pretax_profit"] = round(
            float(p["gross_profit"]) - total - float(p["surtax"]) + float(p.get("other_pl") or 0), 2)
        net = float(p.get("revenue_net") or 0)
        p["pretax_margin_pct"] = round(p["pretax_profit"] / net * 100, 2) if net else 0.0
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": True,
        "ratio_pct": float(ratio_pct),
        "ratio_disp": f"{ratio_pct:g}%",
    }


# ---------- 公共费用按月比例分摊（迭代20） ----------
def _merge_alloc_into_period(p: dict, add_by_cat: dict[str, float]) -> None:
    """就地把分摊额（按台账 5 类）叠加进单周期的费用与税前（与整比例版同一套公式）。"""
    man = p.get("manual") or {}
    led = dict(p.get("ledger_expenses") or {})
    for cat in _LEDGER_TO_EXPENSE:
        led[cat] = round(float(led.get(cat) or 0.0) + float(add_by_cat.get(cat) or 0.0), 2)
    # 记下本周期各类实际叠加的分摊额（迭代22·D4：BU 利润表抽屉把「直记」与「分摊自公共」分开展示）
    p["alloc_added"] = {cat: round(float(add_by_cat.get(cat) or 0.0), 2) for cat in _LEDGER_TO_EXPENSE}
    sales_exp = round(float(man.get("营销人力成本") or 0) + float(led.get("市场费用") or 0), 2)
    admin_exp = round(float(man.get("管理人力成本") or 0) + float(led.get("管理费用") or 0), 2)
    fixed_exp = round(float(led.get("固定运营费用") or 0), 2)
    rd_exp = round(float(man.get("研发人力成本") or 0) + float(led.get("技术服务费") or 0), 2)
    fin_exp = round(float(led.get("财务费用") or 0) + float(man.get("财务费用补充") or 0), 2)
    total = round(sales_exp + admin_exp + fixed_exp + rd_exp + fin_exp, 2)
    p["ledger_expenses"] = led
    p["expense"] = {
        "营销费用": sales_exp, "管理费用": admin_exp, "固定运营费用": fixed_exp,
        "研发费用": rd_exp, "财务费用": fin_exp, "total": total,
    }
    p["pretax_profit"] = round(
        float(p["gross_profit"]) - total - float(p["surtax"]) + float(p.get("other_pl") or 0), 2)
    net = float(p.get("revenue_net") or 0)
    p["pretax_margin_pct"] = round(p["pretax_profit"] / net * 100, 2) if net else 0.0


def _alloc_cats_for_range(public_month_led: dict, ratios_by_month: dict, bu_name: str,
                          start, end, cap) -> dict[str, float]:
    """某周期内：逐月 公共池5类 × 该月该 BU 比例，按类加总。缺月比例=0（不分摊）。"""
    add = {cat: 0.0 for cat in _LEDGER_TO_EXPENSE}
    for (y, m) in periods.months_in(start, end, cap):
        pct = (ratios_by_month.get(f"{y:04d}-{m:02d}") or {}).get(bu_name)
        if not pct:
            continue
        led = public_month_led.get((y, m)) or {}
        for cat in _LEDGER_TO_EXPENSE:
            add[cat] += float(led.get(cat) or 0.0) * float(pct) / 100.0
    return {cat: round(v, 2) for cat, v in add.items()}


def apply_public_expense_allocation_monthly(summary: dict, public_month_led: dict,
                                            ratios_by_month: dict, bu_name: str, today) -> None:
    """就地：按月比例把公共池费用叠加进单 BU summary 各周期（迭代20）。
    public_month_led={(y,m):{5类:金额}}；ratios_by_month={'YYYY-MM':{BU:比例%}}；
    当月合计可 <100%（剩余留公司层）。没有任何生效比例 → meta 标 enabled=False。"""
    P = summary.get("periods") or {}
    # 「已配置」与「有金额」分开：配置了比例（哪怕当期公共池为 0）也标注口径，别让读者以为没摊
    has_ratio = any((r or {}).get(bu_name) for r in ratios_by_month.values())
    for key, p in P.items():
        rng = p.get("range")
        if not rng:
            continue
        start = datetime.date.fromisoformat(rng[0])
        end = datetime.date.fromisoformat(rng[1])
        add = _alloc_cats_for_range(public_month_led, ratios_by_month, bu_name, start, end, today)
        if not any(add.values()):
            continue
        _merge_alloc_into_period(p, add)
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": has_ratio, "mode": "monthly", "ratio_pct": None,
        "ratio_disp": "按月比例" if has_ratio else "",
    }


def alloc_amounts_by_period(public_month_led: dict, ratios_by_month: dict,
                            bu_names: list[str], today) -> dict[str, dict[str, float]]:
    """每周期每 BU 的分摊总额（供全公司「构成·按业务BU」视图跟着挪·迭代20）。
    只认在 bu_names 里的 BU（孤儿比例行由调用方另行告警）。返回 {周期key: {BU: 金额}}。"""
    want = set(bu_names or [])
    ranges = periods.all_period_ranges(today)
    out: dict[str, dict[str, float]] = {}
    for key, (_lab, start, end, _grp) in ranges.items():
        per: dict[str, float] = {}
        for (y, m) in periods.months_in(start, end, today):
            r = ratios_by_month.get(f"{y:04d}-{m:02d}") or {}
            led = public_month_led.get((y, m)) or {}
            month_pub = sum(float(led.get(c) or 0.0) for c in _LEDGER_TO_EXPENSE)
            for b, pct in r.items():
                if b in want and pct:
                    per[b] = per.get(b, 0.0) + month_pub * float(pct) / 100.0
        cleaned = {b: round(v, 2) for b, v in per.items() if round(v, 2)}
        if cleaned:
            out[key] = cleaned
    return out


ALLOC_IN_LABEL = "分摊自公共"       # BU 组抽屉里的细类行
ALLOC_OUT_LABEL = "已分摊至各BU"    # 公共组抽屉里的负数行


def apply_alloc_to_pc_view(groups, alloc_by_bu: dict[str, float]):
    """把分摊结果套进「构成·按业务BU（利润中心）」单周期分组列表（迭代20·防两处真相）。
    groups=[(组名,合计,[(细类,金额)…])]；公共组减去已摊总额并挂负数行，各 BU 组加分摊额并挂正数行。
    **各组合计之和不变**（分摊只挪归属）。groups 为 None（台账无此列）原样返回。"""
    if not groups or not alloc_by_bu:
        return groups
    total_alloc = round(sum(alloc_by_bu.values()), 2)
    if total_alloc <= 0:
        return groups
    gmap = {g: (t, list(f)) for g, t, f in groups}
    if "公共" not in gmap:   # 分摊额来自公共池；池不存在说明上游没数，不动
        return groups
    for b, amt in alloc_by_bu.items():
        if amt <= 0:
            continue
        t, f = gmap.get(b, (0.0, []))
        gmap[b] = (round(t + amt, 2), f + [(ALLOC_IN_LABEL, round(amt, 2))])
    t, f = gmap["公共"]
    gmap["公共"] = (round(t - total_alloc, 2), f + [(ALLOC_OUT_LABEL, round(-total_alloc, 2))])
    return [(g, t, sorted(f, key=lambda x: -x[1]))
            for g, (t, f) in sorted(gmap.items(), key=lambda kv: -kv[1][0])]


def load_manual_safe(cfg):
    try:
        return loaders.load_manual(cfg)
    except FileNotFoundError:
        return {}


def _scan_dict_source_issues(rows, date_col, amount_col):
    """一个智云源里：日期非空但解析不出（行会被整条剔除）/ 金额非空但解析不出（会按0算）的行数。"""
    date_bad = amt_bad = 0
    for r in rows:
        dv = r.get(date_col)
        if dv is not None and str(dv).strip() and loaders.parse_date_parts(dv) is None:
            date_bad += 1
        if loaders.amount_parse_fails(r.get(amount_col)):
            amt_bad += 1
    return date_bad, amt_bad


def _scan_ledger_issues(ledger_rows, ledger_year, lcols):
    c_amt, c_d, c_m = lcols["含税金额"], lcols["收单日期"], lcols["收单月份"]
    date_bad = amt_bad = 0
    for row in ledger_rows:
        if loaders.amount_parse_fails(row[c_amt] if len(row) > c_amt else None):
            amt_bad += 1
        if periods.ledger_row_date(row, ledger_year, lcols) is None:
            rawd = row[c_d] if len(row) > c_d else None
            rawm = row[c_m] if len(row) > c_m else None
            if (rawd is not None and str(rawd).strip()) or (rawm is not None and str(rawm).strip()):
                date_bad += 1  # 填了但解析不出（如收单月份写成"7月"）→ 该行被静默剔除
    return date_bad, amt_bad


def _data_health(cfg, cc, project, orders, receipts, inhouse, ledger_rows, ledger_year, lcols,
                 P, today, unclassified, month_keys, manual_raw):
    """数据体检：每个源的覆盖情况 + 关键校验 → 让人信这个数。"""
    year = today.year

    def months_of(rows, col):
        ms = set()
        for r in rows:
            p = loaders.parse_date_parts(r.get(col))
            if p and p[0] == year:
                ms.add(p[1])
        return sorted(ms)

    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    inhouse_hit = sum(1 for r in inhouse if kw in str(r.get(cc["inhouse_type"], "")).upper())
    led_ms = sorted({p[1] for r in ledger_rows
                     if (p := periods.ledger_row_date(r, ledger_year, lcols)) and p[0] == year})

    sources = [
        {"name": "项目明细(智云)", "rows": len(project), "months": months_of(project, cc["project_delivery_date"])},
        {"name": "下单(智云)", "rows": len(orders), "months": months_of(orders, cc["order_date"])},
        {"name": "回款(智云)", "rows": len(receipts), "months": months_of(receipts, cc["receipt_date"])},
        {"name": "内部译员·IN-HOUSE(智云)", "rows": inhouse_hit, "months": months_of(inhouse, cc["inhouse_date"])},
        {"name": "收单台账", "rows": len(ledger_rows), "months": led_ms},
    ]

    warnings = []
    # 某源整表读到 0 行 = 文件空 / 导错
    for s in sources:
        if s["rows"] == 0:
            warnings.append(f"{s['name']} 读到 0 行（文件空或导错，请核对）")
    # 坏值计数：日期解析不出=整行被剔除、金额解析不出=按0算——都不能无声发生
    value_scans = [
        ("项目明细(智云)", *_scan_dict_source_issues(project, cc["project_delivery_date"], cc["project_revenue"])),
        ("下单(智云)", *_scan_dict_source_issues(orders, cc["order_date"], cc["order_amount"])),
        ("回款(智云)", *_scan_dict_source_issues(receipts, cc["receipt_date"], cc["receipt_amount"])),
        ("内部译员(智云)", *_scan_dict_source_issues(inhouse, cc["inhouse_date"], cc["inhouse_amount"])),
        ("收单台账", *_scan_ledger_issues(ledger_rows, ledger_year, lcols)),
    ]
    for name, date_bad, amt_bad in value_scans:
        if date_bad:
            warnings.append(f"{name} 有 {date_bad} 行日期解析不出，已被剔除不计入任何周期（请核对源表日期格式）")
        if amt_bad:
            warnings.append(f"{name} 有 {amt_bad} 行金额非数字，按 0 计（请核对源表金额格式）")
    # 手填：未填=0（不再沿用上月）；缺整月提示陆总补录
    if not manual_raw:
        warnings.append("手填为空或未读到：全部手填项按 0 计（利润可能虚高，请到管理端「人工填写」补录）")
    else:
        miss = manual_missing_months(cfg, manual_raw, today.year, today.month)
        if miss:
            show = "、".join(miss[:4]) + ("…" if len(miss) > 4 else "")
            warnings.append(f"手填缺 {len(miss)} 个月未录（{show}）：缺月按 0 计，请当月补填")
    # 有收入的月却期间费用为 0 = 收单台账疑似缺该月（活跃月费用不该为0）——比"某月无收入"更可信，不误报淡季
    for k in month_keys:
        if P[k]["revenue_net"] > 0 and P[k]["expense"]["total"] == 0:
            warnings.append(f"{P[k]['label']}有收入但期间费用为0（疑似收单台账缺该月）")
    if inhouse_hit == 0 and len(inhouse) > 0:
        warnings.append("内部译员表没筛到 IN-HOUSE 行 → 内部译员成本按0算；请确认导出时按「译员类型-资源库=IN-HOUSE」筛过")
    if unclassified["expense"]["count"]:
        warnings.append(f"收单台账 {unclassified['expense']['count']} 笔未填「对应报表大类」（{unclassified['expense']['amount']/1e4:.1f}万），未计入费用")
    return {"sources": sources, "warnings": warnings, "ok": len(warnings) == 0}
