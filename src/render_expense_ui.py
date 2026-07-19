#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 render.py 纯搬家（任务书54.13）；禁止改算法。"""
from __future__ import annotations

import json
import charts
import tpl
from render_widgets import (
    _esc,
)
from render_common import GROUP_COLORS
from render_pl_ui import _drow, _detail_block


def render_trend(trend, hl, *, period_months_map=None, year_key=None):
    # 看端卡头只留「按月」；柱顶/线上说明见图例，不堆运营备注。
    # 迭代：卡根挂 data-rm-map（复用 _period_months_map）供前端只切高亮，柱图全年视角不变。

    yk = year_key or ""
    rm_map = period_months_map or {}
    map_json = json.dumps(rm_map, ensure_ascii=False, separators=(",", ":"))
    return tpl.fill(
        "render/trend_card.html", yk=_esc(yk), map_json=_esc(map_json), chart=charts.combo_bar_line_chart(trend, hl)
    )

def render_donut(p):
    e = p["expense"]
    man = p["manual"]
    led = p["ledger_expenses"]
    groups = ["营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"]
    segs = [(g, e[g], GROUP_COLORS[g]) for g in groups if e[g] > 0]
    # 悬浮明细：每类拆成 手填人力 / 台账 两块（陆总口径）
    detail = {
        "营销费用": [("营销人力成本(手填)", man["营销人力成本"]), ("市场费用(台账)", led["市场费用"])],
        "管理费用": [("管理人力成本(手填)", man["管理人力成本"]), ("管理费用(台账)", led["管理费用"])],
        "固定运营费用": [("固定运营费用(台账)", led["固定运营费用"])],
        "研发费用": [("研发人力成本(手填)", man["研发人力成本"]), ("技术服务费(台账)", led["技术服务费"])],
        "财务费用": [("财务费用(台账)", led["财务费用"]), ("财务费用补充(手填)", man["财务费用补充"])],
    }
    legend = "".join(
        tpl.fill("render/donut_legend_item.html", color=GROUP_COLORS[g], name=g, amt=charts.fmt_wan(e[g]))
        for g in groups
    )
    return tpl.fill(
        "render/donut_wrap.html",
        donut=charts.donut(segs, "期间费用", charts.fmt_wan(e["total"]) + "万", detail=detail),
        legend=legend,
    )

_HBAR_SINK = frozenset({"未分类", "未标注明细类型"})

def _hbar_rows(rows, prefix):
    """横向条形列表（台账白名单口径分组）+ 每组的抽屉明细块。rows=[(组名,合计,[(细项,金额),...]),...]。
    宽度按最大组归一（服务端算好，前端零运算）；未分类/未标注明细类型灰色沉底。"""
    if rows is None:
        return tpl.load("render/ev_empty_old.html")
    if not rows:
        return tpl.load("render/ev_empty_none.html")
    ordered = [r for r in rows if r[0] not in _HBAR_SINK] + [r for r in rows if r[0] in _HBAR_SINK]
    mx = max(v for _, v, _ in rows) or 1
    out, details = [], []
    for name, val, fine in ordered:
        key = f"{prefix}:{name}"
        w = max(2.0, val / mx * 100)
        cls = " unfilled" if name in _HBAR_SINK else ""
        out.append(
            tpl.fill("render/hbar_row.html", cls=cls, key=_esc(key), name=_esc(name), w=w, amt=charts.fmt_wan(val))
        )
        inner = "".join(_drow(n, -a, "", "", sub=True) for n, a in fine[:12])
        rest = fine[12:]
        if rest:
            inner += _drow(f"其他{len(rest)}项", -sum(a for _, a in rest), "", "", sub=True)
        details.append(_detail_block(key, f"{name} · 费用构成（{charts.fmt_wan(val)}万）", inner))
    return tpl.fill("render/hbar_list.html", rows="".join(out), details="".join(details))

def _ledger_subtotal(rows):
    return charts.fmt_wan(sum(v for _, v, _ in rows)) + "万" if rows else "0万"

def render_expense_views(p, fine_rows, pc_rows, dept_rows=None):
    """期间费用构成卡：按大类｜按类别｜按业务BU（利润中心）｜按部门（预算归属部门）。
    四态台账白名单含税口径同一；卡头合计含手填人力，横条小计仅为台账部分。
    dept_rows=summary['expense_by_department'][周期]（与 pc 同形），金额全后端算好。"""
    e = p["expense"]
    tabs = tpl.load("render/expense_tabs.html")
    # 看端：横条小计可扫读；长口径说明留给管理端数据/异常页，此处不堆字
    fine_note = f"台账小计 {_ledger_subtotal(fine_rows)}"
    pc_note = f"台账小计 {_ledger_subtotal(pc_rows)}"
    dept_note = f"台账小计 {_ledger_subtotal(dept_rows)}"
    return tpl.fill(
        "render/expense_card.html",
        total=charts.fmt_wan(e["total"]),
        tabs=tabs,
        donut=render_donut(p),
        fine_rows=_hbar_rows(fine_rows, "fine"),
        fine_note=fine_note,
        pc_rows=_hbar_rows(pc_rows, "pc"),
        pc_note=pc_note,
        dept_rows=_hbar_rows(dept_rows, "dept"),
        dept_note=dept_note,
    )

