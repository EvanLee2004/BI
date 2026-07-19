#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db._impl 原 db.py 正文（54.4·E）。看板.db 访问层：连接、建表、读标准表/手填表。

设计要点：
- 读回层**刻意返回与旧 loaders 完全相同的结构**，让 profit/columns/periods 原样计算，守刀1回归红线：
  * 智云四源 → list[dict]，键=config.columns 里的源列名（如「整单交付日期」「交付额/本币」）；
  * 收单台账 → (表头行, 数据行)，与 loaders.load_ledger 同形（逐行原样、含空行，保证行数一致）；
  * 手填 → {'YYYY-MM': {项目: 金额float}}，与 loaders.load_manual 同形。
- 金额库内 INTEGER 分（任务书33·A3）；读回转元 float 交给 profit/fmt；写入侧元→分。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import loaders
import schema

from .constants import DB_DEFAULT_REL, _BUSY_TIMEOUT_MS

# pure-move funcs from _impl.py

def db_path(cfg: dict, root: Path | None = None) -> Path:
    """看板.db 路径：config.db_path（相对数据目录）或默认 数据/看板.db。"""
    rel = cfg.get("db_path", DB_DEFAULT_REL)
    p = Path(rel)
    if p.is_absolute():
        return p
    return loaders.data_dir(cfg, root) / rel


def connect(cfg: dict, root: Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    """打开看板库。

    readonly=True：URI mode=ro（任务书46·5 读写分离语义——读路径不写盘）。
    只读连接跳过 schema.create_all（避免写库）。
    """
    path = db_path(cfg, root)
    if readonly:
        # 文件必须已存在；URI mode=ro（绝对路径，兼容中文路径）
        p = path.resolve()
        if not p.is_file():
            raise FileNotFoundError(f"只读打开失败，库不存在：{p}")
        uri = p.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=_BUSY_TIMEOUT_MS / 1000.0)
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        return conn
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：更新线程与请求线程可共用连接模式（各自仍应独立 connect）
    conn = sqlite3.connect(str(path), timeout=_BUSY_TIMEOUT_MS / 1000.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    schema.create_all(conn)
    return conn


def connect_readonly(cfg: dict, root: Path | None = None) -> sqlite3.Connection:
    """读连接：mode=ro，禁止写。"""
    return connect(cfg, root, readonly=True)


