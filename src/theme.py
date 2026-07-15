#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题 CSS：唯一源 = static/css/theme.css（v1.5+ 清理双源）。

get_css() 供测试/脚本读取；生产页面通过 <link href="/static/css/theme.css"> 加载。
"""
from __future__ import annotations

from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "css" / "theme.css"


def get_css() -> str:
    """读 static/css/theme.css 全文。"""
    return _CSS_PATH.read_text(encoding="utf-8")
