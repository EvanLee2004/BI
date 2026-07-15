#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态 HTML 模板加载器：模块载入时缓存，str.format 填充。禁止热读磁盘。"""
from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "static" / "templates"
_cache: dict[str, str] = {}


def load(rel: str) -> str:
    """读 static/templates/{rel}，模块级缓存一次。"""
    if rel not in _cache:
        _cache[rel] = (_DIR / rel).read_text(encoding="utf-8")
    return _cache[rel]


def fill(rel: str, **kwargs) -> str:
    """load + str.format(**kwargs)。"""
    return load(rel).format(**kwargs)
