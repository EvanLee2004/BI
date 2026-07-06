#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logo 读成 base64 内嵌，保持 HTML 自包含、可单独发送。"""
from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_logo_base64(cfg: dict) -> str:
    rel = cfg["logo"]["rel"]
    # 先找仓库内 docs/Logo.png（部署机拷走整个文件夹就有），找不到再按 config 往上翻（本机开发环境）
    p = ROOT / "docs" / "Logo.png"
    if not p.exists():
        p = ROOT.parents[cfg["logo"]["parents_up"]] / rel
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
