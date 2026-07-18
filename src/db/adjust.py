#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db.adjust — 可导航入口（实现见 db._impl）。"""
from db._impl import (  # noqa: F401
    _now,
    add_adjustment,
    revoke_adjustment,
    revoke_expired_adjustments,
    rearm_adjustment,
    list_adjustments,
)
