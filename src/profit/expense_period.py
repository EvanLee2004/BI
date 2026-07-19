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

from collections import defaultdict

import loaders
import columns
import periods
import money

from .constants import EXPENSE_GROUP_UNFILLED
from .tax_revenue import _sum_amount_in_period, compute_ranking


# pure-move funcs from _impl.py

def compute_expense_monthly_by_cat(  # noqa: C901
    ledger_rows,
    ledger_year,
    lcols,
    cfg,
    *,
    year: int,
    profit_center: str | None = None,
    hide_salary: bool = False,
    alloc_by_month: dict | None = None,
):
    """任务书39·E：全年 1~12 月 × 报表大类 费用矩阵（金额=分）。

    profit_center：BU 页只计「利润归属中心」=该 BU 的直记行；None=全公司。
    alloc_by_month：{(y,m):{大类:分}} 分摊自公共（BU 页叠加，与利润表费用口径一致）。
    hide_salary=True：工资并入「其他」并记 note（跟随 B8 工资明细开关）。
    返回 {categories:[...], months:[{m,total,by_cat:{…}}], salary_merged:bool}。
    """
    included = list(cfg.get("expense_categories_included") or [])
    excluded = list(cfg.get("expense_categories_excluded") or [])
    # 图用台账大类全集（含成本/工资等排除类，便于领导看构成）
    all_cats = []
    for c in included + excluded:
        if c and c not in all_cats and c != "非利润表":
            all_cats.append(c)
    by_m: dict[int, dict[str, float]] = {m: defaultdict(float) for m in range(1, 13)}
    c_amt = lcols.get("含税金额")
    c_pc = lcols.get("业务BU")
    if c_amt is None:
        return {"categories": all_cats, "months": [], "salary_merged": False, "note": ""}
    for row in ledger_rows:
        d = periods.ledger_row_date(row, ledger_year, lcols)
        if not d or d[0] != year:
            continue
        m = int(d[1])
        if m < 1 or m > 12:
            continue
        if profit_center is not None and c_pc is not None:
            pc = str(row[c_pc] if len(row) > c_pc else "").strip()
            if pc != profit_center:
                continue
        amt = money.as_fen(row[c_amt] if len(row) > c_amt else None)
        if not amt:
            continue
        cat, is_unc = columns.classify_expense_category(row, cfg, lcols)
        if is_unc or not cat or cat == "非利润表":
            continue
        if cat not in all_cats:
            all_cats.append(cat)
        by_m[m][cat] += amt
    # 叠加分摊
    if alloc_by_month:
        for (y, m), cats in alloc_by_month.items():
            if int(y) != year or m < 1 or m > 12:
                continue
            for cat, amt in (cats or {}).items():
                if cat and cat != "非利润表":
                    if cat not in all_cats:
                        all_cats.append(cat)
                    by_m[m][cat] += float(amt or 0)
    salary_merged = False
    note = ""
    if hide_salary and "工资" in all_cats:
        salary_merged = True
        note = "工资大类已并入「其他」（全端隐藏，不单列）"
        if "其他" not in all_cats:
            all_cats.append("其他")
        for m in range(1, 13):
            sal = float(by_m[m].pop("工资", 0) or 0)
            if sal:
                by_m[m]["其他"] += sal
        all_cats = [c for c in all_cats if c != "工资"]
    months = []
    for m in range(1, 13):
        bc = {c: round(float(by_m[m].get(c) or 0), 2) for c in all_cats}
        total = round(sum(bc.values()), 2)
        months.append({"m": m, "total": total, "by_cat": bc})
    return {"categories": all_cats, "months": months, "salary_merged": salary_merged, "note": note}


