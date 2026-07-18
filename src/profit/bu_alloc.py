#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit.bu_alloc — 可导航入口（实现见 profit._impl）。"""
from profit._impl import (  # noqa: F401
    filter_rows_by_sales,
    compute_unassigned_orders_by_period,
    normalize_profit_center,
    scan_unknown_profit_centers,
    unknown_pc_warnings,
    filter_ledger_rows_by_pc,
    build_bu_summary,
    apply_public_expense_allocation,
    _merge_alloc_into_period,
    _alloc_cats_for_range,
    apply_public_expense_allocation_monthly,
    alloc_amounts_by_period,
    apply_alloc_to_pc_view,
)
