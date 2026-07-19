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

import loaders
import periods

from .budget_manual import manual_missing_months


# pure-move funcs from _impl.py

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


def _scan_future_dates_dict(rows, date_col, today: datetime.date, max_samples: int = 3):
    """任务书37·B10：归属日期 > 今天 的行数与样例（不拦数据）。"""
    n = 0
    samples: list[str] = []
    for r in rows or []:
        p = loaders.parse_date_parts(r.get(date_col) if isinstance(r, dict) else None)
        if not p:
            continue
        try:
            d = datetime.date(int(p[0]), int(p[1]), int(p[2]))
        except (TypeError, ValueError):
            continue
        if d > today:
            n += 1
            if len(samples) < max_samples:
                samples.append(d.isoformat())
    return n, samples


def _scan_future_dates_ledger(ledger_rows, ledger_year, lcols, today: datetime.date, max_samples: int = 3):
    n = 0
    samples: list[str] = []
    for row in ledger_rows or []:
        p = periods.ledger_row_date(row, ledger_year, lcols)
        if not p:
            continue
        try:
            d = datetime.date(int(p[0]), int(p[1]), int(p[2]))
        except (TypeError, ValueError):
            continue
        if d > today:
            n += 1
            if len(samples) < max_samples:
                samples.append(d.isoformat())
    return n, samples


def _data_health(  # noqa: C901
    cfg,
    cc,
    project,
    orders,
    receipts,
    inhouse,
    ledger_rows,
    ledger_year,
    lcols,
    P,
    today,
    unclassified,
    month_keys,
    manual_raw,
):
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
    led_ms = sorted(
        {p[1] for r in ledger_rows if (p := periods.ledger_row_date(r, ledger_year, lcols)) and p[0] == year}
    )

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
        warnings.append(
            "内部译员表没筛到 IN-HOUSE 行 → 内部译员成本按0算；请确认导出时按「译员类型-资源库=IN-HOUSE」筛过"
        )
    if unclassified["expense"]["count"]:
        warnings.append(
            f"收单台账 {unclassified['expense']['count']} 笔未填「对应报表大类」（{unclassified['expense']['amount'] / 1e6:.1f}万），未计入费用"
        )
    # 任务书37·B10：归属日期 > 今天 → 体检黄（条数+样例），不拦管道。
    # 内部译员只扫 IN-HOUSE（与 norm_inhouse/入库一致，避免文件全表 vs 库过滤后计数对不上红线）。
    inhouse_for_future = [
        r for r in inhouse if kw in str(r.get(cc["inhouse_type"], "")).upper()
    ]
    future_scans = [
        ("项目明细(智云)", *_scan_future_dates_dict(project, cc["project_delivery_date"], today)),
        ("下单(智云)", *_scan_future_dates_dict(orders, cc["order_date"], today)),
        ("回款(智云)", *_scan_future_dates_dict(receipts, cc["receipt_date"], today)),
        ("内部译员(智云)", *_scan_future_dates_dict(inhouse_for_future, cc["inhouse_date"], today)),
        ("收单台账", *_scan_future_dates_ledger(ledger_rows, ledger_year, lcols, today)),
    ]
    for name, n_fut, samples in future_scans:
        if n_fut:
            samp = "、".join(samples) + ("…" if n_fut > len(samples) else "")
            warnings.append(f"{name} 有 {n_fut} 行归属日期晚于今天（样例 {samp}），已计入对应未来月、不拦截")
    return {"sources": sources, "warnings": warnings, "ok": len(warnings) == 0}

def load_manual_safe(cfg):
    try:
        return loaders.load_manual(cfg)
    except FileNotFoundError:
        return {}

