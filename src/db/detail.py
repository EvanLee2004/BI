#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db.detail — 可导航入口（实现见 db._impl）。"""
from db._impl import (  # noqa: F401
    detail_col_kind,
    detail_columns_meta,
    _detail_display_columns,
    _parse_filters_arg,
    _build_column_filters,
    adjustable_fields,
    _detail_base_where,
    query_detail,
    query_detail_distinct,
)
