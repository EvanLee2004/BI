#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营利润计算：年/季/月全周期矩阵，算到「税前利润」。全部在 Python 算完，前端不做任何金额运算。

口径（陆总 2026-07-03 定稿）：
- 收入(不含税) = Σ交付额/本币 ÷ (1+税率)，按整单交付日期。
- 生产成本 = 系统直接成本(项目成本) − 系统内部译员成本(in-house本币结算) + 手填6项(PM/VM/实际内部译员/税费损失/技术流量/其他)。
- 毛利 = 收入 − 生产成本。
- 营销费用 = 营销人力成本(手填) + 市场费用(台账)；管理费用 = 管理人力成本(手填) + 管理费用(台账)；
  固定运营费用(台账)；研发费用 = 研发人力成本(手填) + 技术服务费(台账)；
  财务费用 = 财务费用(台账) + 财务费用补充(手填)。
- 附加税费 = 增值税额 × 附加税率（增值税=不含税收入×6%，附加=×12%），系统自动算。
  注意基数是**不含税收入 net**（net×6% 恰等于增值税额 gross−net），不是含税交付额 gross——别写成"收入×6%×12%"引歧义。
- 其他损益(手填，默认0)。
- 税前利润 = 毛利 − 营销 − 管理 − 固定运营 − 研发 − 财务 − 附加税费 + 其他损益。
- 手填项：某月没填 → default=prev 取上月、default=zero 取0；年/季周期 = 期间内各月手填之和。
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


def compute_ranking(rows, name_col, amount_col, date_col, start, end, top=10, empty_label="（未填）"):
    """按 name_col 汇总期内金额并降序排名。返回 {items:[{name,amount,count}…前top], others:{names,amount,count}|None,
    unfilled:{amount,count}|None, total}。count=笔数；amount 已 round(2)。
    名字为空归"（未填）"→ 单拆 unfilled 固定置底展示（不参与前top排位，但计入 total=守恒：各组合计==总额）。"""
    agg: dict[str, list] = {}
    for r in rows:
        if not periods.date_in_range(loaders.parse_date_parts(r.get(date_col)), start, end):
            continue
        name = str(r.get(name_col) or "").strip() or empty_label
        a = agg.setdefault(name, [0.0, 0])
        a[0] += loaders.parse_amount(r.get(amount_col))
        a[1] += 1
    total = round(sum(v[0] for v in agg.values()), 2)
    uf = agg.pop(empty_label, None)
    unfilled = {"amount": round(uf[0], 2), "count": uf[1]} if uf else None
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])
    items = [{"name": n, "amount": round(v[0], 2), "count": v[1]} for n, v in ranked[:top]]
    rest = ranked[top:]
    others = ({"names": len(rest), "amount": round(sum(v[0] for _, v in rest), 2),
               "count": sum(v[1] for _, v in rest)} if rest else None)
    return {"items": items, "others": others, "unfilled": unfilled, "total": total}


def compute_daily(order_rows, receipt_rows, cols_cfg, start, end, top=10):
    """按天明细（/api/daily 实时算·纯函数只吃行数据）：任意日期区间 → 逐日下单/回款合计 + 期内排名。
    days 只含有业务发生的日（稀疏），升序；totals 与逐日合计守恒（测试守卫 ∑days==compute_orders/receipts）。
    只做下单/回款——费用/手填按月，切不出按天利润（2026-07-10 拍板口径）。"""
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
        "orders_by_dept": compute_ranking(order_rows, "部门", cols_cfg["order_amount"],
                                          cols_cfg["order_date"], start, end, top),
        "orders_by_sales": compute_ranking(order_rows, "销售", cols_cfg["order_amount"],
                                           cols_cfg["order_date"], start, end, top),
        "receipts_by_customer": compute_ranking(receipt_rows, "客户", cols_cfg["receipt_amount"],
                                                cols_cfg["receipt_date"], start, end, top),
    }
    return {"days": out_days, "totals": totals, "rankings": rankings}


