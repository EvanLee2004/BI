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
    "delivery_count", "revenue_gross", "revenue_net", "vat", "system_direct_cost",
    "inhouse_cost", "production_cost", "gross_profit", "gross_margin_pct", "surtax",
    "other_pl", "pretax_profit", "pretax_margin_pct", "orders", "receipts",
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
    }


def session_public(acc: dict | None, *, is_admin_session: bool = False) -> dict:
    import accounts
    if is_admin_session and acc:
        return {
            "account": acc.get("账号"),
            "display": acc.get("显示名") or acc.get("账号"),
            "perm": accounts.PERM_ADMIN,
            "bus": [],
            "profile": accounts.VIEW_FULL,
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
        "profile": accounts.view_profile(acc),
        "is_admin": accounts.is_admin(acc),
        "can_main": accounts.is_main(acc) or accounts.is_admin(acc),
    }