def _fine_to_rows(fine_k):
    """把 {大类:[(细类,金额)…]} 摊平成「按类别」横条行 [(细类,合计,[(大类,金额)…])…]（迭代22·D2）。
    同名细类跨大类合并；抽屉里按大类拆开看。金额全后端 round，前端零运算。"""
    if not fine_k:
        return []
    agg: dict[str, float] = {}
    src: dict[str, list] = {}
    for cat, pairs in fine_k.items():
        for name, amt in pairs or []:
            agg[name] = agg.get(name, 0.0) + float(amt)
            src.setdefault(name, []).append((cat, float(amt)))
    rows = [(n, round(v, 2), sorted(src[n], key=lambda x: -x[1])) for n, v in agg.items()]
    rows.sort(key=lambda r: -r[1])
    return rows

def render_bu_expense_views(p, fine_k):
    """BU 页期间费用构成卡：按大类（环形）｜按类别（横条）两态。
    与整体页「按类别」同口径（预算明细费用类型）；不出「按部门」。"""
    e = p.get("expense") or {}
    rows = _fine_to_rows(fine_k)
    tabs = tpl.load("render/bu_expense_tabs.html")
    return tpl.fill(
        "render/bu_expense_card.html",
        total=charts.fmt_wan(e.get("total") or 0),
        tabs=tabs,
        donut=render_donut(p),
        fine_rows=_hbar_rows(rows, "fine"),
        subtotal=_ledger_subtotal(rows),
    )

def render_dept_budget(dept_budget):
    """部门费用预算执行卡。迭代19 陆总拍板：界面下线（半吊子汇总无意义）；函数保留给旧测试/兼容，恒返回空。"""
    return ""

def expense_monthly_from_period_ledgers(summary: dict) -> dict:
    """从各月周期 ledger_expenses 拼 1~12 矩阵（BU 分摊后与利润表费用口径一致）。"""
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    cats: list[str] = []
    by_m: dict[int, dict[str, float]] = {m: {} for m in range(1, 13)}
    for k in month_keys:
        try:
            rest = k.split("年", 1)[1]
            m = int(rest.replace("月", "").split("-")[0]) if rest.endswith("月") else 0
        except (IndexError, ValueError):
            m = 0
        if m < 1 or m > 12:
            continue
        led = (P.get(k) or {}).get("ledger_expenses") or {}
        for c, v in led.items():
            if not c:
                continue
            if c not in cats:
                cats.append(c)
            by_m[m][c] = round(float(v or 0), 2)
    months = []
    for m in range(1, 13):
        bc = {c: float(by_m[m].get(c) or 0) for c in cats}
        months.append({"m": m, "total": round(sum(bc.values()), 2), "by_cat": bc})
    return {"categories": cats, "months": months, "salary_merged": False, "note": ""}

def apply_expense_salary_hide(raw: dict | None, hide_salary: bool) -> dict | None:
    """整体页 B8：默认隐工资 → 图中「工资」并入「其他」并注明（仅显示层副本，不改 summary）。"""
    if not raw:
        return raw
    if not hide_salary or "工资" not in (raw.get("categories") or []):
        return raw
    import copy

    out = copy.deepcopy(raw)
    cats = [c for c in out.get("categories") or [] if c != "工资"]
    if "其他" not in cats:
        cats.append("其他")
    for m in out.get("months") or []:
        bc = dict(m.get("by_cat") or {})
        sal = float(bc.pop("工资", 0) or 0)
        if sal:
            bc["其他"] = round(float(bc.get("其他") or 0) + sal, 2)
        m["by_cat"] = bc
        m["total"] = round(sum(float(bc.get(c) or 0) for c in cats), 2)
    out["categories"] = cats
    out["salary_merged"] = True
    out["note"] = "工资大类已并入「其他」（全端隐藏，不单列）"
    return out

def pack_expense_trend_months(raw: dict) -> tuple[list[str], list[dict], str]:
    """把 compute_expense_monthly_by_cat 结果压成 SVG 入参（显示串/高度比例后端算好）。"""
    cats = list(raw.get("categories") or [])
    months_out = []
    for m in raw.get("months") or []:
        total = float(m.get("total") or 0)
        segs = []
        by_cat = m.get("by_cat") or {}
        for c in cats:
            amt = float(by_cat.get(c) or 0)
            if amt <= 0:
                continue
            pct = (amt / total * 100.0) if total else 0.0
            segs.append(
                {
                    "cat": c,
                    "amount": amt,
                    "amount_disp": charts.fmt_wan(amt),
                    "pct_disp": f"{pct:.1f}%",
                }
            )
        months_out.append(
            {
                "m": m.get("m"),
                "total": total,
                "total_disp": charts.fmt_wan(total),
                "segs": segs,
            }
        )
    note = raw.get("note") or ""
    return cats, months_out, note

def render_expense_trend(raw: dict | None, *, title: str = "费用月度趋势 · 按报表大类") -> str:
    """任务书39·E / 46·0：费用堆叠面积图卡 HTML。raw=compute_expense_monthly_by_cat 结果。"""
    if not raw:
        return ""
    cats, months, note = pack_expense_trend_months(raw)
    chart = charts.expense_stack_chart(months, cats, note=note)
    return tpl.fill("render/exp_trend_card.html", title=_esc(title), chart=chart)

