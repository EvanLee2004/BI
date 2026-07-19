#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 render.py 纯搬家（任务书54.13）；禁止改算法。"""
from __future__ import annotations

import tpl
from render_shell import (
    DRAWER_HTML,
    PARTICLES_HTML,
    PW_MODAL_HTML,
    RK_MODAL_HTML,
    DAILY_HTML,
)
from render_widgets import (
    _title_version_html,
    render_basic,
    render_period_bar,
    _pv,
    _esc,
)


from render_expense_ui import (
    render_trend,
    render_expense_views,
    render_bu_expense_views,
    render_expense_trend,
    apply_expense_salary_hide,
    expense_monthly_from_period_ledgers,
    _fine_to_rows,
)
from render_pl_ui import render_pl_table, render_bu_pl_table
from render_receipts_rank import (
    render_receipts,
    render_rankings,
    render_profit_rankings,
    monthly_data_script,
    _period_months_map,
)

def build_dashboard_fragments(summary, cfg, logo_b64) -> dict:
    """B：整页渲染就绪碎片（全部显示串/HTML 段后端算好）。JS 只拼接，零金额运算。"""
    meta = summary["meta"]
    P = summary["periods"]
    FT = summary["expense_fine_type"]
    yk = meta["year_key"]
    all_keys = [yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"] + meta["tab_groups"].get("区间", [])
    logo = tpl.fill("render/logo.html", src=logo_b64) if logo_b64 else ""
    unc = meta["unclassified"]["expense"]
    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    kpi_views = "".join(
        _pv(
            k,
            yk,
            render_basic(k, P, meta["year"], month_keys, budget, bu_orders=BUO.get(k), show_delivered_unpaid=show_ar),
        )
        for k in all_keys
    )
    BP = summary.get("expense_by_profit_center", {})
    BD = summary.get("expense_by_department", {})
    donut_views = "".join(
        _pv(k, yk, render_expense_views(P[k], _fine_to_rows(FT.get(k) or {}), BP.get(k), BD.get(k))) for k in all_keys
    )
    unc_amt = float(unc.get("amount") or 0) if unc else 0.0
    pl_views = "".join(
        _pv(k, yk, render_pl_table(P[k], FT.get(k, {}), unclassified_amt=unc_amt if k == yk else None))
        for k in all_keys
    )
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k])) for k in all_keys)
    # 陆总#8 / 任务书34：整体页 embed_full；月度字典全周期共享，只注入一次脚本（≡ page.js）
    _rk_store: dict = {}
    _rk_parts = [
        _pv(k, yk, render_rankings(P[k], embed_full=True, monthly_store=_rk_store, emit_monthly_script=False))
        for k in all_keys
    ]
    rank_views = monthly_data_script(_rk_store) + "".join(_rk_parts)
    hl = meta["current_month_label"].split("年")[1]
    rm_map = _period_months_map(summary)
    receipts_html = render_receipts(
        summary["receipt_order_monthly"],
        summary["meta"].get("budget"),
        period_months_map=rm_map,
        year_key=yk,
        periods=P,
        default_key=yk,
        show_delivered_unpaid=show_ar,
    )
    receipts_budget = tpl.fill("render/period_receipts.html", html=receipts_html)
    trend_html = render_trend(summary["trend"], hl, period_months_map=rm_map, year_key=yk)
    # 任务书39·E：整体费用堆叠（B8 默认隐工资）
    hide_sal = True  # 54.12 R-01 全端隐工资
    exp_raw = apply_expense_salary_hide(summary.get("expense_monthly_by_cat"), hide_sal)
    expense_trend_html = render_expense_trend(exp_raw, title="费用月度趋势 · 按报表大类")
    return {
        "title": "甲骨易智能经营罗盘",
        "particles": PARTICLES_HTML,
        "logo": logo,
        "version": _title_version_html(),
        "generated_at": meta["generated_at"],
        "pw_modal": PW_MODAL_HTML,
        "period_bar": render_period_bar(summary),
        "kpi_views": kpi_views,
        "trend_html": trend_html,
        "donut_views": donut_views,
        "pl_views": pl_views,
        "profit_rank_views": profit_rank_views,
        "receipts_budget": receipts_budget,
        "daily_html": DAILY_HTML,
        "rank_views": rank_views,
        "expense_trend_html": expense_trend_html,
        "drawer": DRAWER_HTML,
    }

def assemble_dashboard_html(frags: dict) -> str:
    """用碎片填充模板 → 完整 HTML（与历史 render_dashboard 逐字节一致）。"""
    body = tpl.fill(
        "render/dashboard_body.html",
        particles=frags["particles"],
        logo=frags["logo"],
        version=frags["version"],
        generated_at=frags["generated_at"],
        pw_modal=frags["pw_modal"],
        period_bar=frags["period_bar"],
        kpi_views=frags["kpi_views"],
        trend_html=frags["trend_html"],
        donut_views=frags["donut_views"],
        pl_views=frags["pl_views"],
        profit_rank_views=frags["profit_rank_views"],
        receipts_budget=frags["receipts_budget"],
        daily_html=frags["daily_html"],
        rank_views=frags["rank_views"],
        expense_trend_html=frags.get("expense_trend_html") or "",
        drawer=frags["drawer"],
    )
    return tpl.fill("render/page_shell.html", title=frags.get("title") or "甲骨易智能经营罗盘", body=body)

