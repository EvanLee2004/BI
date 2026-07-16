#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驾驶舱 JSON API（v1.4 前后端分离 · 只序列化 summary，不算账）。

铁律：不 import 后改写 profit 结果；调用方传入已由 core/profit 算好的 summary。
数字提取口径与 golden/baseline_numbers.json 生成脚本一致，供全等对照测试。
"""

from __future__ import annotations

from typing import Any

# 与 golden 提取脚本 KPI_KEYS 保持一致
KPI_KEYS = (
    "delivery_count",
    "revenue_gross",
    "revenue_net",
    "vat",
    "system_direct_cost",
    "inhouse_cost",
    "production_cost",
    "gross_profit",
    "gross_margin_pct",
    "surtax",
    "other_pl",
    "pretax_profit",
    "pretax_margin_pct",
    "orders",
    "receipts",
    "receipt_order_ratio_pct",
)


def extract_numbers(summary: dict) -> dict[str, Any]:
    """从 summary 抽出与 golden/baseline_numbers.json 同结构的关键数字树。"""
    meta = summary.get("meta") or {}
    periods_out: dict[str, Any] = {}
    for pk, p in (summary.get("periods") or {}).items():
        if not isinstance(p, dict):
            continue
        row: dict[str, Any] = {k: p.get(k) for k in KPI_KEYS}
        exp = p.get("expense") or {}
        row["expense"] = {k: exp.get(k) for k in exp}
        man = p.get("manual") or {}
        row["manual"] = {k: man.get(k) for k in man}
        led = p.get("ledger_expenses") or {}
        row["ledger_expenses"] = {k: led.get(k) for k in led}
        rk = p.get("rankings") or {}
        row["rankings_totals"] = {
            dim: {
                "total": (blk or {}).get("total"),
                "n_items": len((blk or {}).get("items") or []),
                "n_full": len((blk or {}).get("full_items") or []),
            }
            for dim, blk in rk.items()
            if isinstance(blk, dict)
        }
        pr = p.get("profit_rankings") or {}
        row["profit_rankings_totals"] = {
            dim: {
                "total_revenue": (blk or {}).get("total_revenue"),
                "total_profit": (blk or {}).get("total_profit"),
                "conc_pct": (blk or {}).get("conc_pct"),
                "n_items": len((blk or {}).get("items") or []),
            }
            for dim, blk in pr.items()
            if isinstance(blk, dict)
        }
        periods_out[pk] = row
    return {
        "meta_year": meta.get("year"),
        "meta_year_key": meta.get("year_key"),
        "period_keys": list((summary.get("periods") or {}).keys()),
        "periods": periods_out,
        "trend": summary.get("trend"),
        "receipt_monthly": summary.get("receipt_monthly"),
        "receipt_order_monthly": summary.get("receipt_order_monthly"),
    }


def cockpit_payload(summary: dict, *, scope: str = "整体", bu_name: str | None = None) -> dict:
    """给前端/外部系统的完整驾驶舱 JSON（含 numbers 快照 + 原始 periods 等）。"""
    meta = summary.get("meta") or {}
    return {
        "api_version": "v1",
        "scope": scope,
        "bu_name": bu_name,
        "meta": {
            "generated_at": meta.get("generated_at"),
            "year": meta.get("year"),
            "year_key": meta.get("year_key"),
            "current_month_key": meta.get("current_month_key"),
            "current_month_label": meta.get("current_month_label"),
            "tab_groups": meta.get("tab_groups"),
            "health": meta.get("health"),
            "budget": meta.get("budget"),
            "dept_budget": meta.get("dept_budget"),
            "unclassified": meta.get("unclassified"),
            "bu_orders": meta.get("bu_orders"),
            "unassigned": meta.get("unassigned"),
        },
        "period_keys": list((summary.get("periods") or {}).keys()),
        "default_period": meta.get("year_key"),
        "periods": summary.get("periods") or {},
        "trend": summary.get("trend") or [],
        "receipt_monthly": summary.get("receipt_monthly") or [],
        "receipt_order_monthly": summary.get("receipt_order_monthly") or [],
        "expense_fine_type": summary.get("expense_fine_type") or {},
        "expense_by_department": summary.get("expense_by_department"),
        "expense_by_profit_center": summary.get("expense_by_profit_center"),
        "numbers": extract_numbers(summary),
        # B-P0/P1：各周期排名双血条渲染就绪视图
        "rankings_view": {
            pk: rankings_view_for_period(pv)
            for pk, pv in (summary.get("periods") or {}).items()
            if isinstance(pv, dict)
        },
    }


def session_public(acc: dict | None, *, is_admin_session: bool = False) -> dict:
    import accounts

    if is_admin_session and acc:
        return {
            "account": acc.get("账号"),
            "display": acc.get("显示名") or acc.get("账号"),
            "perm": accounts.PERM_ADMIN,
            "bus": [],
            "is_admin": True,
            "can_main": True,
        }
    if not acc:
        return {}
    return {
        "account": acc.get("账号"),
        "display": acc.get("显示名") or acc.get("账号"),
        "perm": acc.get("权限"),
        "bus": accounts.bu_names_of(acc),
        "is_admin": __import__("authz").is_admin(acc),
        "can_main": __import__("authz").can_main(acc),
    }


def rankings_view_for_period(
    period: dict, *, embed_full: bool = False, monthly_store: dict | None = None
) -> dict:
    """P0：排名双血条渲染就绪 JSON（显示串已算好，前端只拼 DOM）。

    embed_full=True（BU）：附带 full_items 显示串，rankings.js 预拼 .rk-full 本地展开，
    不调全公司排名 API（铁律12）。宽度/金额均在本函数算完，JS 只 toFixed 拼 CSS。
    陆总#8 / 任务书34：12 月显示串进 monthly_store（或本 view.monthly_data）；
    行上只带 mkey，禁止 items[].monthly 大数组。
    """
    import render

    rk = period.get("rankings") or {}
    s, e = period.get("range", ("", ""))
    rm = period.get("rankings_monthly") or {}
    year = rm.get("year") or 0
    # 外部 store=多周期去重；None=单周期自带 monthly_data
    own_store = monthly_store is None
    store: dict = {} if own_store else monthly_store  # type: ignore[assignment]
    dual_s = render.attach_monthly_to_dual(
        render._merge_dual_rank(rk.get("orders_by_sales"), rk.get("receipts_by_sales")),
        rm.get("sales"),
        year=year,
        dim="sales",
        store=store,
    )
    dual_c = render.attach_monthly_to_dual(
        render._merge_dual_rank(rk.get("orders_by_customer"), rk.get("receipts_by_customer")),
        rm.get("customer"),
        year=year,
        dim="customer",
        store=store,
    )

    def _item_row(i, it, *, wo=None, wr=None):
        return {
            "i": i,
            "name": it["name"],
            "name_esc": render._esc(it["name"]),
            "wo": round(wo if wo is not None else (it.get("wo") or 0), 1),
            "wr": round(wr if wr is not None else (it.get("wr") or 0), 1),
            "order_disp": it.get("order_disp") or render._rank_amt(it.get("order") or 0),
            "receipt_disp": it.get("receipt_disp") or render._rank_amt(it.get("receipt") or 0),
            "mkey": it.get("mkey") or "",
        }

    def pack(dual, title, dim):
        items = []
        for i, it in enumerate(dual.get("items") or [], 1):
            items.append(_item_row(i, it))
        others = dual.get("others")
        others_out = None
        if others:
            others_out = {
                "names": others["names"],
                "amt": f"下单{others.get('order_disp') or render._rank_amt(others.get('order') or 0)} / 回款{others.get('receipt_disp') or render._rank_amt(others.get('receipt') or 0)}",
                "count": others["names"],
            }
        out = {
            "title": title,
            "dim": dim,
            "items": items,
            "others": others_out,
            "empty": not items,
            "embed_full": bool(embed_full and others),
        }
        # 与 render._dual_card(embed_full=True) 同源：有「其余」才挂全量行
        if embed_full and others:
            full_src = dual.get("full_items") or dual.get("items") or []
            mx = dual.get("mx") or 1
            if not mx:
                mx = 1
            full_out = []
            for i, it in enumerate(full_src, 1):
                oa = float(it.get("order") or 0)
                ra = float(it.get("receipt") or 0)
                wo = max(oa / mx * 100, 0)
                wr = max(ra / mx * 100, 0)
                row = dict(it)
                row.setdefault("order_disp", render._rank_amt(oa))
                row.setdefault("receipt_disp", render._rank_amt(ra))
                full_out.append(_item_row(i, row, wo=wo, wr=wr))
            out["full_items"] = full_out
        return out

    result = {
        "visible": True,
        "start": s,
        "end": e,
        "sales": pack(dual_s, "下单/回款 · 按销售", "sales"),
        "customer": pack(dual_c, "下单/回款 · 按客户", "customer"),
    }
    if own_store:
        result["monthly_data"] = store
    return result


def _period_keys(summary: dict) -> tuple[str, list[str]]:
    meta = summary.get("meta") or {}
    periods = summary.get("periods") or {}
    yk = meta.get("year_key") or ""
    tab = meta.get("tab_groups") or {}
    period_keys = (
        ([yk] if yk else []) + list(tab.get("季度") or []) + list(tab.get("月") or []) + list(tab.get("区间") or [])
    )
    seen, ordered = set(), []
    for k in period_keys:
        if k and k not in seen and k in periods:
            seen.add(k)
            ordered.append(k)
    for k in periods:
        if k not in seen:
            ordered.append(k)
    return yk, ordered


def build_cockpit_views(summary: dict, cfg: dict | None = None) -> dict:
    """整页渲染就绪 views（B-P2~P4 shipped）。

    - rankings_view：叶子显示串 → rankings.js 组装（无服务端拼排名 DOM）
    - *_body：各周期卡正文的**显示串**（金额/条件已在 Python 算完；JS 只做 .pv 周期壳拼接）
    - trend_html / receipts_budget / period_bar：非按周期 .pv 的显示串块
    """
    import render

    cfg = cfg or {}
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    # 测试/残缺 summary：不硬崩，返回空 views
    if not meta.get("year_key") and not P:
        return {
            "year_key": "",
            "period_keys": [],
            "rankings_view": {},
            "rankings_monthly_data": {},
            "kpi_body": {},
            "pl_body": {},
            "donut_body": {},
            "profit_rank_body": {},
            "trend_html": "",
            "receipts_budget": "",
            "period_bar": "",
            "daily_html": "",
        }
    yk, ordered = _period_keys(summary)
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    BP = summary.get("expense_by_profit_center") or {}
    BD = summary.get("expense_by_department") or {}
    unc = (meta.get("unclassified") or {}).get("expense") or {}
    unc_amt = float(unc.get("amount") or 0) if unc else 0.0

    kpi_body, pl_body, donut_body, profit_rank_body = {}, {}, {}, {}
    for k in ordered:
        if k not in P:
            continue
        kpi_body[k] = render.render_basic(
            k, P, meta.get("year"), month_keys, budget, bu_orders=BUO.get(k), show_delivered_unpaid=show_ar
        )
        pl_body[k] = render.render_pl_table(P[k], FT.get(k, {}), unclassified_amt=unc_amt if k == yk else None)
        donut_body[k] = render.render_expense_views(P[k], render._fine_to_rows(FT.get(k) or {}), BP.get(k), BD.get(k))
        profit_rank_body[k] = render.render_profit_rankings(P[k])

    hl = ""
    try:
        hl = (meta.get("current_month_label") or "").split("年")[1]
    except Exception:
        hl = ""
    rm_map = render._period_months_map(summary)
    trend_html = render.render_trend(summary.get("trend") or [], hl, period_months_map=rm_map, year_key=yk)
    receipts_html = render.render_receipts(
        summary.get("receipt_order_monthly") or [],
        budget,
        period_months_map=rm_map,
        year_key=yk,
        periods=P,
        default_key=yk,
        show_delivered_unpaid=show_ar,
    )
    receipts_budget = render.tpl.fill("render/period_receipts.html", html=receipts_html)
    try:
        period_bar = render.render_period_bar(summary)
    except Exception:
        period_bar = ""

    # 任务书34：全周期去重一份 rankings_monthly_data；各 period 行只带 mkey
    monthly_store: dict = {}
    rankings_view = {
        pk: rankings_view_for_period(pv, embed_full=True, monthly_store=monthly_store)
        for pk, pv in P.items()
        if isinstance(pv, dict)
    }
    return {
        "year_key": yk,
        "period_keys": ordered,
        # 陆总#8 + 其余本地展开：整体页也 embed_full（完整名单预挂 views，零新 API）
        "rankings_view": rankings_view,
        "rankings_monthly_data": monthly_store,
        # 周期卡正文显示串（JS wrap .pv）
        "kpi_body": kpi_body,
        "pl_body": pl_body,
        "donut_body": donut_body,
        "profit_rank_body": profit_rank_body,
        # 非 .pv 块显示串
        "trend_html": trend_html,
        "receipts_budget": receipts_budget,
        "period_bar": period_bar,
        "daily_html": render.DAILY_HTML,
        # 任务书39·E：费用堆叠（B8 默隐工资）
        "expense_trend_html": render.render_expense_trend(
            render.apply_expense_salary_hide(
                summary.get("expense_monthly_by_cat"),
                not bool(cfg.get("overall_see_salary", False)),
            ),
            title="费用月度趋势 · 按报表大类",
        ),
    }


def build_bu_cockpit_views(bu_name: str, summary: dict, cfg: dict | None = None) -> dict:
    """BU 页渲染就绪 views（与 render.build_bu_dashboard_fragments 同源渲染函数）。

    复用：render_basic / render_bu_pl_table / render_bu_expense_views /
    render_profit_rankings(embed_full=True) / rankings_view_for_period /
    render_trend / render_receipts / render_period_bar / bu_pl_tag 模板。
    绝不走整体页 render_pl_table / render_expense_views / 无 embed_full 排名。
    """
    import render

    cfg = cfg or {}
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    FT = summary.get("expense_fine_type") or {}
    if not meta.get("year_key") and not P:
        return {
            "year_key": "",
            "period_keys": [],
            "rankings_view": {},
            "rankings_monthly_data": {},
            "kpi_body": {},
            "pl_body": {},
            "donut_body": {},
            "profit_rank_body": {},
            "trend_html": "",
            "receipts_html": "",
            "pl_tag": "",
            "period_bar": "",
            "daily_html": "",
            "expense_trend_html": "",
            "scope": "BU",
            "bu_name": bu_name or "",
        }
    yk, ordered = _period_keys(summary)
    month_keys = (meta.get("tab_groups") or {}).get("月") or []
    budget = meta.get("budget")
    show_ar = bool(cfg.get("show_delivered_unpaid", False))
    alloc = meta.get("public_allocation") or {"enabled": False}

    kpi_body, pl_body, donut_body, profit_rank_body = {}, {}, {}, {}
    tag_note = ""
    for k in ordered:
        if k not in P:
            continue
        # 与 build_bu_dashboard_fragments 一致：BU KPI 不传 bu_orders
        kpi_body[k] = render.render_basic(k, P, meta.get("year"), month_keys, budget, show_delivered_unpaid=show_ar)
        pl_html, tag_note = render.render_bu_pl_table(P[k], alloc, fine=FT.get(k))
        pl_body[k] = pl_html
        donut_body[k] = render.render_bu_expense_views(P[k], FT.get(k))
        # 铁律12：收入排名「其余」预渲染 .pr-full，不调全公司 API
        profit_rank_body[k] = render.render_profit_rankings(P[k], embed_full=True)

    hl = ""
    try:
        hl = (meta.get("current_month_label") or "").split("年")[1]
    except Exception:
        hl = ""
    rm_map = render._period_months_map(summary)
    trend_html = render.render_trend(summary.get("trend") or [], hl, period_months_map=rm_map, year_key=yk)
    # BU 模板用 receipts_html（非整体页 period_receipts 包壳）
    receipts_html = render.render_receipts(
        summary.get("receipt_order_monthly") or [],
        budget,
        period_months_map=rm_map,
        year_key=yk,
        periods=P,
        default_key=yk,
        show_delivered_unpaid=show_ar,
    )
    try:
        period_bar = render.render_period_bar(summary)
    except Exception:
        period_bar = ""
    pl_tag = render.tpl.fill("render/bu_pl_tag.html", note=render._esc(tag_note)) if tag_note else ""

    monthly_store: dict = {}
    rankings_view = {
        pk: rankings_view_for_period(pv, embed_full=True, monthly_store=monthly_store)
        for pk, pv in P.items()
        if isinstance(pv, dict)
    }
    # 任务书39·B/E：与 build_bu_dashboard_fragments 同源（弹窗壳仍在 fragments.rk_modal）
    daily_html = render.tpl.load("partials/daily_panel.html")
    bu_exp = render.expense_monthly_from_period_ledgers(summary)
    if not any(m.get("total") for m in bu_exp.get("months") or []):
        bu_exp = summary.get("expense_monthly_by_cat") or bu_exp
    expense_trend_html = render.render_expense_trend(
        bu_exp, title=f"{bu_name} · 费用月度趋势 · 按报表大类"
    )
    return {
        "year_key": yk,
        "period_keys": ordered,
        "scope": "BU",
        "bu_name": bu_name or "",
        # 下单/回款双血条叶子：embed_full=True → rankings.js 拼 .rk-full（铁律12）
        "rankings_view": rankings_view,
        "rankings_monthly_data": monthly_store,
        "kpi_body": kpi_body,
        "pl_body": pl_body,
        "donut_body": donut_body,
        "profit_rank_body": profit_rank_body,
        "trend_html": trend_html,
        "receipts_html": receipts_html,
        "pl_tag": pl_tag,
        "period_bar": period_bar,
        "daily_html": daily_html,
        "expense_trend_html": expense_trend_html,
    }


# 客户端路径须由 JS 组装的 fragments 字段（禁止服务端预拼后 fill）
# 整体页 + BU 页共有字段；BU 另有 pl_tag 等由 bu 模板填
_CLIENT_ASSEMBLE_FIELDS = (
    "kpi_views",
    "pl_views",
    "donut_views",
    "profit_rank_views",
    "rank_views",
    "trend_html",
    "receipts_budget",
    "period_bar",
    "daily_html",
    "expense_trend_html",  # 任务书39·E 由 views 注入
    # BU 模板字段
    "receipts_html",
    "pl_tag",
)


def client_strip_fragments(fr: dict, *, assert_clean: bool = False) -> dict:
    """HTTP client 路径：清空所有须 JS 组装的卡字段。

    publish-once 后缓存已是 strip 态，本函数为幂等 no-op（再 strip 仍空）。
    assert_clean=True 时若发现非空卡字段则抛 AssertionError（测试守卫双渲染回潮）。
    """
    out = dict(fr or {})
    dirty = []
    for f in _CLIENT_ASSEMBLE_FIELDS:
        if out.get(f):
            dirty.append(f)
            out[f] = ""
        elif f in out:
            out[f] = ""
    if assert_clean and dirty:
        raise AssertionError(f"publish-once 期望 fragments 已 strip，仍非空: {dirty}")
    return out


def fragments_client_fields_empty(fr: dict) -> bool:
    """True = 所有 client 组装字段为空（publish-once 缓存合格）。"""
    fr = fr or {}
    return all(not fr.get(f) for f in _CLIENT_ASSEMBLE_FIELDS)


def cockpit_fragments(summary: dict, cfg: dict, logo_b64: str | None = None, *, client: bool = True) -> dict:
    """整页碎片 + views。

    client=True：清空须由 JS 组装的卡字段，强制 shipped 路径。
    client=False：保留 Python 全量预渲染（导出/快照）。
    """
    import render

    fr = render.build_dashboard_fragments(summary, cfg, logo_b64 or "")
    views = build_cockpit_views(summary, cfg)
    if client:
        fr = client_strip_fragments(fr)
    return {
        "api_version": "v1",
        "mode": "fragments",
        "fragments": fr,
        "views": views,
    }
