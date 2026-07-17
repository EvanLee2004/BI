#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段2：版本化 ViewModel（语义键 + 后端算好的显示串）。

字段一律 value_disp / pct_disp / *_html（SVG 字符串），前端零金额运算。
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def frontend_mode(cfg: dict | None = None) -> str:
    """vue|legacy：env KANBAN_FRONTEND > config.frontend > vue。

    任务书51·B1：vue 路径不执行 legacy HTML 建造；legacy 仍走完整 HTML views。
    """
    env = (os.environ.get("KANBAN_FRONTEND") or "").strip().lower()
    if env in ("vue", "legacy"):
        return env
    cfg_fe = str((cfg or {}).get("frontend") or "").strip().lower()
    if cfg_fe in ("vue", "legacy"):
        return cfg_fe
    return "vue"


def _vue_core_views(summary: dict) -> dict[str, Any]:
    """Vue 路径仅建造结构化必需元数据：周期键 + 双血条 rankings_view（非 HTML）。

    **不**调用 render_basic / render_pl_table / render_expense_views / SVG 等 HTML 路径。
    """
    import api_v1

    yk, ordered = api_v1._period_keys(summary)
    P = summary.get("periods") or {}
    monthly_store: dict = {}
    rankings_view = {
        pk: api_v1.rankings_view_for_period(pv, embed_full=True, monthly_store=monthly_store)
        for pk, pv in P.items()
        if isinstance(pv, dict)
    }
    return {
        "year_key": yk,
        "period_keys": ordered,
        "rankings_view": rankings_view,
        "rankings_monthly_data": monthly_store,
        "pl_tag": "",
        "bu_name": "",
    }


class KpiCardsVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    year_key: str = ""
    period_keys: list[str] = Field(default_factory=list)
    # 周期 → 已渲染 KPI 卡 HTML（legacy/deprecated，Vue 改用 cards_by_period）
    body_by_period: dict[str, str] = Field(default_factory=dict)
    # 任务书50·B：结构化 KPI
    cards_by_period: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class TrendVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    svg_html: str = ""  # 后端 SVG（legacy/导出）
    # ECharts 用：标签与显示串均后端产；数值为后端已算好的数（前端只填 option，零运算）
    labels: list[str] = Field(default_factory=list)
    revenue: list[float] = Field(default_factory=list)
    cost: list[float] = Field(default_factory=list)
    margin_pct: list[float] = Field(default_factory=list)
    revenue_disp: list[str] = Field(default_factory=list)
    cost_disp: list[str] = Field(default_factory=list)
    margin_pct_disp: list[str] = Field(default_factory=list)
    # 任务书50·C：Y 轴刻度显示串（后端下发，禁前端格式化金额）
    y_axis_labels: list[str] = Field(default_factory=list)
    y_axis_ticks: list[dict[str, Any]] = Field(default_factory=list)


class PLTableVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_by_period: dict[str, str] = Field(default_factory=dict)  # deprecated HTML
    pl_tag: str = ""
    # 任务书50·B：{period: {rows, details}}
    table_by_period: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ExpenseVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_by_period: dict[str, str] = Field(default_factory=dict)  # deprecated HTML
    trend_html: str = ""  # 费用面积图 SVG 卡
    # 堆叠面积：categories + 每月各层金额/显示串
    area_categories: list[str] = Field(default_factory=list)
    area_labels: list[str] = Field(default_factory=list)  # 1月..12月
    area_series: list[dict[str, Any]] = Field(default_factory=list)  # [{name, data, data_disp}]
    area_totals_disp: list[str] = Field(default_factory=list)
    # 环形：当前周期叶子
    donut_by_period: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    # 任务书50·B：四态构成横条
    views_by_period: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # 环形中心文案
    donut_center_by_period: dict[str, dict[str, str]] = Field(default_factory=dict)
    area_y_axis_labels: list[str] = Field(default_factory=list)
    area_y_axis_ticks: list[dict[str, Any]] = Field(default_factory=list)


class RankingsVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    rankings_view: dict[str, Any] = Field(default_factory=dict)
    rankings_monthly_data: dict[str, Any] = Field(default_factory=dict)
    profit_rank_body: dict[str, str] = Field(default_factory=dict)  # deprecated HTML
    # 任务书50·B：结构化利润结构
    profit_rank_by_period: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ReceiptsVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    receipts_html: str = ""
    receipts_budget: str = ""
    # 回款柱线
    labels: list[str] = Field(default_factory=list)
    receipts: list[float] = Field(default_factory=list)
    orders: list[float] = Field(default_factory=list)
    receipts_disp: list[str] = Field(default_factory=list)
    orders_disp: list[str] = Field(default_factory=list)
    ratio_pct_disp: list[str] = Field(default_factory=list)
    y_axis_labels: list[str] = Field(default_factory=list)
    y_axis_ticks: list[dict[str, Any]] = Field(default_factory=list)
    # 摘要条显示串（可选）
    summary_by_period: dict[str, dict[str, str]] = Field(default_factory=dict)