def render_dashboard(summary, cfg, logo_b64):
    """兼容入口：碎片 → 组装（B 阶段后与 JS assemble 同源）。"""
    return assemble_dashboard_html(build_dashboard_fragments(summary, cfg, logo_b64))

def build_bu_dashboard_fragments(bu_name, summary, cfg, logo_b64) -> dict:
    """BU 页渲染就绪碎片（与整体页同源组装：page.js + bu_body 模板）。"""
    meta = summary["meta"]
    P = summary["periods"]
    FT = summary.get("expense_fine_type") or {}
    yk = meta["year_key"]
    all_keys = [yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"] + meta["tab_groups"].get("区间", [])
    logo = tpl.fill("render/logo.html", src=logo_b64) if logo_b64 else ""
    alloc = meta.get("public_allocation") or {"enabled": False}
    pl_parts, tag_note = [], ""
    for k in all_keys:
        pl_html, tag_note = render_bu_pl_table(P[k], alloc, fine=FT.get(k))
        pl_parts.append(_pv(k, yk, pl_html))
    pl_views = "".join(pl_parts)
    donut_views = "".join(_pv(k, yk, render_bu_expense_views(P[k], FT.get(k))) for k in all_keys)
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k], embed_full=True)) for k in all_keys)
    _rk_store: dict = {}
    _rk_parts = [
        _pv(k, yk, render_rankings(P[k], embed_full=True, monthly_store=_rk_store, emit_monthly_script=False))
        for k in all_keys
    ]
    rank_views = monthly_data_script(_rk_store) + "".join(_rk_parts)
    name = _esc(bu_name)
    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    kpi_views = "".join(
        _pv(k, yk, render_basic(k, P, meta["year"], month_keys, budget, show_delivered_unpaid=show_ar))
        for k in all_keys
    )
    hl = meta["current_month_label"].split("年")[1]
    rm_map = _period_months_map(summary)
    receipts_html = render_receipts(
        summary["receipt_order_monthly"],
        budget,
        period_months_map=rm_map,
        year_key=yk,
        periods=P,
        default_key=yk,
        show_delivered_unpaid=show_ar,
    )
    trend_html = render_trend(summary["trend"], hl, period_months_map=rm_map, year_key=yk)
    from urllib.parse import quote as _q

    export_url = f"/bu/{_q(bu_name)}/export.png"
    pl_tag = tpl.fill("render/bu_pl_tag.html", note=_esc(tag_note)) if tag_note else ""
    # 任务书39·E：BU 费用堆叠=各月 ledger（含分摊自公共）与利润表费用口径对齐，铁律12
    bu_exp = expense_monthly_from_period_ledgers(summary)
    if not any(m.get("total") for m in bu_exp.get("months") or []):
        bu_exp = summary.get("expense_monthly_by_cat") or bu_exp
    expense_trend_html = render_expense_trend(bu_exp, title=f"{bu_name} · 费用月度趋势 · 按报表大类")
    # 任务书39·B：BU 页同款「按时间段看」（查询走 /api/bu_daily；弹窗壳仍走 rk_modal，避免双份）
    daily_html = tpl.load("partials/daily_panel.html")
    return {
        "title": f"甲骨易智能经营罗盘 · {name}",
        "particles": PARTICLES_HTML,
        "logo": logo,
        "name": name,
        "version": _title_version_html(),
        "generated_at": meta["generated_at"],
        "export_url": export_url,
        "pw_modal": PW_MODAL_HTML,
        "period_bar": render_period_bar(summary),
        "kpi_views": kpi_views,
        "trend_html": trend_html,
        "donut_views": donut_views,
        "pl_tag": pl_tag,
        "pl_views": pl_views,
        "profit_rank_views": profit_rank_views,
        "receipts_html": receipts_html,
        "daily_html": daily_html,
        "rank_views": rank_views,
        "expense_trend_html": expense_trend_html,
        "drawer": DRAWER_HTML,
        "rk_modal": RK_MODAL_HTML,
    }

def assemble_bu_dashboard_html(frags: dict) -> str:
    """BU 碎片 → 完整 HTML（与历史 render_bu_page 逐字节一致）。"""
    body = tpl.fill(
        "render/bu_body.html",
        particles=frags["particles"],
        logo=frags["logo"],
        name=frags["name"],
        version=frags["version"],
        generated_at=frags["generated_at"],
        export_url=frags["export_url"],
        pw_modal=frags["pw_modal"],
        period_bar=frags["period_bar"],
        kpi_views=frags["kpi_views"],
        trend_html=frags["trend_html"],
        donut_views=frags["donut_views"],
        pl_tag=frags["pl_tag"],
        pl_views=frags["pl_views"],
        profit_rank_views=frags["profit_rank_views"],
        receipts_html=frags["receipts_html"],
        daily_html=frags.get("daily_html") or "",
        rank_views=frags["rank_views"],
        expense_trend_html=frags.get("expense_trend_html") or "",
        drawer=frags["drawer"],
        rk_modal=frags["rk_modal"],
    )
    return tpl.fill("render/page_shell.html", title=frags.get("title") or "甲骨易智能经营罗盘", body=body)

def render_bu_page(bu_name, summary, cfg, logo_b64):
    """兼容入口：BU 碎片 → 组装。"""
    return assemble_bu_dashboard_html(build_bu_dashboard_fragments(bu_name, summary, cfg, logo_b64))

