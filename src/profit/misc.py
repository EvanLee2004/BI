#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profit.misc — 可导航入口（实现见 profit._impl）。"""
from profit._impl import (  # noqa: F401
    load_manual_safe,
    _scan_dict_source_issues,
    _scan_ledger_issues,
    _scan_future_dates_dict,
    _scan_future_dates_ledger,
    _data_health,
)
