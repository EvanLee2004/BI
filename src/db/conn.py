#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db.conn — 可导航入口（实现见 db._impl）。"""
from db._impl import (  # noqa: F401
    db_path,
    connect,
    connect_readonly,
)
