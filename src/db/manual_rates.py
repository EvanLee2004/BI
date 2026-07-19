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

import money

from .adjust import _now
from .loaders_std import load_manual


# pure-move funcs from _impl.py

def set_manual(
    conn: sqlite3.Connection, 归属月: str, 项目: str, 金额: float, 经手人: str, 范围: str = "全公司"
) -> None:
    """写手填。范围=全公司 → manual_手填；范围=某 BU → manual_手填BU。均留痕。金额入参元→库内分。"""
    scope = (范围 or "全公司").strip() or "全公司"
    now = _now()
    fen = money.yuan_to_fen(金额)
    if fen is None:
        fen = 0
    if scope == "全公司":
        old = conn.execute("SELECT 金额 FROM manual_手填 WHERE 归属月=? AND 项目=?", (归属月, 项目)).fetchone()
        旧值 = old[0] if old else None
        conn.execute(
            "INSERT INTO manual_历史(时间,经手人,归属月,项目,旧值,新值) VALUES(?,?,?,?,?,?)",
            (now, 经手人, 归属月, 项目, 旧值, fen),
        )
        conn.execute(
            "INSERT OR REPLACE INTO manual_手填(归属月,项目,金额,填写时间,经手人) VALUES(?,?,?,?,?)",
            (归属月, 项目, fen, now, 经手人),
        )
    else:
        old = conn.execute(
            "SELECT 金额 FROM manual_手填BU WHERE 归属月=? AND 范围=? AND 项目=?", (归属月, scope, 项目)
        ).fetchone()
        旧值 = old[0] if old else None
        conn.execute(
            "INSERT INTO manual_历史(时间,经手人,归属月,项目,旧值,新值) VALUES(?,?,?,?,?,?)",
            (now, 经手人, f"{归属月}|{scope}", 项目, 旧值, fen),
        )
        conn.execute(
            "INSERT OR REPLACE INTO manual_手填BU(归属月,范围,项目,金额,填写时间,经手人) VALUES(?,?,?,?,?,?)",
            (归属月, scope, 项目, fen, now, 经手人),
        )
    conn.commit()


def load_manual_scope(cfg: dict, conn: sqlite3.Connection, scope: str) -> dict[str, dict[str, float]]:
    """某 BU 范围手填 → {'YYYY-MM': {项目: 金额元}}。无表/无数据 → {}。"""
    scope = (scope or "").strip()
    if not scope or scope == "全公司":
        return load_manual(cfg, conn)
    try:
        rows = conn.execute("SELECT 归属月,项目,金额 FROM manual_手填BU WHERE 范围=?", (scope,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, float]] = {}
    for 归属月, 项目, 金额 in rows:
        if 归属月 is None or 项目 is None or 金额 is None:
            continue
        out.setdefault(str(归属月), {})[str(项目)] = int(金额)
    return out


def set_alloc_ratio(conn: sqlite3.Connection, month: str, bu: str, pct, user: str) -> None:
    """写/删某月某 BU 的分摊比例（迭代20）。pct=None/空 → 删行（该月该 BU 不分摊）。"""
    month = str(month or "").strip()
    bu = str(bu or "").strip()
    if not month or not bu:
        raise ValueError("归属月与 BU 不能为空")
    if pct is None or pct == "":
        conn.execute("DELETE FROM manual_分摊比例 WHERE 归属月=? AND BU=?", (month, bu))
    else:
        v = float(pct)
        if not (0 <= v <= 100):
            raise ValueError(f"比例须在 0~100：{bu}={pct}")
        now = _now()
        conn.execute(
            "INSERT OR REPLACE INTO manual_分摊比例(归属月,BU,比例,填写时间,经手人) VALUES(?,?,?,?,?)",
            (month, bu, round(v, 1), now, user),
        )
    conn.commit()


def get_alloc_ratios(conn: sqlite3.Connection, month: str) -> dict[str, float]:
    """某月分摊比例 → {BU: 比例%}。无表/无数据 → {}。"""
    try:
        rows = conn.execute(
            "SELECT BU,比例 FROM manual_分摊比例 WHERE 归属月=?", (str(month or "").strip(),)
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(b): float(v) for b, v in rows if b is not None and v is not None}


def load_alloc_ratios(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """全部分摊比例 → {'YYYY-MM': {BU: 比例%}}。无表/无数据 → {}。"""
    try:
        rows = conn.execute("SELECT 归属月,BU,比例 FROM manual_分摊比例").fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, float]] = {}
    for 归属月, b, v in rows:
        if 归属月 is None or b is None or v is None:
            continue
        out.setdefault(str(归属月), {})[str(b)] = float(v)
    return out


def set_detax_rate(conn: sqlite3.Connection, category: str, rate, user: str) -> None:
    """写/删某费用类别的去税率(%)。rate=None/空/0 → 删行（该类别不去税，等价默认）。"""
    category = str(category or "").strip()
    if not category:
        raise ValueError("费用类别不能为空")
    if rate is None or rate == "" or float(rate) == 0:
        conn.execute("DELETE FROM manual_费用去税率 WHERE 费用类别=?", (category,))
    else:
        v = float(rate)
        if not (0 <= v <= 100):
            raise ValueError(f"去税率须在 0~100：{category}={rate}")
        conn.execute(
            "INSERT OR REPLACE INTO manual_费用去税率(费用类别,税率,填写时间,经手人) VALUES(?,?,?,?)",
            (category, round(v, 2), _now(), user),
        )
    conn.commit()


