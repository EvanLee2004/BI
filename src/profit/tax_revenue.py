#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit.tax_revenue — 可导航入口（实现见 profit._impl）。"""
from profit._impl import (  # noqa: F401
    split_tax,
    compute_revenue_cost,
    _sum_amount_in_period,
    compute_orders,
    compute_receipts,
    compute_name_month_totals,
)
