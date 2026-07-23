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
    conn: sqlite3.Connection,
    归属月: str,
    项目: str,
    金额: float,
    经手人: str,
    范围: str = "全公司",
    *,
    commit: bool = True,
) -> None:
    """写手填。范围=全公司 → manual_手填；范围=某 BU → manual_手填BU。均留痕。金额入参元→库内分。

    commit=False 时不 conn.commit()，供批量事务由调用方一次提交（任务书63·F-02）。
    """
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
    if commit:
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


def set_alloc_ratio(
    conn: sqlite3.Connection, month: str, bu: str, pct, user: str, *, commit: bool = True
) -> None:
    """写/删某月某 BU 的分摊比例（迭代20）。pct=None/空 → 删行（该月该 BU 不分摊）。

    任务书63·H-04：每次写/删先追加 manual_分摊比例历史（删除记 新值=NULL）。
    commit=False 时不提交，供批量事务。
    """
    month = str(month or "").strip()
    bu = str(bu or "").strip()
    if not month or not bu:
        raise ValueError("归属月与 BU 不能为空")
    now = _now()
    old_row = conn.execute(
        "SELECT 比例 FROM manual_分摊比例 WHERE 归属月=? AND BU=?", (month, bu)
    ).fetchone()
    旧值 = float(old_row[0]) if old_row and old_row[0] is not None else None
    if pct is None or pct == "":
        新值 = None
        conn.execute("DELETE FROM manual_分摊比例 WHERE 归属月=? AND BU=?", (month, bu))
    else:
        v = money.quantize_rate(pct, places=1)
        if not (0 <= v <= 100):
            raise ValueError(f"比例须在 0~100：{bu}={pct}")
        新值 = v
        conn.execute(
            "INSERT OR REPLACE INTO manual_分摊比例(归属月,BU,比例,填写时间,经手人) VALUES(?,?,?,?,?)",
            (month, bu, 新值, now, user),
        )
    conn.execute(
        "INSERT INTO manual_分摊比例历史(时间,经手人,归属月,BU,旧值,新值) VALUES(?,?,?,?,?,?)",
        (now, user, month, bu, 旧值, 新值),
    )
    if commit:
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


def set_detax_rate(
    conn: sqlite3.Connection, category: str, rate, user: str, *, commit: bool = True
) -> None:
    """写/删某费用类别的去税率(%)。rate=None/空/0 → 删行（该类别不去税，等价默认）。

    任务书63·H-04：每次写/删先追加 manual_去税率历史（删除记 新值=NULL）。
    """
    category = str(category or "").strip()
    if not category:
        raise ValueError("费用类别不能为空")
    now = _now()
    old_row = conn.execute(
        "SELECT 税率 FROM manual_费用去税率 WHERE 费用类别=?", (category,)
    ).fetchone()
    旧值 = float(old_row[0]) if old_row and old_row[0] is not None else None
    新值 = None
    if rate is not None and rate != "":
        try:
            zv = money.parse_decimal(rate)
        except ValueError as e:
            raise ValueError(f"去税率须为数字：{category}={rate}") from e
        if zv is not None and zv != 0:
            v = money.quantize_rate(zv, places=2)
            if not (0 <= v <= 100):
                raise ValueError(f"去税率须在 0~100：{category}={rate}")
            新值 = v
    if 新值 is None:
        conn.execute("DELETE FROM manual_费用去税率 WHERE 费用类别=?", (category,))
    else:
        conn.execute(
            "INSERT OR REPLACE INTO manual_费用去税率(费用类别,税率,填写时间,经手人) VALUES(?,?,?,?)",
            (category, 新值, now, user),
        )
    conn.execute(
        "INSERT INTO manual_去税率历史(时间,经手人,费用类别,旧值,新值) VALUES(?,?,?,?,?)",
        (now, user, category, 旧值, 新值),
    )
    if commit:
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


# ---- 2.4.0 两轴模型：公共明细金额覆盖 + 明细精配规则（Stage B 仅数据层，不接线计算）----

_ALLOC_DETAIL_MODES = frozenset({"比例", "金额"})


