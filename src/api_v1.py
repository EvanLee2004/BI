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
    from viewmodels.format import (
        _esc,
        _merge_dual_rank,
        _rank_amt,
        attach_monthly_to_dual,
    )

    rk = period.get("rankings") or {}
    s, e = period.get("range", ("", ""))
    rm = period.get("rankings_monthly") or {}
    year = rm.get("year") or 0
    # 外部 store=多周期去重；None=单周期自带 monthly_data
    own_store = monthly_store is None
    store: dict = {} if own_store else monthly_store  # type: ignore[assignment]
    dual_s = attach_monthly_to_dual(
        _merge_dual_rank(rk.get("orders_by_sales"), rk.get("receipts_by_sales")),
        rm.get("sales"),
        year=year,
        dim="sales",
        store=store,
    )
    dual_c = attach_monthly_to_dual(
        _merge_dual_rank(rk.get("orders_by_customer"), rk.get("receipts_by_customer")),
        rm.get("customer"),
        year=year,
        dim="customer",
        store=store,
    )

    def _item_row(i, it, *, wo=None, wr=None):
        return {
            "i": i,
            "name": it["name"],
            "name_esc": _esc(it["name"]),
            "wo": round(wo if wo is not None else (it.get("wo") or 0), 1),
            "wr": round(wr if wr is not None else (it.get("wr") or 0), 1),
            "order_disp": it.get("order_disp") or _rank_amt(it.get("order") or 0),
            "receipt_disp": it.get("receipt_disp") or _rank_amt(it.get("receipt") or 0),
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
                "amt": f"下单{others.get('order_disp') or _rank_amt(others.get('order') or 0)} / 回款{others.get('receipt_disp') or _rank_amt(others.get('receipt') or 0)}",
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
        # 与 HTML 双血条卡 embed_full=True 同源：有「其余」才挂全量行
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
                row.setdefault("order_disp", _rank_amt(oa))
                row.setdefault("receipt_disp", _rank_amt(ra))
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


def _empty_html_view_fields() -> dict:
    """兼容缓存键：HTML 卡字段恒空（生产 JSON 路径不装 HTML）。"""
    return {
        "kpi_body": {},
        "pl_body": {},
        "donut_body": {},
        "profit_rank_body": {},
        "trend_html": "",
        "receipts_budget": "",
        "receipts_html": "",
        "period_bar": "",
        "daily_html": "",
        "expense_trend_html": "",
        "pl_tag": "",
    }


def build_json_views(
    summary: dict,
    cfg: dict | None = None,
    *,
    embed_full: bool = False,
    bu_name: str | None = None,
) -> dict:
    """生产 JSON/VM 就绪 views（2.7.9 G4 真路径）。

    仅 period_keys + rankings_view（format 显示串）；**零** HTML 装运层。
    recompute / generate / build_bu_pages 只许调本函数。
    """
    _ = cfg  # 预留与 HTML 签名对齐；JSON 路径暂不消费
    meta = summary.get("meta") or {}
    P = summary.get("periods") or {}
    if not meta.get("year_key") and not P:
        out = {
            "year_key": "",
            "period_keys": [],
            "rankings_view": {},
            "rankings_monthly_data": {},
            **_empty_html_view_fields(),
        }
        if bu_name is not None:
            out["scope"] = "BU"
            out["bu_name"] = bu_name or ""
        return out
    yk, ordered = _period_keys(summary)
    monthly_store: dict = {}
    rankings_view = {
        pk: rankings_view_for_period(pv, embed_full=embed_full, monthly_store=monthly_store)
        for pk, pv in P.items()
        if isinstance(pv, dict)
    }
    out = {
        "year_key": yk,
        "period_keys": ordered,
        "rankings_view": rankings_view,
        "rankings_monthly_data": monthly_store,
        **_empty_html_view_fields(),
    }
    if bu_name is not None:
        out["scope"] = "BU"
        out["bu_name"] = bu_name or ""
    return out


def build_json_bu_views(bu_name: str, summary: dict, cfg: dict | None = None) -> dict:
    """BU 生产 JSON views（铁律12：embed_full=True 本地完整名单）。"""
    return build_json_views(summary, cfg, embed_full=True, bu_name=bu_name or "")



