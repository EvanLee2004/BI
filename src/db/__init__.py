#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db 可导航包（54.4·E）。实现：db._impl（原样搬家）。

子模块仅导航 re-export；本 __init__ 导出 _impl 全部公开与下划线符号，兼容
`from profit import _scan_ledger_issues` 等旧路径。
"""
from __future__ import annotations

import db._impl as _impl

# 显式绑定全部符号（含 _ 前缀）
for _name in dir(_impl):
    if _name.startswith("__") and _name not in ("__all__", "__doc__"):
        continue
    globals()[_name] = getattr(_impl, _name)

del _impl, _name
