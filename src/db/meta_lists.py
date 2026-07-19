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
from .misc import latest_run


# pure-move funcs from _impl.py

def list_order_depts(conn: sqlite3.Connection) -> list[str]:
    """下单表里实际出现过的部门（非空去重，异常处理「下单未填部门」归类下拉用，不硬编码）。"""
    return sorted(
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT 部门 FROM std_下单 WHERE 已删除=0 AND 部门 IS NOT NULL AND TRIM(部门)<>''"
        )
    )


def list_salespeople(conn: sqlite3.Connection) -> list[dict]:
    """三源「销售」去重汇总（管理端 BU 拖拽归属池）。
    A2：剔除 std_内部译员——该表「销售」按任务映射、语义不可信，不许污染 BU 归属候选池。
    返回 [{"name": 销售名, "rows": 合计行数}, …] 按行数降序、同名序。
    空/纯空白不算；名字 trim 后聚合。"""
    sql = """
    SELECT TRIM(销售) AS n, COUNT(*) AS c FROM (
      SELECT 销售 FROM std_收入明细 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
      UNION ALL
      SELECT 销售 FROM std_下单 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
      UNION ALL
      SELECT 销售 FROM std_回款 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
    ) GROUP BY TRIM(销售) ORDER BY c DESC, n COLLATE NOCASE
    """
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.OperationalError:
        # 极老库缺某表/列：降级空池，不炸管理端
        return []
    return [{"name": r[0], "rows": int(r[1])} for r in rows if r[0]]


def order_stats_by_sales(conn: sqlite3.Connection, year: int | str) -> dict[str, dict]:
    """当年（按归属月）各销售的下单笔数+下单金额（A1 归属页参考信息用；服务端算好、前端零运算）。
    返回 {销售名(TRIM): {"count": 笔数, "amount": 金额}}。空/纯空白销售不计。"""
    like = f"{year}-%"
    try:
        rows = conn.execute(
            "SELECT TRIM(销售) n, COUNT(*), COALESCE(SUM(下单预估额),0) FROM std_下单 "
            "WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>'' AND 归属月 LIKE ? "
            "GROUP BY TRIM(销售)",
            (like,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    # 金额分（显示走 core._unassigned_wan / fmt_wan）
    return {r[0]: {"count": int(r[1]), "amount": int(r[2] or 0)} for r in rows if r[0]}


def log_config_change(conn: sqlite3.Connection, 操作账号: str, 类别: str, 摘要: str) -> None:
    """追加一条配置变更摘要（人读文本）。摘要绝不含密码等敏感值（调用方负责脱敏）。"""
    if not str(摘要 or "").strip():
        return
    conn.execute(
        "INSERT INTO manual_配置变更(时间,操作账号,类别,摘要) VALUES(?,?,?,?)",
        (_now(), str(操作账号 or ""), str(类别 or ""), str(摘要)),
    )
    conn.commit()


def list_config_changes(conn: sqlite3.Connection, category: str | None = None, limit: int = 200) -> list[dict]:
    """配置变更记录（倒序，最近 limit 条；可按类别筛）。管理端「操作记录」页数据源。"""
    cols = ["id", "时间", "操作账号", "类别", "摘要"]
    limit = max(1, min(1000, int(limit)))
    if category:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_配置变更 WHERE 类别=? ORDER BY id DESC LIMIT ?", (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_配置变更 ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(zip(cols, r, strict=False)) for r in rows]


def exceptions_summary(conn: sqlite3.Connection) -> dict:
    """异常处理中心「总览」计数（新增一类异常=这里加一个键+前端注册一张卡）。
    体检黄红/警不在此（运行信号留在顶栏体检条，总览只引用 /api/health）。"""
    n_dept = conn.execute(f"SELECT COUNT(*) FROM std_下单 WHERE 已删除=0 AND {UNFILLED_DEPT_WHERE}").fetchone()[0]
    n_uc = conn.execute(f"SELECT COUNT(*) FROM std_费用明细 WHERE 已删除=0 AND {UNCLASSIFIED_WHERE}").fetchone()[0]
    n_exp = conn.execute("SELECT COUNT(*) FROM adj_调整记录 WHERE 状态='过期疑似'").fetchone()[0]
    run = latest_run(conn) or {}
    n_missing = int(((run.get("体检") or {}).get("adjust") or {}).get("missing", 0) or 0)
    return {
        "order_unfilled_dept": n_dept,
        "expense_unclassified": n_uc,
        "adjust_expired": n_exp,
        "adjust_missing": n_missing,
    }


def audit_duplicate_locators(conn: sqlite3.Connection) -> dict:
    """审计各 std 表「定位键」重复（内容完全相同 → 同哈希）。

    任务书33·A4 约定行为（已实现、本函数只报告）：
    - **写调整**（add_adjustment）：命中 >1 行 → **拒绝**，不静默改多行；
    - **重放**（apply_adjustments）：命中 >1 行 → **过期疑似**、不套用，体检黄。
    返回 {表名: {定位键: 行数}, …} 仅含 count≥2 的键；无重复 → {}。
    """
    out: dict[str, dict[str, int]] = {}
    for table in schema.STD_TABLE_NAMES:
        try:
            rows = conn.execute(
                f"SELECT 定位键, COUNT(*) c FROM {table} WHERE 已删除=0 AND 定位键 IS NOT NULL AND TRIM(定位键)<>'' "
                f"GROUP BY 定位键 HAVING c>1"
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        if rows:
            out[table] = {str(k): int(c) for k, c in rows}
    return out


def pragma_quick_check(conn: sqlite3.Connection) -> dict:
    """PRAGMA quick_check → {ok: bool, detail: str}。异常 → 体检红。"""
    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
        msgs = [str(r[0]) for r in rows if r and r[0] is not None]
        ok = len(msgs) == 1 and msgs[0].lower() == "ok"
        return {"ok": ok, "detail": "; ".join(msgs) if msgs else "empty"}
    except sqlite3.Error as e:
        return {"ok": False, "detail": f"quick_check failed: {e}"}


