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
    # 任务书51·B7：min/max/interval，前端禁最近刻度扫描
    y_axis_min: float = 0.0
    y_axis_max: float = 0.0
    y_axis_interval: float = 0.0


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
    # 任务书52·F-4
    area_y_axis_min: float = 0.0
    area_y_axis_max: float = 0.0
    area_y_axis_interval: float = 0.0


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
    y_axis_min: float = 0.0
    y_axis_max: float = 0.0
    y_axis_interval: float = 0.0
    # 摘要条显示串（54.4·B4 由 packer 用 summary 已算值填充）
    summary_by_period: dict[str, dict[str, str]] = Field(default_factory=dict)
    # 月均预算虚线（年回款目标/12 展示；数值与柱同单位）
    budget_month: float = 0.0
    budget_month_disp: str = ""


class LedgerVM(BaseModel):
    """明细白名单：行数据走 GET /api/v1/vm/ledger（任何会话一律白名单列）。"""
    model_config = ConfigDict(extra="allow")
    columns: list[str] = Field(default_factory=list)
    note: str = "行数据见 /api/v1/vm/ledger"
    forbidden_columns: list[str] = Field(default_factory=list)
    # 任务书51·B6：周期 → month_from/month_to（YYYY-MM），前端只赋值
    period_months: dict[str, dict[str, str]] = Field(default_factory=dict)


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


def _attach_year_budget_bars(row: dict, budget: dict, charts) -> None:
    for key, title, bkey in (
        ("receipt_target_disp", "回款年目标", "receipt"),
        ("order_target_disp", "下单年目标", "order"),
    ):
        b = budget.get(bkey) if isinstance(budget, dict) else None
        if not (b and b.get("target") is not None):
            continue
        pct = b.get("pct")
        if pct is None:
            pct_txt = "—"
        elif float(pct) > 999:
            pct_txt = ">999% · 目标待校准"
        else:
            pct_txt = f"{float(pct):.1f}%"
        bw = max(0.0, min(float(pct or 0), 100.0))
        row[key] = charts.fmt_wan(float(b["target"]))
        row[f"{bkey}_pct_disp"] = pct_txt
        row[f"{bkey}_bar_w"] = f"{bw:.1f}"
        row[f"{bkey}_title"] = title


def _pack_one_period_receipt_row(pk, p, yk, budget, charts) -> dict[str, str] | None:
    if not isinstance(p, dict):
        return None
    tot_o = float(p.get("orders") or 0)
    tot_r = float(p.get("receipts") or 0)
    gap = tot_o - tot_r
    ratio = p.get("receipt_order_ratio_pct")
    if ratio is None and tot_o:
        ratio = round(tot_r / tot_o * 100, 2) if tot_o else None
    ytd_txt = f"{float(ratio):.1f}%" if ratio is not None else "—"
    try:
        bar_w = max(0.0, min(float(ratio or 0), 100.0))
    except (TypeError, ValueError):
        bar_w = 0.0
    gap_hint = "尚待回款" if gap > 0 else ("回款超下单" if gap < 0 else "持平")
    row: dict[str, str] = {
        "period_label": str(p.get("label") or pk),
        "orders_disp": charts.fmt_wan(tot_o),
        "receipts_disp": charts.fmt_wan(tot_r),
        "gap_disp": charts.fmt_wan(abs(gap)),
        "gap_hint": gap_hint,
        "ratio_disp": ytd_txt,
        "bar_w": f"{bar_w:.1f}",
    }
    if pk == yk and budget:
        _attach_year_budget_bars(row, budget, charts)
    return row


def _pack_receipts_side_and_budget(summary: dict) -> dict[str, Any]:
    """任务书54.4·B4：用 summary 已算好的 orders/receipts/ratio/budget 组装显示串。

    - summary_by_period：各周期右侧摘要（总下单/总回款/尚待回款/回款率/年目标条）
    - receipts_budget：月均预算显示串（年回款目标÷12 的展示；与 legacy markLine 一致）
    - budget_month / budget_month_disp：图上虚线用（数值与柱同口径已算目标）
    不碰 profit 算账；仅显示串与展示刻度。
    """
    import charts

    meta = summary.get("meta") or {}
    yk = meta.get("year_key") or ""
    budget = meta.get("budget") or {}
    periods = summary.get("periods") or {}
    summary_by_period: dict[str, dict[str, str]] = {}
    for pk, p in periods.items():
        row = _pack_one_period_receipt_row(pk, p, yk, budget, charts)
        if row is not None:
            summary_by_period[pk] = row
    rb = budget.get("receipt") if isinstance(budget, dict) else None
    budget_month = None
    budget_month_disp = ""
    receipts_budget = ""
    if rb and rb.get("target") is not None:
        budget_month = float(rb["target"]) / 12.0
        budget_month_disp = charts.fmt_wan(budget_month)
        receipts_budget = f"月均预算 {budget_month_disp}万"
    return {
        "summary_by_period": summary_by_period,
        "receipts_budget": receipts_budget,
        "budget_month": budget_month if budget_month is not None else 0.0,
        "budget_month_disp": budget_month_disp,
    }