def load_detax_rates(conn: sqlite3.Connection) -> dict[str, float]:
    """全部费用去税率 → {费用类别: 税率%}。无表/无数据 → {}（默认不去税·回归红线中性）。"""
    try:
        rows = conn.execute("SELECT 费用类别,税率 FROM manual_费用去税率").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(c): float(v) for c, v in rows if c is not None and v is not None and float(v) > 0}


def list_detax_categories(conn: sqlite3.Connection, cfg: dict) -> list[dict]:
    """可去税的费用类别清单（陆总按重要性挑房租等填）——台账「预算明细费用类型」细类去重，
    限「对应报表大类」在期间费用白名单内（与利润表口径一致），带全年含税金额参考、按金额降序（大头在前）。
    返回 [{category, amount}]；空细类不列（归「(未分类)」不去税）。用于管理端录入页只读展示，不参与计算。"""
    included = set(cfg.get("expense_categories_included") or [])
    if not included:
        return []
    rows = conn.execute("SELECT 对应报表大类,预算明细费用类型,含税金额 FROM std_费用明细 WHERE 已删除=0").fetchall()
    agg: dict[str, float] = {}
    for big, fine, amt in rows:
        if str(big or "").strip() not in included:
            continue
        fine = str(fine or "").strip()
        if not fine:
            continue
        try:
            agg[fine] = agg.get(fine, 0) + int(amt or 0)
        except (TypeError, ValueError):
            agg.setdefault(fine, 0)
    # 管理端去税页参考金额：元
    out = [{"category": k, "amount": round(money.fen_to_yuan(v), 2)} for k, v in agg.items()]
    out.sort(key=lambda d: (-d["amount"], d["category"]))
    return out


def effective_alloc_month(conn: sqlite3.Connection, month: str) -> tuple[dict[str, float], str | None]:
    """某月**生效**分摊比例（陆总0714：默认沿用最近一次填写月，改了从当月生效）。
    该月自己填过 → (该月比例, 该月)；没填 → 沿用 ≤该月 最近一个填过的月 (其比例, 来源月)；
    从没填过 → ({}, None)。月份键 YYYY-MM 字符串序即时间序。"""
    month = str(month or "").strip()
    own = get_alloc_ratios(conn, month)
    if own:
        return own, month
    raw = load_alloc_ratios(conn)
    prev = sorted(k for k in raw if k < month)
    if not prev:
        return {}, None
    src = prev[-1]
    return dict(raw[src]), src


def effective_alloc_ratios(conn: sqlite3.Connection, year: int, upto_month: int) -> dict[str, dict[str, float]]:
    """当年 1..upto_month 每月的**生效**比例（沿用规则同 effective_alloc_month）。
    供分摊计算用：{'YYYY-MM': {BU: 比例%}}；从没填过任何比例 → {}。"""
    raw = load_alloc_ratios(conn)
    if not raw:
        return {}
    filled = sorted(raw)
    out: dict[str, dict[str, float]] = {}
    for m in range(1, max(1, int(upto_month)) + 1):
        key = f"{int(year):04d}-{m:02d}"
        if key in raw:
            out[key] = dict(raw[key])
            continue
        prev = [k for k in filled if k < key]
        if prev:
            out[key] = dict(raw[prev[-1]])
    return out


def get_manual(conn: sqlite3.Connection, month: str | None = None, 范围: str = "全公司") -> list[dict]:
    """管理端列表。范围=全公司读 manual_手填；否则读 manual_手填BU。金额列返回元。"""
    scope = (范围 or "全公司").strip() or "全公司"
    if scope == "全公司":
        cols = ["归属月", "项目", "金额", "填写时间", "经手人"]
        if month:
            rows = conn.execute(
                f"SELECT {','.join(cols)} FROM manual_手填 WHERE 归属月=? ORDER BY 项目", (month,)
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT {','.join(cols)} FROM manual_手填 ORDER BY 归属月,项目").fetchall()
        out = [dict(zip(cols, r, strict=False)) for r in rows]
    else:
        cols = ["归属月", "项目", "金额", "填写时间", "经手人", "范围"]
        try:
            if month:
                rows = conn.execute(
                    "SELECT 归属月,项目,金额,填写时间,经手人,范围 FROM manual_手填BU "
                    "WHERE 归属月=? AND 范围=? ORDER BY 项目",
                    (month, scope),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT 归属月,项目,金额,填写时间,经手人,范围 FROM manual_手填BU WHERE 范围=? ORDER BY 归属月,项目",
                    (scope,),
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        out = [dict(zip(cols, r, strict=False)) for r in rows]
    for d in out:
        if d.get("金额") is not None:
            d["金额"] = money.fen_to_yuan(d["金额"])
    return out