class LedgerVM(BaseModel):
    """明细白名单：行数据走 GET /api/v1/vm/ledger（任何会话一律白名单列）。"""
    model_config = ConfigDict(extra="allow")
    columns: list[str] = Field(default_factory=list)
    note: str = "行数据见 /api/v1/vm/ledger"
    forbidden_columns: list[str] = Field(default_factory=list)


class BUPageVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    scope: str = "BU"
    bu_name: str = ""
    year_key: str = ""
    period_keys: list[str] = Field(default_factory=list)
    kpi: KpiCardsVM = Field(default_factory=KpiCardsVM)
    trend: TrendVM = Field(default_factory=TrendVM)
    pl: PLTableVM = Field(default_factory=PLTableVM)
    expense: ExpenseVM = Field(default_factory=ExpenseVM)
    rankings: RankingsVM = Field(default_factory=RankingsVM)
    receipts: ReceiptsVM = Field(default_factory=ReceiptsVM)
    ledger: LedgerVM = Field(default_factory=LedgerVM)
    period_bar: str = ""
    daily_html: str = ""  # deprecated
    daily: dict[str, Any] = Field(default_factory=dict)
    # 与 fragments 数字对齐用：extract_numbers 快照
    numbers: dict[str, Any] = Field(default_factory=dict)


class CockpitVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    api_version: str = "v1"
    scope: str = "整体"
    year_key: str = ""
    period_keys: list[str] = Field(default_factory=list)
    kpi: KpiCardsVM = Field(default_factory=KpiCardsVM)
    trend: TrendVM = Field(default_factory=TrendVM)
    pl: PLTableVM = Field(default_factory=PLTableVM)
    expense: ExpenseVM = Field(default_factory=ExpenseVM)
    rankings: RankingsVM = Field(default_factory=RankingsVM)
    receipts: ReceiptsVM = Field(default_factory=ReceiptsVM)
    ledger: LedgerVM = Field(default_factory=LedgerVM)
    period_bar: str = ""
    daily_html: str = ""  # deprecated
    daily: dict[str, Any] = Field(default_factory=dict)
    numbers: dict[str, Any] = Field(default_factory=dict)


def _pack_trend_series(trend_rows) -> dict[str, Any]:
    """summary['trend'] → ECharts 序列（显示串用 charts.fmt_wan）。"""
    import charts

    labels, rev, cost, margin = [], [], [], []
    rev_d, cost_d, mar_d = [], [], []
    for row in trend_rows or []:
        if not row or len(row) < 4:
            continue
        lab, r, c, m = row[0], float(row[1] or 0), float(row[2] or 0), float(row[3] or 0)
        labels.append(str(lab))
        rev.append(r)
        cost.append(c)
        margin.append(m)
        rev_d.append(charts.fmt_wan(r))
        cost_d.append(charts.fmt_wan(c))
        mar_d.append(f"{m:.1f}%")
    return {
        "labels": labels,
        "revenue": rev,
        "cost": cost,
        "margin_pct": margin,
        "revenue_disp": rev_d,
        "cost_disp": cost_d,
        "margin_pct_disp": mar_d,
    }


def _pack_receipt_series(rows) -> dict[str, Any]:
    import charts

    labels, recs, ords = [], [], []
    rd, od, ratio_d = [], [], []
    for row in rows or []:
        if not row or len(row) < 3:
            continue
        lab = str(row[0])
        rec = float(row[1] or 0)
        order = float(row[2] or 0)
        ratio = float(row[3] or 0) if len(row) > 3 else 0.0
        labels.append(lab)
        recs.append(rec)
        ords.append(order)
        rd.append(charts.fmt_wan(rec))
        od.append(charts.fmt_wan(order))
        ratio_d.append(f"{ratio:.1f}%")
    return {
        "labels": labels,
        "receipts": recs,
        "orders": ords,
        "receipts_disp": rd,
        "orders_disp": od,
        "ratio_pct_disp": ratio_d,
    }


def _pack_expense_area(raw: dict | None) -> dict[str, Any]:
    import charts

    raw = raw or {}
    cats = list(raw.get("categories") or [])
    labels = [f"{i + 1}月" for i in range(12)]
    series = []
    totals_disp = []
    for c in cats:
        data, data_disp = [], []
        for i in range(12):
            months = raw.get("months") or []
            m = months[i] if i < len(months) else {}
            by = m.get("by_cat") or {}
            amt = float(by.get(c) or 0)
            data.append(amt)
            data_disp.append(charts.fmt_wan(amt))
        series.append({"name": c, "data": data, "data_disp": data_disp})
    for i in range(12):
        months = raw.get("months") or []
        m = months[i] if i < len(months) else {}
        totals_disp.append(charts.fmt_wan(float(m.get("total") or 0)))
    return {
        "area_categories": cats,
        "area_labels": labels,
        "area_series": series,
        "area_totals_disp": totals_disp,
    }


