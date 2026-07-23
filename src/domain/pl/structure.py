#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理利润表单一结构建造（任务书51·B2）。

render_*（legacy HTML）与 packers（VM）均消费 pl_structure；业务口径只在此维护一份。
"""

from __future__ import annotations

from typing import Any


def _wan(v) -> str:
    import charts

    return charts.fmt_wan(float(v or 0))


def amt_disp(impact) -> str:
    """主表利润影响显示串：带符号万元。"""
    v = float(impact or 0)
    sign = "−" if v < 0 else ""
    return sign + _wan(abs(v)) + "万"


def abs_amt_disp(v) -> str:
    """抽屉明细金额：绝对值 + 万（行名已含加/减语义）。"""
    return _wan(abs(float(v or 0))) + "万"


def _fine_pairs(fine_pairs, limit=8) -> list[dict[str, Any]]:
    pairs = sorted(fine_pairs or [], key=lambda x: -x[1])
    lines: list[dict[str, Any]] = []
    for n, a in pairs[:limit]:
        lines.append(
            {
                "name": str(n),
                "impact": abs(float(a or 0)),
                "amt_disp": abs_amt_disp(a),
                "kind": "",
                "sub": True,
            }
        )
    rest = pairs[limit:]
    if rest:
        s = sum(float(a or 0) for _, a in rest)
        # 2.4.0：其他N项可展开 — children 下发全部剩余明细（前端只展示，不运算）
        children = [
            {
                "name": str(n),
                "impact": abs(float(a or 0)),
                "amt_disp": abs_amt_disp(a),
                "kind": "",
                "sub": True,
            }
            for n, a in rest
        ]
        lines.append(
            {
                "name": f"其他{len(rest)}项",
                "impact": abs(s),
                "amt_disp": abs_amt_disp(s),
                "kind": "",
                "sub": True,
                "expandable": True,
                "children": children,
            }
        )
    return lines


def _dline(name, impact, kind="", *, sub=False) -> dict[str, Any]:
    a = abs(float(impact or 0))
    return {
        "name": name,
        "impact": a,
        "amt_disp": abs_amt_disp(a),
        "kind": kind,
        "sub": sub,
    }


def _dline_deduction(name, amount, kind="", *, sub=False) -> dict[str, Any]:
    """成本抽屉减项：impact 为负，amt_disp 带 U+2212（与主表 amt_disp 同规则）。"""
    a = abs(float(amount or 0))
    impact = -a
    return {
        "name": name,
        "impact": impact,
        "amt_disp": amt_disp(impact),
        "kind": kind,
        "sub": sub,
    }


def _row(
    name,
    impact,
    *,
    kind="",
    formula="",
    open_key=None,
    total=False,
    grand=False,
    is_pct=False,
    pct=None,
    pending=False,
) -> dict[str, Any]:
    if is_pct:
        txt = f"{pct:.1f}%" if pct is not None else "—"
        return {
            "name": name,
            "impact": None,
            "pct": pct,
            "amt_disp": txt,
            "kind": kind,
            "formula": formula,
            "open_key": None,
            "total": False,
            "grand": False,
            "is_pct": True,
            "pending": False,
        }
    return {
        "name": name,
        "impact": float(impact or 0),
        "pct": None,
        "amt_disp": amt_disp(impact),
        "kind": kind,
        "formula": formula,
        "open_key": open_key,
        "total": total,
        "grand": grand,
        "is_pct": False,
        "pending": bool(pending),
    }


_PROD_MANUAL = [
    "PM人力成本",
    "VM人力成本",
    "实际内部译员成本",
    "税费损失",
    "技术流量成本",
    "其他（生产成本）",
]

_EXP_GROUPS = (
    ("sales", "营销费用", "营销人力成本", "市场费用"),
    ("admin", "管理费用", "管理人力成本", "管理费用"),
    ("fixed", "固定运营费用", None, "固定运营费用"),
    ("rd", "研发费用", "研发人力成本", "技术服务费"),
    ("fin", "财务费用", None, "财务费用"),
)


def _pl_cost_details(p: dict, man: dict) -> dict[str, Any]:
    # 减项两项带 U+2212 负号（陆总 2026-07-23：只改抽屉这两项显示，计算不动）
    cost_lines = [
        _dline("系统直接成本", p.get("system_direct_cost"), "system"),
        _dline_deduction("系统内部译员", p.get("inhouse_cost"), "system"),
        _dline_deduction("直接成本增值税", man.get("直接成本增值税", 0.0), "manual"),
    ]
    for n in _PROD_MANUAL:
        cost_lines.append(_dline(n, man.get(n, 0.0), "manual"))
    return {"title": "交付成本（生产成本）构成", "lines": cost_lines}


def _pl_bu_expense_block(p, e, man, led, fine, alloc_meta) -> tuple[str, bool, bool, list, dict]:
    """BU 费用行 + 抽屉；返回 (tag_note, has_fee, has_manual, rows, details)。"""
    alloc = alloc_meta or {}
    on = bool(alloc.get("enabled"))
    rdisp = alloc.get("ratio_disp") or ""
    alloc_added = p.get("alloc_added") or {}
    exp_total = float(e.get("total") or 0)
    has_fee = exp_total > 0.005 or any(float(led.get(c) or 0) > 0.005 for c in led)
    man_keys = (
        "营销人力成本",
        "管理人力成本",
        "研发人力成本",
        "财务费用补充",
        "PM人力成本",
        "VM人力成本",
        "实际内部译员成本",
        "税费损失",
        "技术流量成本",
        "其他（生产成本）",
        "其他损益",
    )
    has_manual = any(abs(float(man.get(k) or 0)) > 0.005 for k in man_keys)
    if on and rdisp:
        tag_note = f"含公共分摊 {rdisp}"
    elif has_fee:
        tag_note = "本BU直记"
    else:
        tag_note = ""
    rows: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for cat_key, nm, man_key, led_cat in _EXP_GROUPS:
        v = float(e.get(nm) or 0)
        pending = not (has_fee or abs(v) > 0.005)
        rows.append(_row(nm, -v, open_key=cat_key, pending=pending))
        alloc_amt = float(alloc_added.get(led_cat) or 0.0)
        direct_amt = round(float(led.get(led_cat) or 0.0) - alloc_amt, 2)
        lines: list[dict[str, Any]] = []
        if man_key:
            lines.append(_dline(man_key, man.get(man_key, 0), "manual"))
        lines.append(_dline(led_cat, direct_amt, "ledger"))
        lines.extend(_fine_pairs(fine.get(led_cat)))
        if nm == "财务费用":
            lines.append(_dline("财务费用补充", man.get("财务费用补充", 0), "manual"))
        lines.extend(_alloc_public_lines(p, led_cat, alloc_amt))
        details[cat_key] = {"title": f"{nm}构成", "lines": lines}
    return tag_note, has_fee, has_manual, rows, details


def _alloc_public_lines(p: dict, led_cat: str, alloc_amt: float) -> list[dict[str, Any]]:
    """2.4.0：分摊自公共列到明细项级；无明细时回退合计行。"""
    out: list[dict[str, Any]] = []
    for item in (p.get("alloc_added_details") or {}).get(led_cat) or []:
        if not isinstance(item, dict):
            continue
        nm_d = str(item.get("name") or "").strip()
        amt_d = float(item.get("amt") or 0)
        if nm_d and abs(amt_d) >= 0.005:
            out.append(_dline(f"分摊自公共·{nm_d}", amt_d, "ledger"))
    if out:
        return out
    if alloc_amt > 0.005:
        return [_dline("分摊自公共", alloc_amt, "ledger")]
    return out


def _pl_main_expense_block(e, man, led, fine) -> tuple[list, dict]:
    """整体页五类费用固定行 + 固定抽屉。"""
    rows: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for cat_key, nm, _mk, _lc in _EXP_GROUPS:
        rows.append(_row(nm, -float(e.get(nm) or 0), open_key=cat_key))

    def led_block(title_led, amount, fine_key, extra_before=None, extra_after=None):
        lines = list(extra_before or [])
        lines.append(_dline(title_led, amount, "ledger"))
        lines.extend(_fine_pairs(fine.get(fine_key)))
        lines.extend(extra_after or [])
        return lines

    details["sales"] = {
        "title": "营销费用构成",
        "lines": led_block(
            "市场费用",
            led.get("市场费用", 0),
            "市场费用",
            extra_before=[_dline("营销人力成本", man.get("营销人力成本", 0), "manual")],
        ),
    }
    details["admin"] = {
        "title": "管理费用构成",
        "lines": led_block(
            "管理费用",
            led.get("管理费用", 0),
            "管理费用",
            extra_before=[_dline("管理人力成本", man.get("管理人力成本", 0), "manual")],
        ),
    }
    details["fixed"] = {
        "title": "固定运营费用构成",
        "lines": led_block("固定运营费用明细", led.get("固定运营费用", 0), "固定运营费用"),
    }
    details["rd"] = {
        "title": "研发费用构成",
        "lines": led_block(
            "技术服务费",
            led.get("技术服务费", 0),
            "技术服务费",
            extra_before=[_dline("研发人力成本", man.get("研发人力成本", 0), "manual")],
        ),
    }
    details["fin"] = {
        "title": "财务费用构成",
        "lines": led_block(
            "财务费用",
            led.get("财务费用", 0),
            "财务费用",
            extra_after=[_dline("财务费用补充", man.get("财务费用补充", 0), "manual")],
        ),
    }
    return rows, details


def pl_structure(
    p: dict,
    fine: dict | None = None,
    *,
    is_bu: bool = False,
    unclassified_amt: float | None = None,
    alloc_meta: dict | None = None,
) -> dict[str, Any]:
    """单周期利润表结构 → {rows, details, tag_note, meta}。

    rows/details 含 impact（数值）与 *_disp（显示串）；VM 取 disp 字段，HTML 用 impact 填模板。
    is_bu=True 时：
      - 费用抽屉拆直记/分摊；
      - pending 标记供 HTML「待补」行（VM 仍下发金额 disp，与重构前 pack 一致）。
    """
    fine = fine or {}
    e = p.get("expense") or {}
    man = p.get("manual") or {}
    led = p.get("ledger_expenses") or {}
    rows: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}

    rows.append(_row("交付收入（不含税）", p.get("revenue_net"), kind="system", formula="交付金额÷1.06"))
    rows.append(_row("交付成本（生产成本）", -float(p.get("production_cost") or 0), open_key="cost"))
    rows.append(_row("毛利", p.get("gross_profit"), total=True))
    rows.append(
        _row(
            "毛利率",
            0,
            is_pct=True,
            pct=p.get("gross_margin_pct"),
            formula="毛利÷交付收入",
        )
    )
    details["cost"] = _pl_cost_details(p, man)

    tag_note = ""
    has_fee = False
    has_manual = False
    if is_bu:
        tag_note, has_fee, has_manual, exp_rows, exp_det = _pl_bu_expense_block(p, e, man, led, fine, alloc_meta)
        rows.extend(exp_rows)
        details.update(exp_det)
    else:
        exp_rows, exp_det = _pl_main_expense_block(e, man, led, fine)
        rows.extend(exp_rows)
        details.update(exp_det)

    rows.append(_row("附加税费", -float(p.get("surtax") or 0), kind="system", formula="净收入×6%×12%"))
    other_pl = float(p.get("other_pl") or 0)
    if is_bu:
        other_pending = not (abs(other_pl) > 0.005 or has_manual)
        rows.append(_row("其他损益", other_pl, kind="manual", pending=other_pending))
    else:
        rows.append(_row("其他损益", other_pl, kind="manual"))
        if unclassified_amt is not None and float(unclassified_amt) > 0:
            rows.append(_row("未计入费用（台账未填大类）", -float(unclassified_amt), kind="ledger"))

    rows.append(
        _row(
            "税前利润",
            p.get("pretax_profit"),
            grand=True,
            formula="毛利−期间费用−附加税±其他",
        )
    )
    rows.append(
        _row(
            "税前利润率",
            0,
            is_pct=True,
            pct=p.get("pretax_margin_pct"),
            formula="税前利润÷交付收入",
        )
    )
    return {
        "rows": rows,
        "details": details,
        "tag_note": tag_note,
        "meta": {"is_bu": is_bu, "has_fee": has_fee, "has_manual": has_manual},
    }


def structure_for_vm(struct: dict[str, Any]) -> dict[str, Any]:
    """裁成 VM 公开字段（与任务书50 pack_pl 输出对齐：rows/details 仅 name/amt_disp/…）。"""
    rows_out = []
    for r in struct.get("rows") or []:
        rows_out.append(
            {
                "name": r["name"],
                "amt_disp": r["amt_disp"],
                "kind": r.get("kind") or "",
                "formula": r.get("formula") or "",
                "open_key": r.get("open_key"),
                "total": bool(r.get("total")),
                "grand": bool(r.get("grand")),
                "is_pct": bool(r.get("is_pct")),
            }
        )
    details_out: dict[str, Any] = {}
    for k, block in (struct.get("details") or {}).items():
        details_out[k] = {
            "title": block.get("title") or "",
            "lines": [
                {
                    "name": ln["name"],
                    "amt_disp": ln["amt_disp"],
                    "kind": ln.get("kind") or "",
                    "sub": bool(ln.get("sub")),
                }
                for ln in (block.get("lines") or [])
            ],
        }
    return {"rows": rows_out, "details": details_out}


# ---------- KPI 目标条 / 峰值（packers 与 render_widgets 共用）----------


def kpi_peak_for(summary: dict, key: str) -> dict[str, str] | None:
    """跨月峰值 {label, value_disp}；全 0 或无月则 None。"""
    import charts
    from render_widgets import _kpi_val

    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    year = meta.get("year")
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    if not month_keys:
        return None
    best_v, best_mk = None, None
    for mk in month_keys:
        if mk not in P:
            continue
        v = float(_kpi_val(P[mk], key) or 0.0)
        if best_v is None or v > best_v:
            best_v, best_mk = v, mk
    if best_v is None:
        return None
    if best_v == 0.0 and all(float(_kpi_val(P.get(mk) or {}, key) or 0.0) == 0.0 for mk in month_keys):
        return None
    lab = (
        best_mk.replace(f"{year}年", "")
        if isinstance(best_mk, str) and best_mk.startswith(f"{year}年")
        else str(best_mk)
    )
    wan = charts.fmt_wan(best_v)
    # value_wan：legacy HTML 模板自拼「万」；value_disp：VM 整串
    return {"label": lab, "value_wan": wan, "value_disp": wan + "万"}


def kpi_target_bar(tkey, pkey, p, budget) -> dict[str, Any] | None:
    """结构化目标条（VM + legacy HTML 共用）；无 tkey → None；无 budget 项 → empty 态。

    字段约定：
    - VM 用 *_disp 显示串；
    - HTML 用 tgt（毛利数值）/ tgt_wan·done_wan（金额模板自拼「万」）。
    """
    import charts
    from render_widgets import _kpi_val

    if not budget or not tkey:
        return None
    use_h1 = ("1-6" in pkey) or pkey.endswith("1-6月") or ("1~6" in pkey)
    item, label = None, "年目标"
    if use_h1 and budget.get(f"{tkey}_h1"):
        item = budget[f"{tkey}_h1"]
        label = "H1目标"
    if item is None:
        item = budget.get(tkey)
        label = "年目标"
    if not item:
        return {"empty": True, "label": label}
    tgt, done, pct = item.get("target"), item.get("done"), item.get("pct")
    if tkey in ("margin", "pretax_margin"):
        if use_h1 and item.get("done") is not None:
            cur = item["done"]
        else:
            cur = p.get("gross_margin_pct" if tkey == "margin" else "pretax_margin_pct")
        cur_s = f"{cur:.1f}%" if cur is not None else "—"
        if pct is not None and pct > 999:
            pct_s = ">999% · 目标待校准"
        else:
            pct_s = f"{pct:.0f}%" if pct is not None else "—"
        w = min(max(pct or 0, 0), 100)
        cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
        return {
            "empty": False,
            "kind": "margin",
            "label": label,
            "tgt": tgt,
            "tgt_disp": str(tgt),
            "cur_disp": cur_s,
            "pct_disp": pct_s,
            "bar_w": w,
            "cls": cls,
        }
    if done is None:
        done = _kpi_val(p, {"order": "orders", "receipt": "receipts"}.get(tkey, "orders"))
        pct = (done / tgt * 100.0) if tgt else None
    if pct is not None and pct > 999:
        pct_s = ">999% · 目标待校准"
    else:
        pct_s = f"{pct:.1f}%" if pct is not None else "—"
    w = min(max(pct or 0, 0), 100)
    cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
    tgt_wan = charts.fmt_wan(tgt)
    done_wan = charts.fmt_wan(done)
    return {
        "empty": False,
        "kind": "amount",
        "label": label,
        "tgt_wan": tgt_wan,
        "done_wan": done_wan,
        "tgt_disp": tgt_wan + "万",
        "done_disp": done_wan + "万",
        "pct_disp": pct_s,
        "bar_w": w,
        "cls": cls,
    }
