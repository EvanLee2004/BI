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

import periods

from .constants import _BU_EMPTY_LEDGER_HEADER, _LEDGER_TO_EXPENSE, ALLOC_IN_LABEL, ALLOC_OUT_LABEL
from .expense_period import expense_totals_from_man_led
from .summary import build_summary, filter_rows_by_sales


# pure-move funcs from _impl.py

def _apply_expense_and_pretax(p: dict, led: dict, cfg=None) -> None:
    """led 已含直记+公共分摊后：叠 J 类人工分摊，写 expense / pretax（与 build_period 同口径）。"""
    man = p.get("manual") or {}
    exp = expense_totals_from_man_led(man, led, cfg)
    p["ledger_expenses"] = led
    p["expense"] = {
        "营销费用": round(float(exp["营销费用"]), 2),
        "管理费用": round(float(exp["管理费用"]), 2),
        "固定运营费用": round(float(exp["固定运营费用"]), 2),
        "研发费用": round(float(exp["研发费用"]), 2),
        "财务费用": round(float(exp["财务费用"]), 2),
        "total": round(float(exp["total"]), 2),
    }
    total = float(p["expense"]["total"])
    p["pretax_profit"] = round(
        float(p["gross_profit"]) - total - float(p["surtax"]) + float(p.get("other_pl") or 0), 2
    )
    net = float(p.get("revenue_net") or 0)
    p["pretax_margin_pct"] = round(p["pretax_profit"] / net * 100, 2) if net else 0.0


def build_bu_summary(
    cfg,
    project_rows,
    order_rows,
    receipt_rows,
    inhouse_rows,
    today,
    sales_set,
    *,
    company_ledger_by_period=None,
    alloc_ratio_pct=None,
    alloc_enabled=False,
    budget_raw=None,
    ledger_header=None,
    ledger_rows=None,
    ledger_year=None,
    manual_raw=None,
    bu_name: str | None = None,
    detax_rates=None,
):
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
        lh,
        lr,
        ly,
        today,
        manual_raw=man,
        budget_raw=budget_raw,
        dept_budget_raw=None,
        detax_rates=detax_rates,
    )
    if bu_name:
        s.setdefault("meta", {})["bu_name"] = bu_name
    if alloc_enabled and alloc_ratio_pct is not None and company_ledger_by_period:
        apply_public_expense_allocation(s, company_ledger_by_period, float(alloc_ratio_pct), cfg=cfg)
    else:
        s.setdefault("meta", {})["public_allocation"] = {"enabled": False, "ratio_pct": None, "ratio_disp": ""}
    return s


def apply_public_expense_allocation(
    summary: dict, company_ledger_by_period: dict, ratio_pct: float, cfg=None
) -> None:
    """就地：把「公共池」台账 5 类 × 比例 **叠加** 进 BU 已有直记费用（不覆盖直记）。
    company_ledger_by_period 应为公共归属中心的费用；若传入全公司（旧测），则按比例拆全额——
    与「仅公共池」在无直记时数值等价。手填不摊；附加税按 BU 自身收入。
    任务书61·J：重算费用时必须叠 manual_alloc（房租/物业费/装修费），禁止 man+led 漏 mac。
    cfg 可选；缺省时 expense_totals_from_man_led 用内置三类 map。"""
    factor = float(ratio_pct) / 100.0
    P = summary.get("periods") or {}
    for key, p in P.items():
        led_src = company_ledger_by_period.get(key) or {}
        led = dict(p.get("ledger_expenses") or {})
        for cat in _LEDGER_TO_EXPENSE:
            add = round(float(led_src.get(cat) or 0.0) * factor, 2)
            led[cat] = round(float(led.get(cat) or 0.0) + add, 2)
        _apply_expense_and_pretax(p, led, cfg)
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": True,
        "ratio_pct": float(ratio_pct),
        "ratio_disp": f"{ratio_pct:g}%",
    }


