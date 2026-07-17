#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段2：版本化 ViewModel（语义键 + 后端算好的显示串）。

字段一律 value_disp / pct_disp / *_html（SVG 字符串），前端零金额运算。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


def build_cockpit_vm(summary: dict, cfg: dict | None = None) -> CockpitVM:
    """从 summary 构建整体页 VM（复用 build_cockpit_views，零重算金额）。"""
    import api_v1
    import db
    import render
    from viewmodels import packers

    views = api_v1.build_cockpit_views(summary, cfg)
    numbers = api_v1.extract_numbers(summary)
    ts = _pack_trend_series(summary.get("trend") or [])
    tvals = list(ts.get("revenue") or []) + list(ts.get("cost") or [])
    ts["y_axis_ticks"] = packers.pack_axis_ticks(tvals)
    ts["y_axis_labels"] = [t["label"] for t in ts["y_axis_ticks"]]
    rs = _pack_receipt_series(summary.get("receipt_order_monthly") or [])
    rvals = list(rs.get("receipts") or []) + list(rs.get("orders") or [])
    rs["y_axis_ticks"] = packers.pack_axis_ticks(rvals)
    rs["y_axis_labels"] = [t["label"] for t in rs["y_axis_ticks"]]
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
    return CockpitVM(
        year_key=views.get("year_key") or "",
        period_keys=list(views.get("period_keys") or []),
        kpi=KpiCardsVM(
            year_key=views.get("year_key") or "",
            period_keys=list(views.get("period_keys") or []),
            body_by_period=dict(views.get("kpi_body") or {}),
            cards_by_period=packers.pack_kpi_cards_by_period(summary, cfg),
        ),
        trend=TrendVM(svg_html=views.get("trend_html") or "", **ts),
        pl=PLTableVM(
            body_by_period=dict(views.get("pl_body") or {}),
            table_by_period=packers.pack_pl_by_period(summary, is_bu=False),
        ),
        expense=ExpenseVM(
            body_by_period=dict(views.get("donut_body") or {}),
            trend_html=views.get("expense_trend_html") or "",
            donut_by_period=donut,
            views_by_period=packers.pack_expense_views_by_period(summary),
            donut_center_by_period=_donut_center_by_period(summary),
            **area,
        ),
        rankings=RankingsVM(
            rankings_view=dict(views.get("rankings_view") or {}),
            rankings_monthly_data=dict(views.get("rankings_monthly_data") or {}),
            profit_rank_body=dict(views.get("profit_rank_body") or {}),
            profit_rank_by_period=packers.pack_profit_rank_by_period(summary, embed_full=True),
        ),
        receipts=ReceiptsVM(receipts_budget=views.get("receipts_budget") or "", **rs),
        ledger=LedgerVM(
            columns=list(db.VIEW_EXPENSE_COLUMNS),
            forbidden_columns=list(db.VIEW_EXPENSE_HIDDEN),
        ),
        period_bar=views.get("period_bar") or "",
        daily_html=views.get("daily_html") or "",
        daily=packers.pack_daily_defaults(summary),
        numbers=numbers,
    )


def build_bu_vm(bu_name: str, summary: dict, cfg: dict | None = None) -> BUPageVM:
    import api_v1
    import db
    import render
    from viewmodels import packers

    views = api_v1.build_bu_cockpit_views(bu_name, summary, cfg)
    numbers = api_v1.extract_numbers(summary)
    ts = _pack_trend_series(summary.get("trend") or [])
    tvals = list(ts.get("revenue") or []) + list(ts.get("cost") or [])
    ts["y_axis_ticks"] = packers.pack_axis_ticks(tvals)
    ts["y_axis_labels"] = [t["label"] for t in ts["y_axis_ticks"]]
    rs = _pack_receipt_series(summary.get("receipt_order_monthly") or [])
    rvals = list(rs.get("receipts") or []) + list(rs.get("orders") or [])
    rs["y_axis_ticks"] = packers.pack_axis_ticks(rvals)
    rs["y_axis_labels"] = [t["label"] for t in rs["y_axis_ticks"]]
    bu_exp = render.expense_monthly_from_period_ledgers(summary)
    if not any(m.get("total") for m in (bu_exp.get("months") or [])):
        bu_exp = summary.get("expense_monthly_by_cat") or bu_exp
    area = _pack_expense_area(bu_exp)
    area_vals: list[float] = []
    for s in area.get("area_series") or []:
        area_vals.extend(s.get("data") or [])
    area["area_y_axis_ticks"] = packers.pack_axis_ticks(area_vals)
    area["area_y_axis_labels"] = [t["label"] for t in area["area_y_axis_ticks"]]
    donut = _pack_donut_by_period(summary)
    return BUPageVM(
        bu_name=bu_name or views.get("bu_name") or "",
        year_key=views.get("year_key") or "",
        period_keys=list(views.get("period_keys") or []),
        kpi=KpiCardsVM(
            year_key=views.get("year_key") or "",
            period_keys=list(views.get("period_keys") or []),
            body_by_period=dict(views.get("kpi_body") or {}),
            cards_by_period=packers.pack_kpi_cards_by_period(summary, cfg),
        ),
        trend=TrendVM(svg_html=views.get("trend_html") or "", **ts),
        pl=PLTableVM(
            body_by_period=dict(views.get("pl_body") or {}),
            pl_tag=views.get("pl_tag") or "",
            table_by_period=packers.pack_pl_by_period(summary, is_bu=True),
        ),
        expense=ExpenseVM(
            body_by_period=dict(views.get("donut_body") or {}),
            trend_html=views.get("expense_trend_html") or "",
            donut_by_period=donut,
            views_by_period=packers.pack_expense_views_by_period(summary),
            donut_center_by_period=_donut_center_by_period(summary),
            **area,
        ),
        rankings=RankingsVM(
            rankings_view=dict(views.get("rankings_view") or {}),
            rankings_monthly_data=dict(views.get("rankings_monthly_data") or {}),
            profit_rank_body=dict(views.get("profit_rank_body") or {}),
            profit_rank_by_period=packers.pack_profit_rank_by_period(summary, embed_full=True),
        ),
        receipts=ReceiptsVM(receipts_html=views.get("receipts_html") or "", **rs),
        ledger=LedgerVM(
            columns=list(db.VIEW_EXPENSE_COLUMNS_BU),
            forbidden_columns=list(db.VIEW_EXPENSE_HIDDEN),
        ),
        period_bar=views.get("period_bar") or "",
        daily_html=views.get("daily_html") or "",
        daily=packers.pack_daily_defaults(summary),
        numbers=numbers,
    )


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
    "build_cockpit_vm",
    "build_bu_vm",
]