def set_public_detail_amount_override(
    conn: sqlite3.Connection,
    month: str,
    category: str,
    amount_yuan,
    user: str,
    *,
    commit: bool = True,
) -> None:
    """写/删某月某明细费用类型的金额覆盖（轴①）。amount_yuan=None/空 → 删行（回退台账自动抓）。

    金额入参元 → 库内 INTEGER 分；写删只追加历史。
    """
    month = str(month or "").strip()
    category = str(category or "").strip()
    if not month or not category:
        raise ValueError("归属月与明细费用类型不能为空")
    now = _now()
    old_row = conn.execute(
        "SELECT 金额 FROM manual_公共明细金额覆盖 WHERE 归属月=? AND 明细费用类型=?",
        (month, category),
    ).fetchone()
    旧值 = int(old_row[0]) if old_row and old_row[0] is not None else None
    if amount_yuan is None or amount_yuan == "":
        新值 = None
        conn.execute(
            "DELETE FROM manual_公共明细金额覆盖 WHERE 归属月=? AND 明细费用类型=?",
            (month, category),
        )
    else:
        fen = money.yuan_to_fen(amount_yuan)
        if fen is None:
            raise ValueError(f"金额须为数字：{category}={amount_yuan}")
        if fen < 0:
            raise ValueError(f"金额须 ≥0：{category}={amount_yuan}")
        新值 = int(fen)
        conn.execute(
            "INSERT OR REPLACE INTO manual_公共明细金额覆盖"
            "(归属月,明细费用类型,金额,填写时间,经手人) VALUES(?,?,?,?,?)",
            (month, category, 新值, now, user),
        )
    conn.execute(
        "INSERT INTO manual_公共明细金额覆盖历史"
        "(时间,经手人,归属月,明细费用类型,旧值,新值) VALUES(?,?,?,?,?,?)",
        (now, user, month, category, 旧值, 新值),
    )
    if commit:
        conn.commit()


def get_public_detail_amount_overrides(
    conn: sqlite3.Connection, month: str
) -> dict[str, int]:
    """某月公共明细金额覆盖 → {明细费用类型: 金额分}。无表/无数据 → {}。"""
    try:
        rows = conn.execute(
            "SELECT 明细费用类型,金额 FROM manual_公共明细金额覆盖 WHERE 归属月=?",
            (str(month or "").strip(),),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, int] = {}
    for cat, amt in rows:
        if cat is None or amt is None:
            continue
        out[str(cat)] = int(amt)
    return out


def load_public_detail_amount_overrides(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, int]]:
    """全部公共明细金额覆盖 → {'YYYY-MM': {明细费用类型: 金额分}}。"""
    try:
        rows = conn.execute(
            "SELECT 归属月,明细费用类型,金额 FROM manual_公共明细金额覆盖"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, int]] = {}
    for month, cat, amt in rows:
        if month is None or cat is None or amt is None:
            continue
        out.setdefault(str(month), {})[str(cat)] = int(amt)
    return out


def set_alloc_detail_rule(
    conn: sqlite3.Connection,
    month: str,
    category: str,
    bu: str,
    mode,
    value,
    user: str,
    *,
    commit: bool = True,
) -> None:
    """写/删某月某明细项对某 BU 的精配规则（轴②）。

    mode 须为 '比例' 或 '金额'；value=None/空 → 删行。
    比例：value 0~100（百分数）；金额：value 入参元 → 库内 值=分（REAL 存整分）。
    写删只追加历史。
    """
    month = str(month or "").strip()
    category = str(category or "").strip()
    bu = str(bu or "").strip()
    if not month or not category or not bu:
        raise ValueError("归属月、明细费用类型与 BU 不能为空")
    now = _now()
    old_row = conn.execute(
        "SELECT 模式,值 FROM manual_分摊_明细规则 WHERE 归属月=? AND 明细费用类型=? AND BU=?",
        (month, category, bu),
    ).fetchone()
    旧模式 = str(old_row[0]) if old_row and old_row[0] is not None else None
    旧值 = float(old_row[1]) if old_row and old_row[1] is not None else None

    if value is None or value == "" or mode is None or mode == "":
        新模式, 新值 = None, None
        conn.execute(
            "DELETE FROM manual_分摊_明细规则 WHERE 归属月=? AND 明细费用类型=? AND BU=?",
            (month, category, bu),
        )
    else:
        m = str(mode).strip()
        if m not in _ALLOC_DETAIL_MODES:
            raise ValueError(f"模式须为 比例 或 金额：{m}")
        if m == "比例":
            v = money.quantize_rate(value, places=1)
            if not (0 <= v <= 100):
                raise ValueError(f"比例须在 0~100：{bu}={value}")
            新模式, 新值 = m, v
        else:
            fen = money.yuan_to_fen(value)
            if fen is None:
                raise ValueError(f"金额须为数字：{bu}={value}")
            if fen < 0:
                raise ValueError(f"金额须 ≥0：{bu}={value}")
            新模式, 新值 = m, float(int(fen))
        conn.execute(
            "INSERT OR REPLACE INTO manual_分摊_明细规则"
            "(归属月,明细费用类型,BU,模式,值,填写时间,经手人) VALUES(?,?,?,?,?,?,?)",
            (month, category, bu, 新模式, 新值, now, user),
        )
    conn.execute(
        "INSERT INTO manual_分摊_明细规则历史"
        "(时间,经手人,归属月,明细费用类型,BU,旧模式,旧值,新模式,新值) VALUES(?,?,?,?,?,?,?,?,?)",
        (now, user, month, category, bu, 旧模式, 旧值, 新模式, 新值),
    )
    if commit:
        conn.commit()