def _merge_alloc_into_period(p: dict, add_by_cat: dict[str, float], cfg=None) -> None:
    """就地把分摊额（按台账 5 类）叠加进单周期的费用与税前（与整比例版同一套公式 + J mac）。"""
    led = dict(p.get("ledger_expenses") or {})
    for cat in _LEDGER_TO_EXPENSE:
        led[cat] = round(float(led.get(cat) or 0.0) + float(add_by_cat.get(cat) or 0.0), 2)
    # 记下本周期各类实际叠加的分摊额（迭代22·D4：BU 利润表抽屉把「直记」与「分摊自公共」分开展示）
    p["alloc_added"] = {cat: round(float(add_by_cat.get(cat) or 0.0), 2) for cat in _LEDGER_TO_EXPENSE}
    _apply_expense_and_pretax(p, led, cfg)


def _alloc_cats_for_range(
    public_month_led: dict, ratios_by_month: dict, bu_name: str, start, end, cap
) -> dict[str, float]:
    """某周期内：逐月 公共池5类 × 该月该 BU 比例，按类加总。缺月比例=0（不分摊）。"""
    add = {cat: 0.0 for cat in _LEDGER_TO_EXPENSE}
    for y, m in periods.months_in(start, end, cap):
        pct = (ratios_by_month.get(f"{y:04d}-{m:02d}") or {}).get(bu_name)
        if not pct:
            continue
        led = public_month_led.get((y, m)) or {}
        for cat in _LEDGER_TO_EXPENSE:
            add[cat] += float(led.get(cat) or 0.0) * float(pct) / 100.0
    return {cat: round(v, 2) for cat, v in add.items()}


def apply_public_expense_allocation_monthly(
    summary: dict, public_month_led: dict, ratios_by_month: dict, bu_name: str, today, cfg=None
) -> None:
    """就地：按月比例把公共池费用叠加进单 BU summary 各周期（迭代20）。
    public_month_led={(y,m):{5类:金额}}；ratios_by_month={'YYYY-MM':{BU:比例%}}；
    当月合计可 <100%（剩余留公司层）。没有任何生效比例 → meta 标 enabled=False。
    cfg：任务书61·J 重算费用时叠人工三类分摊；缺省用内置 map。"""
    P = summary.get("periods") or {}
    # 「已配置」与「有金额」分开：配置了比例（哪怕当期公共池为 0）也标注口径，别让读者以为没摊
    has_ratio = any((r or {}).get(bu_name) for r in ratios_by_month.values())
    for _key, p in P.items():
        rng = p.get("range")
        if not rng:
            continue
        start = datetime.date.fromisoformat(rng[0])
        end = datetime.date.fromisoformat(rng[1])
        add = _alloc_cats_for_range(public_month_led, ratios_by_month, bu_name, start, end, today)
        if not any(add.values()):
            continue
        _merge_alloc_into_period(p, add, cfg=cfg)
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": has_ratio,
        "mode": "monthly",
        "ratio_pct": None,
        "ratio_disp": "按月比例" if has_ratio else "",
    }


def alloc_amounts_by_period(
    public_month_led: dict, ratios_by_month: dict, bu_names: list[str], today
) -> dict[str, dict[str, float]]:
    """每周期每 BU 的分摊总额（供全公司「构成·按业务BU」视图跟着挪·迭代20）。
    只认在 bu_names 里的 BU（孤儿比例行由调用方另行告警）。返回 {周期key: {BU: 金额}}。"""
    want = set(bu_names or [])
    ranges = periods.all_period_ranges(today)
    out: dict[str, dict[str, float]] = {}
    for key, (_lab, start, end, _grp) in ranges.items():
        per: dict[str, float] = {}
        for y, m in periods.months_in(start, end, today):
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
    if "公共" not in gmap:  # 分摊额来自公共池；池不存在说明上游没数，不动
        return groups
    for b, amt in alloc_by_bu.items():
        if amt <= 0:
            continue
        t, f = gmap.get(b, (0.0, []))
        gmap[b] = (round(t + amt, 2), f + [(ALLOC_IN_LABEL, round(amt, 2))])
    t, f = gmap["公共"]
    gmap["公共"] = (round(t - total_alloc, 2), f + [(ALLOC_OUT_LABEL, round(-total_alloc, 2))])
    return [(g, t, sorted(f, key=lambda x: -x[1])) for g, (t, f) in sorted(gmap.items(), key=lambda kv: -kv[1][0])]




