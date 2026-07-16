#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务书46·阶段4：配置即数据引擎（口径配置缓存 + 版本 + 不变量校验）。

默认配置由现硬编码忠实导出，保证 golden/红线零变化。
"""

from __future__ import annotations

import json
import sqlite3
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

# 首批迁入键
DEFAULT_KEYS = (
    "报表大类白名单",
    "费用细类到大类映射",
    "利润表行结构",
    "手填项清单",
    "去税类别白名单",
)

_CACHE: dict[str, Any] = {"ver": 0, "data": {}, "loaded_at": 0.0}


def default_config_from_hardcoded(cfg: dict | None = None) -> dict[str, Any]:
    """从现 config / 代码硬编码导出默认口径（忠实、不改语义）。"""
    cfg = cfg or {}
    cats = list(cfg.get("expense_report_categories") or cfg.get("报表大类") or [])
    if not cats:
        cats = ["工资", "管理费用", "市场费用", "财务费用", "研发费用", "固定运营费用", "其他", "税费"]
    return {
        "报表大类白名单": cats,
        "费用细类到大类映射": dict(cfg.get("fine_to_cat") or cfg.get("费用细类到大类映射") or {}),
        "利润表行结构": list(cfg.get("pl_rows") or []),
        "手填项清单": list(cfg.get("manual_items") or []),
        "去税类别白名单": list(cfg.get("detax_categories") or []),
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cfg_口径配置 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            键 TEXT NOT NULL,
            值JSON TEXT NOT NULL,
            版本 INTEGER NOT NULL DEFAULT 1,
            生效时间 TEXT,
            操作人 TEXT,
            已回滚 INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cfg_key_ver ON cfg_口径配置(键, 版本)")
    conn.commit()


def seed_if_empty(conn: sqlite3.Connection, cfg: dict | None = None, operator: str = "system") -> int:
    """空表时写入默认配置；返回写入条数。"""
    ensure_schema(conn)
    n = conn.execute("SELECT COUNT(*) FROM cfg_口径配置 WHERE 已回滚=0").fetchone()[0]
    if n:
        return 0
    defaults = default_config_from_hardcoded(cfg)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for k, v in defaults.items():
        conn.execute(
            "INSERT INTO cfg_口径配置(键,值JSON,版本,生效时间,操作人) VALUES(?,?,1,?,?)",
            (k, json.dumps(v, ensure_ascii=False), now, operator),
        )
    conn.commit()
    _CACHE["ver"] = 0
    return len(defaults)


def load_all(conn: sqlite3.Connection, *, use_cache: bool = True) -> dict[str, Any]:
    """读当前有效配置（每键最高版本且未回滚）。"""
    ensure_schema(conn)
    if use_cache and _CACHE["data"] and _CACHE["ver"] > 0:
        return deepcopy(_CACHE["data"])
    rows = conn.execute(
        """
        SELECT 键, 值JSON, 版本 FROM cfg_口径配置
        WHERE 已回滚=0 AND id IN (
            SELECT MAX(id) FROM cfg_口径配置 WHERE 已回滚=0 GROUP BY 键
        )
        """
    ).fetchall()
    out: dict[str, Any] = {}
    max_ver = 0
    for k, raw, ver in rows:
        try:
            out[k] = json.loads(raw)
        except (TypeError, ValueError):
            out[k] = raw
        max_ver = max(max_ver, int(ver or 0))
    if not out:
        out = default_config_from_hardcoded()
    _CACHE["data"] = deepcopy(out)
    _CACHE["ver"] = max_ver or 1
    _CACHE["loaded_at"] = time.time()
    return deepcopy(out)


def validate_invariants(data: dict[str, Any]) -> list[str]:
    """保存前不变量：白名单无重复、映射无悬空、分组合计约束（可扩展）。返回错误列表，空=通过。"""
    errs: list[str] = []
    cats = data.get("报表大类白名单") or []
    if not isinstance(cats, list):
        errs.append("报表大类白名单须为列表")
    else:
        if len(cats) != len(set(map(str, cats))):
            errs.append("报表大类白名单有重复")
    mapping = data.get("费用细类到大类映射") or {}
    if mapping and not isinstance(mapping, dict):
        errs.append("费用细类到大类映射须为对象")
    elif isinstance(mapping, dict) and cats:
        cat_set = set(map(str, cats))
        for fine, cat in mapping.items():
            if str(cat) not in cat_set:
                errs.append(f"映射悬空：细类 {fine} → 大类 {cat} 不在白名单")
    return errs


def save_config(
    conn: sqlite3.Connection,
    key: str,
    value: Any,
    *,
    operator: str = "",
    full: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    """写入新版本。先校验不变量（可传 full 做全集校验）。返回 (新版本, 错误列表)。"""
    ensure_schema(conn)
    cur = load_all(conn, use_cache=False)
    cur[key] = value
    check = full if full is not None else cur
    errs = validate_invariants(check)
    if errs:
        return 0, errs
    row = conn.execute(
        "SELECT COALESCE(MAX(版本),0) FROM cfg_口径配置 WHERE 键=?", (key,)
    ).fetchone()
    ver = int(row[0] or 0) + 1
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO cfg_口径配置(键,值JSON,版本,生效时间,操作人) VALUES(?,?,?,?,?)",
        (key, json.dumps(value, ensure_ascii=False), ver, now, operator),
    )
    conn.commit()
    _CACHE["ver"] = 0
    _CACHE["data"] = {}
    return ver, []


def rollback_key(conn: sqlite3.Connection, key: str, to_version: int, *, operator: str = "") -> bool:
    """回滚到历史版本：复制该版本为新行（版本+1），不物理删。"""
    ensure_schema(conn)
    row = conn.execute(
        "SELECT 值JSON FROM cfg_口径配置 WHERE 键=? AND 版本=? AND 已回滚=0 ORDER BY id DESC LIMIT 1",
        (key, to_version),
    ).fetchone()
    if not row:
        return False
    val = json.loads(row[0])
    ver, errs = save_config(conn, key, val, operator=operator or "rollback")
    return ver > 0 and not errs


def invalidate_cache() -> None:
    _CACHE["ver"] = 0
    _CACHE["data"] = {}
