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

# pure-move funcs from _impl.py

def _now() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_adjustment(
    conn: sqlite3.Connection,
    经手人: str,
    目标表: str,
    定位键: str,
    字段: str,
    新值: str,
    原因: str = "",
    类型: str = "改值",
) -> int:
    """新增一条调整记录（状态=生效）。原值由服务端从库取。目标表/字段严格白名单（防注入）。
    定位键护栏：匹配 0 行拒（键不存在）、匹配多行拒（内容完全相同的重复行，改一条会波及全部——
    真实台账已实测有撞车行；R2 raw 批次层给行级定位后放开）。"""
    import schema

    if 目标表 not in schema.STD_TABLE_NAMES:
        raise ValueError(f"未知目标表：{目标表}")
    if 类型 not in ("改值", "剔除"):
        raise ValueError(f"未知类型：{类型}")
    matches = conn.execute(f"SELECT COUNT(*) FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()[0]
    if matches == 0:
        raise ValueError(f"定位键在 {目标表} 中不存在（或已删除）：{定位键}")
    if matches > 1:
        raise ValueError(
            f"该行与另外 {matches - 1} 行内容完全相同（定位键重复），暂不支持调整/剔除——"
            f"改一条会同时改动全部相同行。请先在源表里让这些行可区分（如备注加字），或等行级定位（R2）上线。"
        )
    原值 = ""
    新值_store = str(新值)
    if 类型 == "改值":
        if 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
            raise ValueError(f"字段不可调整：{目标表}.{字段}")
        原值_raw = conn.execute(f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()[0]
        # 金额列：原值/新值库内均存**分**文本（管理端录入元→此处转分）
        if money.is_amount_field(字段):
            原值 = "" if 原值_raw is None else str(int(原值_raw))
            fen_new = money.yuan_to_fen(新值)
            新值_store = "" if fen_new is None else str(int(fen_new))
        else:
            原值 = "" if 原值_raw is None else str(原值_raw)
    cur = conn.execute(
        "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
        " VALUES(?,?,?,?,?,?,?,?,?, '生效')",
        (_now(), 经手人, 目标表, 定位键, 字段 or "", 原值, 新值_store, 原因, 类型),
    )
    conn.commit()
    return cur.lastrowid


def revoke_adjustment(conn: sqlite3.Connection, adj_id: int) -> bool:
    cur = conn.execute("UPDATE adj_调整记录 SET 状态='已撤销' WHERE id=? AND 状态!='已撤销'", (adj_id,))
    conn.commit()
    return cur.rowcount > 0


def revoke_expired_adjustments(conn: sqlite3.Connection) -> int:
    """批量撤销全部「过期疑似」= 认可源头新值（页面本就在用新值，这里只是确认事实、清掉黄灯）。
    只允许这个方向批量——批量"坚持我的数"会把报警机制废掉，故意不提供。返回撤销条数。"""
    cur = conn.execute("UPDATE adj_调整记录 SET 状态='已撤销' WHERE 状态='过期疑似'")
    conn.commit()
    return cur.rowcount


def rearm_adjustment(conn: sqlite3.Connection, adj_id: int) -> None:
    """坚持我的数：把一条「过期疑似」的改值调整重新生效——用源头当前值刷新「原值」，
    下轮重放即重新套用「新值」。仅限逐条（见 revoke_expired_adjustments 注释）。"""
    import schema

    row = conn.execute("SELECT 目标表,定位键,字段,类型,状态 FROM adj_调整记录 WHERE id=?", (adj_id,)).fetchone()
    if not row:
        raise ValueError(f"调整不存在：id={adj_id}")
    目标表, 定位键, 字段, 类型, 状态 = row
    if 状态 != "过期疑似":
        raise ValueError("仅「过期疑似」的调整可坚持（生效中无需处理，已撤销请重新添加）")
    if 类型 != "改值":
        raise ValueError("仅「改值」类调整可坚持（剔除类过期疑似=同键重复行，请人工处理）")
    if 目标表 not in schema.STD_TABLE_NAMES or 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
        raise ValueError(f"字段不可调整：{目标表}.{字段}")
    cur = conn.execute(f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()
    if cur is None:
        raise ValueError("源头行已不存在，无法坚持——只能撤销该调整")
    if money.is_amount_field(字段):
        源头现值 = "" if cur[0] is None else str(int(cur[0]))  # 分
    else:
        源头现值 = "" if cur[0] is None else str(cur[0])
    conn.execute("UPDATE adj_调整记录 SET 原值=?, 状态='生效' WHERE id=?", (源头现值, adj_id))
    conn.commit()


def list_adjustments(conn: sqlite3.Connection) -> list[dict]:
    """调整列表。金额字段的 原值/新值 库内为分文本 → 返回**元**字符串（与改造前管理端元/元一致）。"""
    cols = ["id", "创建时间", "经手人", "目标表", "定位键", "字段", "原值", "新值", "原因", "类型", "状态"]
    rows = conn.execute(f"SELECT {','.join(cols)} FROM adj_调整记录 ORDER BY id DESC").fetchall()
    out = [dict(zip(cols, r, strict=False)) for r in rows]
    for d in out:
        if not money.is_amount_field(str(d.get("字段") or "")):
            continue
        for k in ("原值", "新值"):
            raw = d.get(k)
            if raw is None or str(raw).strip() == "":
                continue
            s = str(raw).strip()
            try:
                if "." in s or "e" in s.lower():
                    # 未迁移的元文本：原样（已是元）
                    d[k] = s
                else:
                    d[k] = money.fen_to_yuan_str(int(s))
            except (ValueError, TypeError):
                pass
    return out


