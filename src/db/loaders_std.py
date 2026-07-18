#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db.loaders_std — 可导航入口（实现见 db._impl）。"""
from db._impl import (  # noqa: F401
    load_project_detail,
    _fen,
    load_orders,
    load_receipts,
    load_inhouse,
    load_ledger,
    load_manual,
    _s,
)
