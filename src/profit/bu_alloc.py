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
from decimal import Decimal

import money
import periods

from .constants import _BU_EMPTY_LEDGER_HEADER, _LEDGER_TO_EXPENSE, ALLOC_IN_LABEL, ALLOC_OUT_LABEL
from .expense_period import _fen_amount, expense_totals_from_man_led, pretax_profit_fen
from .summary import build_summary, filter_rows_by_sales


# pure-move funcs from _impl.py

def _apply_expense_and_pretax(p: dict, led: dict, cfg=None) -> None:
    """led 已含直记+公共分摊后：叠 J 类人工分摊，写 expense / pretax（与 build_period 同口径）。

    2.6.13：全程 int 分；禁止 round(float(...)) 写费用/税前。
    """
    man = p.get("manual") or {}
    exp = expense_totals_from_man_led(man, led, cfg)
    p["ledger_expenses"] = led
    p["expense"] = {k: int(v) for k, v in exp.items()}
    p["pretax_profit"] = pretax_profit_fen(
        int(p["gross_profit"]),
        int(p["expense"]["total"]),
        int(p["surtax"]),
        int(p.get("other_pl") or 0),
    )
    net = int(p.get("revenue_net") or 0)
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
    任务书61·J：重算费用时必须叠 manual_alloc（手填 2.3.3：房租物业/其他/装修费），禁止 man+led 漏 mac。
    cfg 可选；缺省时 expense_totals_from_man_led 用内置三类 map。"""
    # 2.6.13：分摊份额 = 基数(分) × (pct/100)，HALF_UP 整分
    rate = Decimal(str(ratio_pct)) / Decimal(100)
    P = summary.get("periods") or {}
    for key, p in P.items():
        led_src = company_ledger_by_period.get(key) or {}
        led = dict(p.get("ledger_expenses") or {})
        for cat in _LEDGER_TO_EXPENSE:
            add = money.mul_rates_fen(_fen_amount(led_src.get(cat)), rate)
            led[cat] = _fen_amount(led.get(cat)) + int(add)
        _apply_expense_and_pretax(p, led, cfg)
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": True,
        "ratio_pct": float(ratio_pct),
        "ratio_disp": f"{ratio_pct:g}%",
    }


def _merge_alloc_into_period(p: dict, add_by_cat: dict, cfg=None) -> None:
    """就地把分摊额（按台账 5 类）叠加进单周期的费用与税前（与整比例版同一套公式 + J mac）。

    2.6.13：add/led 写回 int 分。
    """
    led = dict(p.get("ledger_expenses") or {})
    for cat in _LEDGER_TO_EXPENSE:
        led[cat] = _fen_amount(led.get(cat)) + _fen_amount(add_by_cat.get(cat))
    # 记下本周期各类实际叠加的分摊额（迭代22·D4：BU 利润表抽屉把「直记」与「分摊自公共」分开展示）
    p["alloc_added"] = {cat: _fen_amount(add_by_cat.get(cat)) for cat in _LEDGER_TO_EXPENSE}
    _apply_expense_and_pretax(p, led, cfg)


def _alloc_cats_for_range(
    public_month_led: dict, ratios_by_month: dict, bu_name: str, start, end, cap
) -> dict[str, int]:
    """某周期内：逐月 公共池5类 × 该月该 BU 比例，按类加总。缺月比例=0（不分摊）。

    2.6.13：mul_rates_fen HALF_UP 整分。
    """
    add = {cat: 0 for cat in _LEDGER_TO_EXPENSE}
    for y, m in periods.months_in(start, end, cap):
        pct = (ratios_by_month.get(f"{y:04d}-{m:02d}") or {}).get(bu_name)
        if not pct:
            continue
        rate = Decimal(str(pct)) / Decimal(100)
        led = public_month_led.get((y, m)) or {}
        for cat in _LEDGER_TO_EXPENSE:
            add[cat] += money.mul_rates_fen(_fen_amount(led.get(cat)), rate)
    return {cat: int(v) for cat, v in add.items()}


def _share_by_pct(amt_fen: int, pct: float) -> int:
    """分 × 百分数/100，HALF_UP 整分。"""
    return money.mul_rates_fen(amt_fen, Decimal(str(pct)) / Decimal(100))


def _shares_pct_rules(fine: str, amt: int, item_rules: dict[str, dict]) -> list[tuple[str, int]]:
    total_pct = sum(float((r or {}).get("value") or 0) for r in item_rules.values())
    if total_pct > 100.0 + 1e-9:
        raise ValueError(f"明细「{fine}」比例合计 {total_pct:.1f}% 超过 100%")
    return [
        (str(bu), _share_by_pct(amt, float((r or {}).get("value") or 0)))
        for bu, r in item_rules.items()
        if float((r or {}).get("value") or 0)
    ]


def _shares_yuan_rules(fine: str, amt: int, item_rules: dict[str, dict]) -> list[tuple[str, int]]:
    total_yuan = sum(float((r or {}).get("value") or 0) for r in item_rules.values())
    amount_yuan = float(money.fen_to_yuan(amt))
    if total_yuan > amount_yuan + 1e-9:
        raise ValueError(f"明细「{fine}」金额合计 {total_yuan:.2f} 超过本项 {amount_yuan:.2f}")
    out: list[tuple[str, int]] = []
    for bu, r in item_rules.items():
        yuan = float((r or {}).get("value") or 0)
        if yuan:
            out.append((str(bu), int(money.yuan_to_fen(yuan) or 0)))
    return out


def _shares_for_detail_item(
    fine: str,
    amount: int | float,
    item_rules: dict[str, dict],
    default_ratios: dict[str, float],
) -> list[tuple[str, int]]:
    """单明细项 → [(BU, 摊入分 int), ...]。超额 / 混模式 → ValueError。

    2.6.13：比例份额用 mul_rates_fen；金额模式仍 value=元 → yuan_to_fen。
    """
    amt = _fen_amount(amount)
    if item_rules:
        modes = {str((r or {}).get("mode") or "") for r in item_rules.values()}
        modes.discard("")
        if len(modes) > 1:
            raise ValueError(f"明细「{fine}」不可混合比例与金额模式")
        mode = next(iter(modes)) if modes else ""
        if mode == "比例":
            return _shares_pct_rules(fine, amt, item_rules)
        if mode == "金额":
            return _shares_yuan_rules(fine, amt, item_rules)
        raise ValueError(f"明细「{fine}」未知模式：{mode}")
    total_pct = sum(float(v or 0) for v in default_ratios.values())
    if total_pct > 100.0 + 1e-9:
        raise ValueError(f"默认分摊比例合计 {total_pct:.1f}% 超过 100%")
    return [(str(bu), _share_by_pct(amt, float(pct))) for bu, pct in default_ratios.items() if pct]


def allocate_public_details_for_month(
    details: dict[str, dict],
    fine_rules: dict[str, dict[str, dict]] | None,
    default_ratios: dict[str, float] | None,
    bu_names: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """2.4.0 两轴：单月公共明细 → 各 BU 按大类摊入额（单位与 details.amount 一致，库内分）。

    details: {明细费用类型: {amount: 分, cat: 报表大类}}
    fine_rules: {明细: {BU: {mode: '比例'|'金额', value: 比例% 或 金额**元**}}}
    default_ratios: {BU: 比例%} 默认层；无精配的明细走此层。
    超额（比例合计>100 或 金额合计>本项）→ ValueError。
    返回 {BU: {大类: 分 int}}。
    """
    want = set(bu_names or []) if bu_names is not None else None
    fine_rules = fine_rules or {}
    default_ratios = default_ratios or {}
    out: dict[str, dict[str, int]] = {}

    for fine, info in (details or {}).items():
        if not isinstance(info, dict):
            continue
        amount = _fen_amount(info.get("amount"))
        cat = str(info.get("cat") or "").strip()
        if not cat or amount == 0:
            continue
        for bu, share in _shares_for_detail_item(
            str(fine), amount, fine_rules.get(str(fine)) or {}, default_ratios
        ):
            if want is not None and bu not in want:
                continue
            share_i = _fen_amount(share)
            if share_i == 0:
                continue
            bucket = out.setdefault(bu, {})
            bucket[cat] = _fen_amount(bucket.get(cat)) + share_i

    cleaned: dict[str, dict[str, int]] = {}
    for bu, cats in out.items():
        c2 = {c: int(v) for c, v in cats.items() if int(v) != 0}
        if c2:
            cleaned[bu] = c2
    return cleaned


def allocate_public_details_lines_for_month(
    details: dict[str, dict],
    fine_rules: dict[str, dict[str, dict]] | None,
    default_ratios: dict[str, float] | None,
    bu_name: str,
) -> dict[str, list[tuple[str, float]]]:
    """单月单 BU：分摊自公共的明细行 → {大类: [(明细名, 分), ...]}（供 alloc_added 下钻）。"""
    fine_rules = fine_rules or {}
    default_ratios = default_ratios or {}
    lines: dict[str, list[tuple[str, int]]] = {}
    for fine, info in (details or {}).items():
        if not isinstance(info, dict):
            continue
        amount = _fen_amount(info.get("amount"))
        cat = str(info.get("cat") or "").strip()
        if not cat or amount == 0:
            continue
        for bu, share in _shares_for_detail_item(
            str(fine), amount, fine_rules.get(str(fine)) or {}, default_ratios
        ):
            if bu != bu_name:
                continue
            share_i = _fen_amount(share)
            if share_i != 0:
                lines.setdefault(cat, []).append((str(fine), share_i))
    return {c: sorted(lst, key=lambda x: -abs(x[1])) for c, lst in lines.items() if lst}


def _merge_alloc_into_period_with_details(
    p: dict,
    add_by_cat: dict,
    detail_lines: dict[str, list[tuple[str, int]]] | None = None,
    cfg=None,
) -> None:
    """叠加分摊额，并写入明细级 alloc_added_details。"""
    _merge_alloc_into_period(p, add_by_cat, cfg=cfg)
    if detail_lines:
        p["alloc_added_details"] = {
            cat: [{"name": n, "amt": int(a)} for n, a in lst]
            for cat, lst in detail_lines.items()
            if lst
        }


def _alloc_detail_for_range(
    public_month_details: dict,
    fine_rules_by_month: dict,
    ratios_by_month: dict,
    bu_name: str,
    start,
    end,
    cap,
) -> tuple[dict[str, int], dict[str, list[tuple[str, int]]]]:
    """周期内逐月明细分摊，汇总到大类 + 明细行。2.6.13：int 分。"""
    add = {cat: 0 for cat in _LEDGER_TO_EXPENSE}
    det: dict[str, dict[str, int]] = {cat: {} for cat in _LEDGER_TO_EXPENSE}
    for y, m in periods.months_in(start, end, cap):
        mk = f"{y:04d}-{m:02d}"
        details = public_month_details.get((y, m)) or {}
        if not details:
            continue
        month_map = allocate_public_details_for_month(
            details,
            fine_rules_by_month.get(mk),
            ratios_by_month.get(mk),
            bu_names=[bu_name],
        )
        bu_cats = month_map.get(bu_name) or {}
        for cat, v in bu_cats.items():
            add[cat] = _fen_amount(add.get(cat)) + _fen_amount(v)
        for cat, lst in allocate_public_details_lines_for_month(
            details,
            fine_rules_by_month.get(mk),
            ratios_by_month.get(mk),
            bu_name,
        ).items():
            bucket = det.setdefault(cat, {})
            for n, a in lst:
                bucket[n] = _fen_amount(bucket.get(n)) + _fen_amount(a)
    lines = {
        cat: sorted(((n, int(a)) for n, a in d.items() if int(a) != 0), key=lambda x: -abs(x[1]))
        for cat, d in det.items()
        if d
    }
    return {cat: int(v) for cat, v in add.items()}, lines


def apply_public_expense_allocation_monthly(
    summary: dict,
    public_month_led: dict,
    ratios_by_month: dict,
    bu_name: str,
    today,
    cfg=None,
    *,
    public_month_details: dict | None = None,
    fine_rules_by_month: dict | None = None,
) -> None:
    """就地：按月把公共池费用叠加进单 BU summary 各周期（迭代20 + 2.4.0 明细两轴）。

    兼容：未传 public_month_details 时走旧 5 大类×默认比例路径。
    传入明细池时：精配优先 → 默认层 → 归回 5 大类；alloc_added 带明细行。
    """
    P = summary.get("periods") or {}
    has_ratio = any((r or {}).get(bu_name) for r in (ratios_by_month or {}).values())
    has_fine = bool(fine_rules_by_month) and any(
        any(str(bu_name) in (rules or {}) for rules in (month_rules or {}).values())
        for month_rules in (fine_rules_by_month or {}).values()
    )
    use_detail = bool(public_month_details)
    for _key, p in P.items():
        rng = p.get("range")
        if not rng:
            continue
        start = datetime.date.fromisoformat(rng[0])
        end = datetime.date.fromisoformat(rng[1])
        if use_detail:
            add, lines = _alloc_detail_for_range(
                public_month_details or {},
                fine_rules_by_month or {},
                ratios_by_month or {},
                bu_name,
                start,
                end,
                today,
            )
            if not any(add.values()):
                continue
            _merge_alloc_into_period_with_details(p, add, lines, cfg=cfg)
        else:
            add = _alloc_cats_for_range(
                public_month_led, ratios_by_month, bu_name, start, end, today
            )
            if not any(add.values()):
                continue
            _merge_alloc_into_period(p, add, cfg=cfg)
    enabled = has_ratio or has_fine
    # 仅有默认层比例时仍标「按月比例」（兼容既有 UI/测试）；有精配才标「按明细分摊」
    if not enabled:
        mode, ratio_disp = "monthly", ""
    elif has_fine:
        mode, ratio_disp = "detail", "按明细分摊"
    else:
        mode, ratio_disp = ("detail" if use_detail else "monthly"), "按月比例"
    summary.setdefault("meta", {})["public_allocation"] = {
        "enabled": enabled,
        "mode": mode,
        "ratio_pct": None,
        "ratio_disp": ratio_disp,
    }


def alloc_amounts_by_period(
    public_month_led: dict,
    ratios_by_month: dict,
    bu_names: list[str],
    today,
    *,
    public_month_details: dict | None = None,
    fine_rules_by_month: dict | None = None,
) -> dict[str, dict[str, int]]:
    """每周期每 BU 的分摊总额（**int 分**；供全公司「构成·按业务BU」视图跟着挪·迭代20/2.4.0/3.3.1）。
    只认在 bu_names 里的 BU。返回 {周期key: {BU: 分}}。

    3.3.1：池合计与份额全程 int 分 + mul_rates_fen/_share_by_pct；禁止把 float 金额四舍五入当真相。
    """
    want = set(bu_names or [])
    ranges = periods.all_period_ranges(today)
    out: dict[str, dict[str, int]] = {}
    use_detail = bool(public_month_details)
    for key, (_lab, start, end, _grp) in ranges.items():
        per: dict[str, int] = {}
        for y, m in periods.months_in(start, end, today):
            mk = f"{y:04d}-{m:02d}"
            if use_detail:
                month_map = allocate_public_details_for_month(
                    public_month_details.get((y, m)) or {},
                    (fine_rules_by_month or {}).get(mk),
                    (ratios_by_month or {}).get(mk),
                    bu_names=list(want),
                )
                for b, cats in month_map.items():
                    if b not in want:
                        continue
                    s = sum(_fen_amount(v) for v in cats.values())
                    if s:
                        per[b] = per.get(b, 0) + int(s)
            else:
                r = ratios_by_month.get(mk) or {}
                led = public_month_led.get((y, m)) or {}
                month_pub = sum(_fen_amount(led.get(c)) for c in _LEDGER_TO_EXPENSE)
                for b, pct in r.items():
                    if b in want and pct:
                        per[b] = per.get(b, 0) + _share_by_pct(int(month_pub), float(pct))
        cleaned = {b: int(v) for b, v in per.items() if int(v)}
        if cleaned:
            out[key] = cleaned
    return out


def apply_alloc_to_pc_view(groups, alloc_by_bu: dict[str, int]):
    """把分摊结果套进「构成·按业务BU（利润中心）」单周期分组列表（迭代20·防两处真相）。
    groups=[(组名,合计分,[(细类,金额分)…])]；公共组减去已摊总额并挂负数行，各 BU 组加分摊额并挂正数行。
    **各组合计之和不变**（分摊只挪归属）。groups 为 None（台账无此列）原样返回。

    3.3.1：合计/明细/分摊额全程 int 分；禁止把 float 金额四舍五入当真相。
    """
    if not groups or not alloc_by_bu:
        return groups
    alloc_i = {str(b): _fen_amount(amt) for b, amt in alloc_by_bu.items()}
    total_alloc = sum(v for v in alloc_i.values() if v > 0)
    if total_alloc <= 0:
        return groups
    gmap: dict[str, tuple[int, list[tuple[str, int]]]] = {}
    for g, t, f in groups:
        fines = [(str(n), _fen_amount(a)) for n, a in (f or [])]
        gmap[str(g)] = (_fen_amount(t), fines)
    if "公共" not in gmap:  # 分摊额来自公共池；池不存在说明上游没数，不动
        return groups
    for b, amt in alloc_i.items():
        if amt <= 0:
            continue
        t, f = gmap.get(b, (0, []))
        gmap[b] = (int(t) + int(amt), list(f) + [(ALLOC_IN_LABEL, int(amt))])
    t, f = gmap["公共"]
    gmap["公共"] = (int(t) - int(total_alloc), list(f) + [(ALLOC_OUT_LABEL, -int(total_alloc))])
    return [
        (g, t, sorted(f, key=lambda x: -x[1]))
        for g, (t, f) in sorted(gmap.items(), key=lambda kv: -kv[1][0])
    ]




