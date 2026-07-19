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
from typing import Any

import loaders
import money
import schema

from .constants import *  # noqa: F403
from .adjust import _now


# pure-move funcs from _impl.py

def load_budget(conn: sqlite3.Connection, scope: str = "全公司") -> dict[str, dict]:
    """{年份: {指标: 金额分 或 比率百分数}}。比率≠钱，见 BUDGET_RATE_METRICS。"""
    out: dict[str, dict] = {}
    for 年份, 指标, 金额 in conn.execute(
        "SELECT 年份,指标,金额 FROM manual_预算 WHERE 范围=? AND 指标<>'费用年预算'", (scope,)
    ).fetchall():
        if 年份 is None or 指标 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(指标)] = money.budget_value_from_store(str(指标), 金额)
    return out


def load_dept_budget(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """{年份: {部门: 金额分}}，取 指标='费用年预算' 且 范围≠全公司 的行。"""
    out: dict[str, dict[str, int]] = {}
    for 年份, 范围, 金额 in conn.execute(
        "SELECT 年份,范围,金额 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'"
    ).fetchall():
        if 年份 is None or 范围 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(范围)] = int(金额)
    return out


def list_budget_depts(conn: sqlite3.Connection) -> list[str]:
    """部门费用预算矩阵的行清单：台账里实际出现过的预算归属部门 ∪ 已填过预算的部门（不硬编码）。"""
    depts = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT 预算归属部门 FROM std_费用明细 WHERE 已删除=0 AND 预算归属部门 IS NOT NULL AND TRIM(预算归属部门)<>''"
        )
    }
    depts |= {
        r[0] for r in conn.execute("SELECT DISTINCT 范围 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'")
    }
    return sorted(depts)


def get_budget(conn: sqlite3.Connection, year: str | None = None) -> list[dict]:
    cols = ["年份", "指标", "范围", "金额", "填写时间", "经手人"]
    if year:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_预算 WHERE 年份=? ORDER BY 指标", (str(year),)
        ).fetchall()
    else:
        rows = conn.execute(f"SELECT {','.join(cols)} FROM manual_预算 ORDER BY 年份,指标").fetchall()
    out = [dict(zip(cols, r, strict=False)) for r in rows]
    for d in out:
        if d.get("金额") is not None:
            # 管理端：金额→元；比率→百分数
            d["金额"] = money.budget_value_from_store(str(d.get("指标") or ""), d["金额"])
            if str(d.get("指标") or "") not in BUDGET_RATE_METRICS:
                d["金额"] = money.fen_to_yuan(d["金额"])
    return out


def set_budget(conn: sqlite3.Connection, 年份: str, 指标: str, 金额: float, 经手人: str, 范围: str = "全公司") -> None:
    """写年度预算。金额入参元→分；比率入参百分数→百分位点（绝不用 yuan_to_fen）。"""
    old = conn.execute("SELECT 金额 FROM manual_预算 WHERE 年份=? AND 指标=? AND 范围=?", (年份, 指标, 范围)).fetchone()
    旧值 = old[0] if old else None
    now = _now()
    stored = money.budget_value_to_store(str(指标), 金额)
    conn.execute(
        "INSERT INTO manual_预算历史(时间,经手人,年份,指标,范围,旧值,新值) VALUES(?,?,?,?,?,?,?)",
        (now, 经手人, 年份, 指标, 范围, 旧值, stored),
    )
    conn.execute(
        "INSERT OR REPLACE INTO manual_预算(年份,指标,范围,金额,填写时间,经手人) VALUES(?,?,?,?,?,?)",
        (年份, 指标, 范围, stored, now, 经手人),
    )
    conn.commit()


def latest_run(conn: sqlite3.Connection) -> dict | None:
    """最近一次运行日志（体检状态条数据源）。"""
    row = conn.execute("SELECT 时间,触发方式,结果,体检JSON FROM meta_运行日志 ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    import json as _json

    时间, 触发方式, 结果, 体检JSON = row
    try:
        体检 = _json.loads(体检JSON) if 体检JSON else {}
    except (ValueError, TypeError):
        体检 = {}
    return {"时间": 时间, "触发方式": 触发方式, "结果": 结果, "体检": 体检}