def get_alloc_detail_rules(
    conn: sqlite3.Connection, month: str
) -> dict[str, dict[str, dict]]:
    """某月明细精配规则 → {明细费用类型: {BU: {mode, value}}}。

    value：比例模式为百分数 float；金额模式为**元** float（库内分→元读回）。
    """
    try:
        rows = conn.execute(
            "SELECT 明细费用类型,BU,模式,值 FROM manual_分摊_明细规则 WHERE 归属月=?",
            (str(month or "").strip(),),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, dict]] = {}
    for cat, b, mode, val in rows:
        if cat is None or b is None or mode is None or val is None:
            continue
        m = str(mode)
        if m == "金额":
            v: float = float(money.fen_to_yuan(int(val)))
        else:
            v = float(val)
        out.setdefault(str(cat), {})[str(b)] = {"mode": m, "value": v}
    return out


def load_alloc_detail_rules(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, dict[str, dict]]]:
    """全部明细精配 → {'YYYY-MM': {明细: {BU: {mode, value}}}}；金额 value=元。"""
    try:
        rows = conn.execute(
            "SELECT 归属月,明细费用类型,BU,模式,值 FROM manual_分摊_明细规则"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, dict[str, dict]]] = {}
    for month, cat, b, mode, val in rows:
        if month is None or cat is None or b is None or mode is None or val is None:
            continue
        m = str(mode)
        if m == "金额":
            v = float(money.fen_to_yuan(int(val)))
        else:
            v = float(val)
        out.setdefault(str(month), {}).setdefault(str(cat), {})[str(b)] = {
            "mode": m,
            "value": v,
        }
    return out


def _sum_rule_values(
    rules_for_item: dict[str, dict],
    *,
    mode: str,
) -> float:
    """累加各 BU 规则值；顺带做单行范围校验。"""
    total = 0.0
    for bu, r in rules_for_item.items():
        v = float((r or {}).get("value") or 0)
        if mode == "比例" and not (0 <= v <= 100):
            raise ValueError(f"比例须在 0~100：{bu}={v}")
        if mode == "金额" and v < 0:
            raise ValueError(f"金额须 ≥0：{bu}={v}")
        total += v
    return total


def validate_alloc_detail_item_rules(
    rules_for_item: dict[str, dict],
    *,
    item_amount_yuan: float | None = None,
) -> None:
    """校验同一明细项下各 BU 精配：比例合计 ≤100；金额合计 ≤ 本项金额（若给定）。

    rules_for_item: {BU: {mode, value}}，value 与 get_alloc_detail_rules 同形（比例% / 金额元）。
    超限 → ValueError。混合模式（同项既有比例又有金额）→ ValueError。
    """
    if not rules_for_item:
        return
    modes = {str((r or {}).get("mode") or "") for r in rules_for_item.values()}
    modes.discard("")
    if not modes:
        return
    if len(modes) > 1:
        raise ValueError("同一明细项不可混合「比例」与「金额」模式")
    mode = next(iter(modes))
    if mode not in _ALLOC_DETAIL_MODES:
        raise ValueError(f"未知模式：{mode}")
    total = _sum_rule_values(rules_for_item, mode=mode)
    if mode == "比例" and total > 100.0 + 1e-9:
        raise ValueError(f"比例合计 {total:.1f}% 超过 100%")
    if (
        mode == "金额"
        and item_amount_yuan is not None
        and total > float(item_amount_yuan) + 1e-9
    ):
        raise ValueError(
            f"金额合计 {total:.2f} 超过本项金额 {float(item_amount_yuan):.2f}"
        )


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