def _pack_donut_by_period(summary: dict) -> dict[str, list[dict[str, Any]]]:
    """各周期费用大类 → [{name, value, value_disp, pct_disp}]（pct 后端算）。"""
    import charts

    out: dict[str, list[dict[str, Any]]] = {}
    for pk, p in (summary.get("periods") or {}).items():
        if not isinstance(p, dict):
            continue
        exp = p.get("expense") or {}
        items = []
        total = sum(float(exp.get(k) or 0) for k in exp if k and not str(k).startswith("_"))
        for k, v in exp.items():
            if str(k).startswith("_"):
                continue
            amt = float(v or 0)
            if amt <= 0:
                continue
            pct = (amt / total * 100.0) if total else 0.0
            items.append(
                {
                    "name": str(k),
                    "value": amt,
                    "value_disp": charts.fmt_wan(amt),
                    "pct_disp": f"{pct:.1f}%",
                }
            )
        out[pk] = items
    return out


def _donut_center_by_period(summary: dict) -> dict[str, dict[str, str]]:
    import charts

    out: dict[str, dict[str, str]] = {}
    for pk, p in (summary.get("periods") or {}).items():
        if not isinstance(p, dict):
            continue
        e = p.get("expense") or {}
        tot = float(e.get("total") or 0)
        out[pk] = {"title": "期间费用", "total_disp": charts.fmt_wan(tot) + "万"}
    return out


def _assemble_vm(
    summary: dict,
    views: dict,
    *,
    scope: str,
    cfg: dict | None = None,
    bu_name: str | None = None,
    html: dict | None = None,
) -> CockpitVM | BUPageVM:
    """任务书51·B3：VM 组装单一主函数（趋势/回款/面积/刻度/环形/KPI/PL/费用/排名）。

    scope=整体 → CockpitVM；scope=BU → BUPageVM。
    html 为 legacy 可选碎片（vue 路径传空 dict）。
    """
    import api_v1
    import db
    import render
    from viewmodels import packers

    html = html or {}
    is_bu = scope == "BU"
    yk = views.get("year_key") or ""
    pkeys = list(views.get("period_keys") or [])
    numbers = api_v1.extract_numbers(summary)

    ts = _pack_trend_series(summary.get("trend") or [])
    tvals = list(ts.get("revenue") or []) + list(ts.get("cost") or [])
    ts["y_axis_ticks"] = packers.pack_axis_ticks(tvals)
    ts["y_axis_labels"] = [t["label"] for t in ts["y_axis_ticks"]]

    rs = _pack_receipt_series(summary.get("receipt_order_monthly") or [])
    rvals = list(rs.get("receipts") or []) + list(rs.get("orders") or [])
    rs["y_axis_ticks"] = packers.pack_axis_ticks(rvals)
    rs["y_axis_labels"] = [t["label"] for t in rs["y_axis_ticks"]]

    if is_bu:
        exp_raw = render.expense_monthly_from_period_ledgers(summary)
        if not any(m.get("total") for m in (exp_raw.get("months") or [])):
            exp_raw = summary.get("expense_monthly_by_cat") or exp_raw
    else:
        exp_raw = render.apply_expense_salary_hide(
            summary.get("expense_monthly_by_cat"),
            not bool((cfg or {}).get("overall_see_salary", False)),
        )
    area = _pack_expense_area(exp_raw)
    area_vals: list[float] = []
    for s in area.get("area_series") or []:
        area_vals.extend(s.get("data") or [])
    area["area_y_axis_ticks"] = packers.pack_axis_ticks(area_vals)
    area["area_y_axis_labels"] = [t["label"] for t in area["area_y_axis_ticks"]]
    donut = _pack_donut_by_period(summary)

    kpi = KpiCardsVM(
        year_key=yk,
        period_keys=pkeys,
        body_by_period=dict(html.get("kpi_body") or {}),
        cards_by_period=packers.pack_kpi_cards_by_period(summary, cfg),
    )
    trend = TrendVM(svg_html=html.get("trend_html") or "", **ts)
    pl = PLTableVM(
        body_by_period=dict(html.get("pl_body") or {}),
        pl_tag=html.get("pl_tag") or "",
        table_by_period=packers.pack_pl_by_period(summary, is_bu=is_bu),
    )
    expense = ExpenseVM(
        body_by_period=dict(html.get("donut_body") or {}),
        trend_html=html.get("expense_trend_html") or "",
        donut_by_period=donut,
        views_by_period=packers.pack_expense_views_by_period(summary),
        donut_center_by_period=_donut_center_by_period(summary),
        **area,
    )
    rankings = RankingsVM(
        rankings_view=dict(views.get("rankings_view") or {}),
        rankings_monthly_data=dict(views.get("rankings_monthly_data") or {}),
        profit_rank_body=dict(html.get("profit_rank_body") or {}),
        profit_rank_by_period=packers.pack_profit_rank_by_period(summary, embed_full=True),
    )
    receipts = ReceiptsVM(
        receipts_html=html.get("receipts_html") or "",
        receipts_budget=html.get("receipts_budget") or "",
        **rs,
    )
    ledger = LedgerVM(
        columns=list(db.VIEW_EXPENSE_COLUMNS_BU if is_bu else db.VIEW_EXPENSE_COLUMNS),
        forbidden_columns=list(db.VIEW_EXPENSE_HIDDEN),
    )
    period_bar = html.get("period_bar") or ""
    daily_html = html.get("daily_html") or ""
    daily = packers.pack_daily_defaults(summary)

    if is_bu:
        return BUPageVM(
            bu_name=bu_name or views.get("bu_name") or "",
            year_key=yk,
            period_keys=pkeys,
            kpi=kpi,
            trend=trend,
            pl=pl,
            expense=expense,
            rankings=rankings,
            receipts=receipts,
            ledger=ledger,
            period_bar=period_bar,
            daily_html=daily_html,
            daily=daily,
            numbers=numbers,
        )
    return CockpitVM(
        year_key=yk,
        period_keys=pkeys,
        kpi=kpi,
        trend=trend,
        pl=pl,
        expense=expense,
        rankings=rankings,
        receipts=receipts,
        ledger=ledger,
        period_bar=period_bar,
        daily_html=daily_html,
        daily=daily,
        numbers=numbers,
    )


