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
    # 周期 → 已渲染 KPI 卡 HTML（显示串）
    body_by_period: dict[str, str] = Field(default_factory=dict)


class TrendVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    svg_html: str = ""  # 后端 SVG


class PLTableVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_by_period: dict[str, str] = Field(default_factory=dict)
    pl_tag: str = ""


class ExpenseVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    body_by_period: dict[str, str] = Field(default_factory=dict)
    trend_html: str = ""  # 费用面积图 SVG 卡


class RankingsVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    rankings_view: dict[str, Any] = Field(default_factory=dict)
    rankings_monthly_data: dict[str, Any] = Field(default_factory=dict)
    profit_rank_body: dict[str, str] = Field(default_factory=dict)


class ReceiptsVM(BaseModel):
    model_config = ConfigDict(extra="allow")
    receipts_html: str = ""
    receipts_budget: str = ""


class LedgerVM(BaseModel):
    """明细白名单元数据（行数据仍走 /api/detail）。"""
    model_config = ConfigDict(extra="allow")
    columns: list[str] = Field(default_factory=list)
    note: str = "行数据见 /api/detail?table=费用明细"


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
    daily_html: str = ""
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
    daily_html: str = ""
    numbers: dict[str, Any] = Field(default_factory=dict)


def build_cockpit_vm(summary: dict, cfg: dict | None = None) -> CockpitVM:
    """从 summary 构建整体页 VM（复用 build_cockpit_views，零重算金额）。"""
    import api_v1
    import db

    views = api_v1.build_cockpit_views(summary, cfg)
    numbers = api_v1.extract_numbers(summary)
    return CockpitVM(
        year_key=views.get("year_key") or "",
        period_keys=list(views.get("period_keys") or []),
        kpi=KpiCardsVM(
            year_key=views.get("year_key") or "",
            period_keys=list(views.get("period_keys") or []),
            body_by_period=dict(views.get("kpi_body") or {}),
        ),
        trend=TrendVM(svg_html=views.get("trend_html") or ""),
        pl=PLTableVM(body_by_period=dict(views.get("pl_body") or {})),
        expense=ExpenseVM(
            body_by_period=dict(views.get("donut_body") or {}),
            trend_html=views.get("expense_trend_html") or "",
        ),
        rankings=RankingsVM(
            rankings_view=dict(views.get("rankings_view") or {}),
            rankings_monthly_data=dict(views.get("rankings_monthly_data") or {}),
            profit_rank_body=dict(views.get("profit_rank_body") or {}),
        ),
        receipts=ReceiptsVM(receipts_budget=views.get("receipts_budget") or ""),
        ledger=LedgerVM(columns=list(db.VIEW_EXPENSE_COLUMNS)),
        period_bar=views.get("period_bar") or "",
        daily_html=views.get("daily_html") or "",
        numbers=numbers,
    )


def build_bu_vm(bu_name: str, summary: dict, cfg: dict | None = None) -> BUPageVM:
    import api_v1
    import db

    views = api_v1.build_bu_cockpit_views(bu_name, summary, cfg)
    numbers = api_v1.extract_numbers(summary)
    return BUPageVM(
        bu_name=bu_name or views.get("bu_name") or "",
        year_key=views.get("year_key") or "",
        period_keys=list(views.get("period_keys") or []),
        kpi=KpiCardsVM(
            year_key=views.get("year_key") or "",
            period_keys=list(views.get("period_keys") or []),
            body_by_period=dict(views.get("kpi_body") or {}),
        ),
        trend=TrendVM(svg_html=views.get("trend_html") or ""),
        pl=PLTableVM(
            body_by_period=dict(views.get("pl_body") or {}),
            pl_tag=views.get("pl_tag") or "",
        ),
        expense=ExpenseVM(
            body_by_period=dict(views.get("donut_body") or {}),
            trend_html=views.get("expense_trend_html") or "",
        ),
        rankings=RankingsVM(
            rankings_view=dict(views.get("rankings_view") or {}),
            rankings_monthly_data=dict(views.get("rankings_monthly_data") or {}),
            profit_rank_body=dict(views.get("profit_rank_body") or {}),
        ),
        receipts=ReceiptsVM(receipts_html=views.get("receipts_html") or ""),
        ledger=LedgerVM(columns=list(db.VIEW_EXPENSE_COLUMNS_BU)),
        period_bar=views.get("period_bar") or "",
        daily_html=views.get("daily_html") or "",
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
