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

import datetime
from collections import defaultdict
from typing import Any

import columns
import periods
import money

from .constants import _PC_TO_BU, _PUBLIC_PC
from .budget_manual import _month_num, build_budget_block, build_manual_monthly, build_period
from .expense_period import (
    build_dept_budget_block,
    compute_expense_monthly_by_cat,
    compute_expenses_by_fine_type,
    compute_expenses_by_group,
    detax_ledger_rows,
    inject_manual_alloc_into_breakdowns,
)
from .misc import _data_health
from .tax_revenue import compute_orders
from .misc import load_manual_safe


# pure-move funcs from _impl.py

def build_summary(
    cfg,
    project_rows,
    order_rows,
    receipt_rows,
    inhouse_rows,
    ledger_header,
    ledger_rows,
    ledger_year,
    today,
    manual_raw=None,
    budget_raw=None,
    dept_budget_raw=None,
    detax_rates=None,
):
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
        P[key] = build_period(
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
            today,
        )
        P[key]["range"] = (start.isoformat(), end.isoformat())  # 排名卡「其余」点开全量明细要带的区间
        fine[key] = compute_expenses_by_fine_type(ledger_rows, ledger_year, start, end, cfg, lcols)
        by_dept[key] = compute_expenses_by_group(ledger_rows, ledger_year, start, end, cfg, lcols, "预算归属部门")
        by_pc[key] = compute_expenses_by_group(ledger_rows, ledger_year, start, end, cfg, lcols, "业务BU")
        # 2.2.4·② 手填三类补进费用三视图（分；不改核心 expense total/pretax）
        fine[key], by_pc[key], by_dept[key] = inject_manual_alloc_into_breakdowns(
            P[key].get("manual"), cfg, fine[key], by_pc[key], by_dept[key]
        )
        tab_groups[group].append(key)

    year_key = f"{today.year}年"
    cur_month_key = f"{today.year}年{today.month}月"
    month_keys = tab_groups["月"]
    trend = [
        (
            P[k]["label"].replace(f"{today.year}年", ""),
            P[k]["revenue_net"],
            P[k]["production_cost"],
            P[k]["gross_margin_pct"],
        )
        for k in month_keys
    ]
    receipt_monthly = [(P[k]["label"].replace(f"{today.year}年", ""), P[k]["receipts"]) for k in month_keys]
    # 回款柱图叠加"每月回款/下单比"用：逐月 (标签, 回款, 下单, 回款/下单比%)；率为 None 表示当月无下单
    receipt_order_monthly = [
        (
            P[k]["label"].replace(f"{today.year}年", ""),
            P[k]["receipts"],
            P[k]["orders"],
            P[k]["receipt_order_ratio_pct"],
        )
        for k in month_keys
    ]

    unclassified = columns.build_unclassified_summary(
        ledger_rows,
        cfg,
        lcols,
        amount_filter=lambda r: periods.date_in_range(
            periods.ledger_row_date(r, ledger_year, lcols),
            datetime.date(today.year, 1, 1),
            datetime.date(today.year, 12, 31),
        ),
    )
    health = _data_health(
        cfg,
        cols_cfg,
        project_rows,
        order_rows,
        receipt_rows,
        inhouse_rows,
        ledger_rows,
        ledger_year,
        lcols,
        P,
        today,
        unclassified,
        month_keys,
        manual_raw,
    )
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
    # 任务书39·E：全年费用×大类矩阵（显示层再按 B8 隐工资；算账口径不改）
    expense_monthly_by_cat = compute_expense_monthly_by_cat(
        ledger_rows,
        ledger_year,
        lcols,
        cfg,
        year=today.year,
        hide_salary=False,
        filled_manual=filled_manual,
    )
    return {
        "meta": {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "year": today.year,
            "year_key": year_key,
            "current_month_key": cur_month_key,
            "current_month_label": P[cur_month_key]["label"],
            "ledger_sheet_used": str(ledger_year),
            "tab_groups": tab_groups,
            "budget": build_budget_block(budget_raw, today.year, P[year_key], h1_period),
            "dept_budget": build_dept_budget_block(dept_budget_raw, by_dept.get(year_key), today.year),
            "unclassified": unclassified,
            "health": health,
        },
        "periods": P,
        "expense_fine_type": fine,
        "expense_by_department": by_dept,
        "expense_by_profit_center": by_pc,
        "trend": trend,
        "receipt_monthly": receipt_monthly,
        "receipt_order_monthly": receipt_order_monthly,
        "expense_monthly_by_cat": expense_monthly_by_cat,
    }


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
    return {key: compute_orders(unassigned, cols_cfg, start, end) for key, (label, start, end, group) in ranges.items()}


def normalize_profit_center(raw) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s in _PUBLIC_PC:
        return "公共"
    return _PC_TO_BU.get(s, s)


def scan_unknown_profit_centers(ledger_rows, ledger_year, lcols, cfg, bu_names, year: int | None = None) -> list[dict]:
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
        amt = money.as_fen(row[c_amt] if len(row) > c_amt else None)
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
    out = [{"name": n, "count": c, "amount": round(a, 2)} for n, (c, a) in stats.items()]
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
            f"（¥{amt / 1e6:.1f} 万）——不进任何 BU 直记也不进公共池，请到设置核对 BU 名或修正台账"
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


