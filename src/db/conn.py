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

# 任务书64·D9：进程内 schema.create_all 只跑一次（按库路径）
_SCHEMA_READY: set[str] = set()

# pure-move funcs from _impl.py

def db_path(cfg: dict, root: Path | None = None) -> Path:
    """看板.db 路径：config.db_path（**相对 data_dir 的文件名/子路径**）或默认 看板.db。

    2.6.3·A2：rel 首段若等于 data_dir 末段 → **明确报错**（不猜、不静默纠正）。
    正确写法：db_path=\"看板.db\"（相对 data_dir）；错误：db_path=\"数据/看板.db\" 会拼成 数据/数据/看板.db。
    """
    rel = cfg.get("db_path", DB_DEFAULT_REL)
    p = Path(rel)
    if p.is_absolute():
        return p
    rel_s = str(rel).replace("\\", "/").strip("/")
    if not rel_s:
        raise ValueError(
            "config.db_path 不能为空；正确写法为相对 data_dir 的路径，例如 \"看板.db\""
        )
    data = loaders.data_dir(cfg, root)
    first = Path(rel_s).parts[0] if Path(rel_s).parts else ""
    data_tail = data.name
    if first and first == data_tail:
        raise ValueError(
            f"config.db_path={rel!r} 首段与 data_dir 末段 {data_tail!r} 重复，"
            f"会拼成影子路径 {data / rel_s}。"
            f"正确写法：db_path 只写相对 data_dir 的部分，例如 \"看板.db\""
            f"（不要写 \"{data_tail}/看板.db\"）"
        )
    return data / rel_s


def connect(cfg: dict, root: Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    """打开看板库。

    readonly=True：URI mode=ro（任务书46·5 读写分离语义——读路径不写盘）。
    只读连接跳过 schema.create_all（避免写库）。
    写连接：schema.create_all 进程内同路径只跑一次（首连标志位）。
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
    key = str(path.resolve())
    if key not in _SCHEMA_READY:
        schema.create_all(conn)
        _SCHEMA_READY.add(key)
    return conn


def connect_readonly(cfg: dict, root: Path | None = None) -> sqlite3.Connection:
    """读连接：mode=ro，禁止写。"""
    return connect(cfg, root, readonly=True)


