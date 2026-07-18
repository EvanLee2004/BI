#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db.manual_rates — 可导航入口（实现见 db._impl）。"""
from db._impl import (  # noqa: F401
    set_manual,
    load_manual_scope,
    set_alloc_ratio,
    get_alloc_ratios,
    set_detax_rate,
)
