#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit.budget_manual — 可导航入口（实现见 profit._impl）。"""
from profit._impl import (  # noqa: F401
    build_dept_budget_block,
    build_manual_monthly,
    manual_missing_months,
    manual_for_period,
    build_period,
    _month_num,
    build_budget_block,
)