def compute_inhouse_cost(inhouse_rows, cols_cfg, cfg, start, end):
    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    tcol = cols_cfg["inhouse_type"]
    return _sum_amount_in_period(
        inhouse_rows, cols_cfg["inhouse_amount"], cols_cfg["inhouse_date"], start, end,
        extra=lambda r: kw in str(r.get(tcol, "")).upper(),
    )


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
    没填任何部门预算 → None（页面不出卡）。只列有预算的部门（执行卡本意=管控）。"""
    budgets = (dept_budget_raw or {}).get(str(year)) or {}
    if not budgets:
        return None
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
    """把手填表补成每月一份（1..cur_month）：default=prev 缺则取上月、default=zero 缺则取0。"""
    items = cfg["manual_items"]
    filled: dict[tuple[int, int], dict[str, float]] = {}
    for m in range(1, cur_month + 1):
        key = f"{year}-{m:02d}"
        row = manual_raw.get(key, {})
        cur: dict[str, float] = {}
        prev = filled.get((year, m - 1), {})
        for it in items:
            name, dflt = it["name"], it["default"]
            if name in row:
                cur[name] = row[name]
            elif dflt == "prev":
                cur[name] = prev.get(name, 0.0)
            else:
                cur[name] = 0.0
        filled[(year, m)] = cur
    return filled


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
    production_cost = round(rc["system_direct_cost"] - inhouse + prod_manual, 2)
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
    # 回款下单率 = 本期回款 ÷ 本期下单（资金回笼节奏参考，非当期回收率）；无下单则无意义置 None
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
        # 板块③ 排名：下单按部门/按销售，回款按客户（期内汇总降序，前10+其余合计）
        "rankings": {
            "orders_by_dept": compute_ranking(order_rows, "部门", cols_cfg["order_amount"],
                                              cols_cfg["order_date"], start, end),
            "orders_by_sales": compute_ranking(order_rows, "销售", cols_cfg["order_amount"],
                                               cols_cfg["order_date"], start, end),
            "receipts_by_customer": compute_ranking(receipt_rows, "客户", cols_cfg["receipt_amount"],
                                                    cols_cfg["receipt_date"], start, end),
        },
    }


# ---------- 顶层 ----------
def build_budget_block(budget_raw, year, year_period) -> dict | None:
    """年度预算完成块：{目标/累计/完成率}×下单+回款。没填预算数 → None（页面维持现状）。
    完成率分母=0 或指标没填 → 对应项为 None，前端显示需防 None。"""
    y = (budget_raw or {}).get(str(year)) or {}
    order_t, receipt_t = y.get("下单年预算"), y.get("回款年预算")
    if order_t is None and receipt_t is None:
        return None

    def _item(target, done):
        if target is None:
            return None
        return {"target": target, "done": done,
                "pct": (done / target * 100.0) if target else None}
    return {"year": year,
            "order": _item(order_t, year_period["orders"]),
            "receipt": _item(receipt_t, year_period["receipts"])}


def build_summary(cfg, project_rows, order_rows, receipt_rows, inhouse_rows,
                  ledger_header, ledger_rows, ledger_year, today, manual_raw=None,
                  budget_raw=None, dept_budget_raw=None):
    cols_cfg = cfg["columns"]
    lcols = columns.resolve_ledger_columns(ledger_header)
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
    # 回款柱图叠加"每月回款下单率"用：逐月 (标签, 回款, 下单, 回款下单率%)；率为 None 表示当月无下单
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
    return {
        "meta": {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "year": today.year, "year_key": year_key, "current_month_key": cur_month_key,
            "current_month_label": P[cur_month_key]["label"],
            "ledger_sheet_used": str(ledger_year), "tab_groups": tab_groups,
            "budget": build_budget_block(budget_raw, today.year, P[year_key]),
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


# 空台账表头（与 db.LEDGER_STD_COLS 同序；BU 口径=公共费用暂不分摊 → 台账费用恒 0）
_BU_EMPTY_LEDGER_HEADER = ["收单月份", "收单日期", "含税金额", "业务BU",
                           "对应报表大类", "预算明细费用类型", "预算归属部门"]


def build_bu_summary(cfg, project_rows, order_rows, receipt_rows, inhouse_rows, today, sales_set):
    """单 BU summary：四源行按销售名单过滤后，**复用 build_summary 全套口径**（公式一字不改）。
    公共费用暂不分摊 → 传空台账（台账费用项恒 0）；手填按 BU 陆总还没填 → 传空手填（恒 0，
    页面标注"待陆总手填"）；预算不进 BU 页（None）。=> BU 税前利润=毛利−附加税费（其余行待补）。"""
    return build_summary(
        cfg,
        filter_rows_by_sales(project_rows, sales_set),
        filter_rows_by_sales(order_rows, sales_set),
        filter_rows_by_sales(receipt_rows, sales_set),
        filter_rows_by_sales(inhouse_rows, sales_set),
        list(_BU_EMPTY_LEDGER_HEADER), [], today.year, today,
        manual_raw={}, budget_raw=None, dept_budget_raw=None)


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
    # 手填表跨年防线：default=上月 的链条从1月起算，缺1月=前几个月静默按0
    if not manual_raw:
        warnings.append("手填与调整表为空或未读到：全部手填项按 0 计（利润会虚高）")
    elif f"{today.year}-01" not in manual_raw:
        warnings.append(f"手填表没有 {today.year}-01 列：default=上月 的手填项在有填数之前按 0 起算（跨年后请先补 1 月）")
    # 有收入的月却期间费用为 0 = 收单台账疑似缺该月（活跃月费用不该为0）——比"某月无收入"更可信，不误报淡季
    for k in month_keys:
        if P[k]["revenue_net"] > 0 and P[k]["expense"]["total"] == 0:
            warnings.append(f"{P[k]['label']}有收入但期间费用为0（疑似收单台账缺该月）")
    if inhouse_hit == 0 and len(inhouse) > 0:
        warnings.append("内部译员表没筛到 IN-HOUSE 行 → 内部译员成本按0算；请确认导出时按「译员类型-资源库=IN-HOUSE」筛过")
    if unclassified["expense"]["count"]:
        warnings.append(f"收单台账 {unclassified['expense']['count']} 笔未填「对应报表大类」（{unclassified['expense']['amount']/1e4:.1f}万），未计入费用")
    return {"sources": sources, "warnings": warnings, "ok": len(warnings) == 0}
