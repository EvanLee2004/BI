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
from typing import Any


from .constants import LEDGER_STD_COLS

# pure-move funcs from _impl.py

def load_project_detail(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, str]]:
    c = cfg["columns"]
    rows = conn.execute(
        "SELECT 订单号,客户,业务线,销售,整单交付日期,交付额,项目成本 FROM std_收入明细 WHERE 已删除=0 ORDER BY id"
    ).fetchall()
    out = []
    for 订单号, 客户, 业务线, 销售, 交付日期, 交付额, 项目成本 in rows:
        out.append(
            {
                "订单号": _s(订单号),
                "客户": _s(客户),
                "业务线": _s(业务线),
                "销售": _s(销售),
                c["project_delivery_date"]: _s(交付日期),
                # 金额：库内分；强制 int（SQLite 常返回 float，as_fen(float) 会误当元再×100）
                c["project_revenue"]: _fen(交付额),
                c["project_cost"]: _fen(项目成本),
            }
        )
    return out


def _fen(v: Any) -> int:
    """库内金额读出为 int 分；None → 0。"""
    if v is None:
        return 0
    return int(v)


def load_orders(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    try:
        rows = conn.execute(
            "SELECT 下单日期,下单预估额,订单号,部门,销售,客户 FROM std_下单 WHERE 已删除=0 ORDER BY id"
        ).fetchall()
        return [
            {
                c["order_date"]: _s(d),
                c["order_amount"]: _fen(a),
                "订单号": _s(o),
                "部门": _s(dep),
                "销售": _s(sal),
                "客户": _s(cu),
            }
            for d, a, o, dep, sal, cu in rows
        ]
    except sqlite3.OperationalError:
        # 极老库缺「客户」列：降级不选该列（非吞所有异常）
        rows = conn.execute(
            "SELECT 下单日期,下单预估额,订单号,部门,销售 FROM std_下单 WHERE 已删除=0 ORDER BY id"
        ).fetchall()
        return [
            {
                c["order_date"]: _s(d),
                c["order_amount"]: _fen(a),
                "订单号": _s(o),
                "部门": _s(dep),
                "销售": _s(sal),
            }
            for d, a, o, dep, sal in rows
        ]


def load_receipts(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute("SELECT 到账日期,到账金额,回款ID,客户,销售 FROM std_回款 WHERE 已删除=0 ORDER BY id").fetchall()
    return [
        {
            c["receipt_date"]: _s(d),
            c["receipt_amount"]: _fen(a),
            "回款记录ID": _s(rid),
            "客户": _s(cu),
            "销售": _s(sal),
        }
        for d, a, rid, cu, sal in rows
    ]


def load_inhouse(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    # 译员姓名列存量库可能尚未补齐：缺列时降级不选（_ensure_columns 后应始终有）
    try:
        rows = conn.execute(
            "SELECT 任务提交日期,结算金额,译员类型,任务ID,译员姓名,销售 FROM std_内部译员 WHERE 已删除=0 ORDER BY id"
        ).fetchall()
        return [
            {
                c["inhouse_date"]: _s(d),
                c["inhouse_amount"]: _fen(a),
                c["inhouse_type"]: _s(t),
                "任务明细ID": _s(tid),
                "译员姓名": _s(nm),
                "销售": _s(sal),
            }
            for d, a, t, tid, nm, sal in rows
        ]
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT 任务提交日期,结算金额,译员类型,任务ID,销售 FROM std_内部译员 WHERE 已删除=0 ORDER BY id"
        ).fetchall()
        return [
            {
                c["inhouse_date"]: _s(d),
                c["inhouse_amount"]: _fen(a),
                c["inhouse_type"]: _s(t),
                "任务明细ID": _s(tid),
                "销售": _s(sal),
            }
            for d, a, t, tid, sal in rows
        ]


def load_ledger(cfg: dict, conn: sqlite3.Connection) -> tuple[list, list[tuple]]:
    """返回 (表头行, 数据行)，与 loaders.load_ledger 同形。含税金额列返回元 float/None。
    逐行原样（含全空行）按 id 顺序返回，保证行数与旧读法一致（体检面板行数回归红线）。"""
    header = list(LEDGER_STD_COLS)
    rows = conn.execute(
        "SELECT 收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型,预算归属部门 FROM std_费用明细 WHERE 已删除=0 ORDER BY id"
    ).fetchall()
    # 文本列原样；金额列强制 int 分（None 保持 None，空行语义）
    body: list[tuple] = []
    for r in rows:
        amt = r[2]
        if amt is not None:
            amt = int(amt)
        body.append((r[0], r[1], amt, r[3], r[4], r[5], r[6]))
    return header, body


def load_manual(cfg: dict, conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for 归属月, 项目, 金额 in conn.execute("SELECT 归属月,项目,金额 FROM manual_手填").fetchall():
        if 归属月 is None or 项目 is None or 金额 is None:
            continue
        out.setdefault(str(归属月), {})[str(项目)] = int(金额)
    return out


def _s(v: Any) -> str:
    """标准表文本列读回：None→""（与旧 loaders 把空单元格转成 "" 一致）。"""
    return "" if v is None else str(v)