def compute_daily(order_rows, receipt_rows, cols_cfg, start, end, top=10, sales_to_bu=None):
    """按天明细（/api/daily 实时算·纯函数只吃行数据）：任意日期区间 → 逐日下单/回款合计 + 期内排名。
    days 只含有业务发生的日（稀疏），升序；totals 与逐日合计守恒（测试守卫 ∑days==compute_orders/receipts）。
    只做下单/回款——费用/手填按月，切不出按天利润（2026-07-10 拍板口径）。
    sales_to_bu={销售名:BU名} 有值时额外算 rankings.orders_by_bu（与全年预渲染「下单·按BU」同口径）。"""
    days: dict[str, list] = {}  # day -> [下单额, 下单笔数, 回款额, 回款笔数]

    def _acc(rows, amount_col, date_col, ai, ci):
        for r in rows:
            d = loaders.parse_date_parts(r.get(date_col))
            if not periods.date_in_range(d, start, end):
                continue
            slot = days.setdefault(f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}", [0.0, 0, 0.0, 0])
            slot[ai] += money.as_fen(r.get(amount_col))
            slot[ci] += 1

    _acc(order_rows, cols_cfg["order_amount"], cols_cfg["order_date"], 0, 1)
    _acc(receipt_rows, cols_cfg["receipt_amount"], cols_cfg["receipt_date"], 2, 3)
    out_days = [
        {"day": k, "orders": round(v[0], 2), "orders_count": v[1], "receipts": round(v[2], 2), "receipts_count": v[3]}
        for k, v in sorted(days.items())
    ]
    totals = {
        "orders": round(sum(v[0] for v in days.values()), 2),
        "orders_count": sum(v[1] for v in days.values()),
        "receipts": round(sum(v[2] for v in days.values()), 2),
        "receipts_count": sum(v[3] for v in days.values()),
    }
    rankings = {
        "orders_by_sales": compute_ranking(
            order_rows, "销售", cols_cfg["order_amount"], cols_cfg["order_date"], start, end, top
        ),
        "orders_by_customer": compute_ranking(
            order_rows, "客户", cols_cfg["order_amount"], cols_cfg["order_date"], start, end, top
        ),
        "receipts_by_sales": compute_ranking(
            receipt_rows, "销售", cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end, top
        ),
        "receipts_by_customer": compute_ranking(
            receipt_rows, "客户", cols_cfg["receipt_amount"], cols_cfg["receipt_date"], start, end, top
        ),
    }
    if sales_to_bu:
        smap = {str(k).strip(): v for k, v in sales_to_bu.items() if str(k).strip()}

        def _bu_of(row):
            return smap.get(str(row.get("销售") or "").strip(), "")

        rankings["orders_by_bu"] = compute_ranking(
            order_rows,
            "销售",
            cols_cfg["order_amount"],
            cols_cfg["order_date"],
            start,
            end,
            top,
            empty_label="（未归属）",
            name_of=_bu_of,
        )
    return {"days": out_days, "totals": totals, "rankings": rankings}


def compute_inhouse_cost(inhouse_rows, cols_cfg, cfg, start, end):
    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    tcol = cols_cfg["inhouse_type"]
    return _sum_amount_in_period(
        inhouse_rows,
        cols_cfg["inhouse_amount"],
        cols_cfg["inhouse_date"],
        start,
        end,
        extra=lambda r: kw in str(r.get(tcol, "")).upper(),
    )


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
            amt_fen = money.as_fen(row[c_amt])
            if amt_fen:
                lst = list(row)
                # 去税在元上除，结果仍以元 float 写回行（下游 as_fen 再入分）——与旧「元路径」舍入一致
                lst[c_amt] = money.fen_to_yuan(amt_fen) / (1.0 + float(r) / 100.0)
                row = tuple(lst)
        out.append(row)
    return out


def compute_ledger_expenses(ledger_rows, ledger_year, start, end, cfg, lcols):
    included = cfg["expense_categories_included"]
    by_cat = defaultdict(float)
    count = 0
    c_amt = lcols["含税金额"]
    for row in ledger_rows:
        amt = money.as_fen(row[c_amt] if len(row) > c_amt else None)
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
        amt = money.as_fen(row[c_amt] if len(row) > c_amt else None)
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
        amt = money.as_fen(row[c_amt] if len(row) > c_amt else None)
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
    return [
        (g, round(v, 2), sorted(fine[g].items(), key=lambda x: -x[1]))
        for g, v in sorted(agg.items(), key=lambda x: -x[1])
    ]


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
        rows.append(
            {"dept": dept, "target": target, "used": round(u, 2), "pct": (u / target * 100.0) if target else None}
        )
    rows.sort(key=lambda r: (r["pct"] is None, -(r["pct"] or 0)))
    return {"year": year, "rows": rows}


