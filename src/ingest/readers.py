#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读原始源 → 交给 normalize。刀1 阶段薄封装 loaders（已验证的 openpyxl 读法、绝不 read_only、
按表头找列），后续 P4 智云自动抓数时在这里换实现，normalize 以下不动。"""

from __future__ import annotations

from pathlib import Path

import loaders


def read_project_detail(cfg, root: Path | None = None):
    return loaders.load_project_detail(cfg, root)


def read_orders(cfg, root: Path | None = None):
    return loaders.load_orders(cfg, root)


def read_receipts(cfg, root: Path | None = None):
    return loaders.load_receipts(cfg, root)


def read_inhouse(cfg, root: Path | None = None):
    return loaders.load_inhouse(cfg, root)


def read_ledger(cfg, ledger_year: int, root: Path | None = None):
    return loaders.load_ledger(cfg, str(ledger_year), root)