def build_cockpit_vm(summary: dict, cfg: dict | None = None) -> CockpitVM:
    """整体页 VM 薄包装（任务书51·B3 → _assemble_vm）。

    任务书51·B1：vue 模式**不执行** legacy HTML 建造；legacy 模式才调 build_cockpit_views。
    """
    import api_v1

    mode = frontend_mode(cfg)
    if mode == "legacy":
        views = api_v1.build_cockpit_views(summary, cfg)
        html = {
            "kpi_body": dict(views.get("kpi_body") or {}),
            "pl_body": dict(views.get("pl_body") or {}),
            "donut_body": dict(views.get("donut_body") or {}),
            "profit_rank_body": dict(views.get("profit_rank_body") or {}),
            "trend_html": views.get("trend_html") or "",
            "expense_trend_html": views.get("expense_trend_html") or "",
            "receipts_budget": views.get("receipts_budget") or "",
            "period_bar": views.get("period_bar") or "",
            "daily_html": views.get("daily_html") or "",
        }
    else:
        views = _vue_core_views(summary)
        html = {}
    return _assemble_vm(summary, views, scope="整体", cfg=cfg, html=html)  # type: ignore[return-value]


def build_bu_vm(bu_name: str, summary: dict, cfg: dict | None = None) -> BUPageVM:
    """BU 页 VM 薄包装（任务书51·B3 → _assemble_vm）。vue 同样跳过 legacy HTML。"""
    import api_v1

    mode = frontend_mode(cfg)
    if mode == "legacy":
        views = api_v1.build_bu_cockpit_views(bu_name, summary, cfg)
        html = {
            "kpi_body": dict(views.get("kpi_body") or {}),
            "pl_body": dict(views.get("pl_body") or {}),
            "donut_body": dict(views.get("donut_body") or {}),
            "profit_rank_body": dict(views.get("profit_rank_body") or {}),
            "trend_html": views.get("trend_html") or "",
            "expense_trend_html": views.get("expense_trend_html") or "",
            "receipts_html": views.get("receipts_html") or "",
            "period_bar": views.get("period_bar") or "",
            "daily_html": views.get("daily_html") or "",
            "pl_tag": views.get("pl_tag") or "",
        }
    else:
        views = _vue_core_views(summary)
        views["bu_name"] = bu_name or ""
        html = {}
    return _assemble_vm(summary, views, scope="BU", cfg=cfg, bu_name=bu_name, html=html)  # type: ignore[return-value]


__all__ = [
    "KpiCardsVM",
    "TrendVM",
    "PLTableVM",
    "ExpenseVM",
    "RankingsVM",
    "ReceiptsVM",
    "LedgerVM",
    "BUPageVM",
    "CockpitVM",
    "frontend_mode",
    "build_cockpit_vm",
    "build_bu_vm",
]