def _pack_expense_area(raw: dict | None) -> dict[str, Any]:
    """费用面积序列。任务书52·F-4：裁到最后一个有数据的月份（后缀空月不拖尾）。"""
    import charts

    raw = raw or {}
    cats = list(raw.get("categories") or [])
    months = raw.get("months") or []
    # 找最后一个 total>0 或 任一类 >0 的月（1-based 月序 0..11）
    last = -1
    for i in range(min(12, len(months))):
        m = months[i] if i < len(months) else {}
        tot = float(m.get("total") or 0)
        if tot > 0.005:
            last = i
            continue
        by = m.get("by_cat") or {}
        if any(float(by.get(c) or 0) > 0.005 for c in cats):
            last = i
    n = last + 1 if last >= 0 else 0
    if n <= 0:
        # 全空：仍给 1 个占位月，避免 ECharts 空轴
        n = 1
    labels = [f"{i + 1}月" for i in range(n)]
    series = []
    totals_disp = []
    for c in cats:
        data, data_disp = [], []
        for i in range(n):
            m = months[i] if i < len(months) else {}
            by = m.get("by_cat") or {}
            amt = float(by.get(c) or 0)
            data.append(amt)
            data_disp.append(charts.fmt_wan(amt))
        series.append({"name": c, "data": data, "data_disp": data_disp})
    for i in range(n):
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
        # "total"=合计键，不是费用大类：进分母/进扇区都会把占比稀释一半（legacy render 用大类白名单天然排除）
        total = sum(float(exp.get(k) or 0) for k in exp if k and not str(k).startswith("_") and str(k) != "total")
        for k, v in exp.items():
            if str(k).startswith("_") or str(k) == "total":
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
    tmeta = packers.pack_axis_meta(tvals)
    ts["y_axis_ticks"] = tmeta["ticks"]
    ts["y_axis_labels"] = [t["label"] for t in tmeta["ticks"]]
    ts["y_axis_min"] = tmeta["min"]
    ts["y_axis_max"] = tmeta["max"]
    ts["y_axis_interval"] = tmeta["interval"]

    rs = _pack_receipt_series(summary.get("receipt_order_monthly") or [])
    rvals = list(rs.get("receipts") or []) + list(rs.get("orders") or [])
    rmeta = packers.pack_axis_meta(rvals)
    rs["y_axis_ticks"] = rmeta["ticks"]
    rs["y_axis_labels"] = [t["label"] for t in rmeta["ticks"]]
    rs["y_axis_min"] = rmeta["min"]
    rs["y_axis_max"] = rmeta["max"]
    rs["y_axis_interval"] = rmeta["interval"]

    if is_bu:
        exp_raw = render.expense_monthly_from_period_ledgers(summary)
        if not any(m.get("total") for m in (exp_raw.get("months") or [])):
            exp_raw = summary.get("expense_monthly_by_cat") or exp_raw
    else:
        exp_raw = render.apply_expense_salary_hide(
            summary.get("expense_monthly_by_cat"),
            True,  # 54.12 R-01 全端隐工资
        )
    # 54.15 R-30：两图白名单（剔成本/非利润表），与环形同源常量
    from domain.expense.chart_whitelist import filter_expense_monthly_raw_for_charts

    area = _pack_expense_area(filter_expense_monthly_raw_for_charts(exp_raw, cfg))
    area_vals: list[float] = []
    for s in area.get("area_series") or []:
        area_vals.extend(s.get("data") or [])
    ameta = packers.pack_axis_meta(area_vals)
    area["area_y_axis_ticks"] = ameta["ticks"]
    area["area_y_axis_labels"] = [t["label"] for t in ameta["ticks"]]
    area["area_y_axis_min"] = ameta["min"]
    area["area_y_axis_max"] = ameta["max"]
    area["area_y_axis_interval"] = ameta["interval"]
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
    side_pack = _pack_receipts_side_and_budget(summary)
    # vue 路径：用 packer 显示串填空字段；legacy html 若已有完整 HTML 优先保留给对照
    rb_html = (html.get("receipts_budget") or "").strip()
    receipts = ReceiptsVM(
        receipts_html=html.get("receipts_html") or "",
        receipts_budget=rb_html or side_pack.get("receipts_budget") or "",
        summary_by_period=side_pack.get("summary_by_period") or {},
        budget_month=side_pack.get("budget_month") or 0.0,
        budget_month_disp=side_pack.get("budget_month_disp") or "",
        **rs,
    )
    ledger = LedgerVM(
        columns=list(db.VIEW_EXPENSE_COLUMNS_BU if is_bu else db.VIEW_EXPENSE_COLUMNS),
        forbidden_columns=list(db.VIEW_EXPENSE_HIDDEN),
        period_months=packers.pack_period_month_ranges(summary),
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
