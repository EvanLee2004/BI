#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金额整数分（任务书33·A3）。

进料口元值 → Decimal 四舍五入到分（ROUND_HALF_UP）→ 库内 INTEGER 分。
算账/展示读回：分 → 元（float，供既有 profit/fmt 路径）；禁止 float×100。
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# 标准表金额列（存分）
STD_MONEY_COLS: dict[str, tuple[str, ...]] = {
    "std_收入明细": ("交付额", "项目成本"),
    "std_下单": ("下单预估额",),
    "std_回款": ("到账金额",),
    "std_内部译员": ("结算金额",),
    "std_费用明细": ("含税金额",),
}

# 人工表金额列（存分；比例/税率仍是百分数 REAL 不动）
MANUAL_MONEY_TABLES: dict[str, tuple[str, ...]] = {
    "manual_手填": ("金额",),
    "manual_手填BU": ("金额",),
    "manual_历史": ("旧值", "新值"),
    "manual_预算": ("金额",),
    "manual_预算历史": ("旧值", "新值"),
}

# 调整记录改值：字段名属于金额时 原值/新值 按元文本存，套用时转分
AMOUNT_FIELD_NAMES = frozenset(
    {
        "交付额",
        "项目成本",
        "下单预估额",
        "到账金额",
        "结算金额",
        "含税金额",
    }
)


def yuan_to_fen(val: Any) -> int | None:
    """元 → 分。None/空串 → None；非法/空解析 → 0（与 parse_amount 空按 0 一致的写入侧）。

    注意：入参必须是**元**。库内已是分的 int 请用 as_fen / 直接用，勿再 yuan_to_fen。
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return int(val) * 100
    if isinstance(val, int) and not isinstance(val, bool):
        # 元整数（管理端/API 常传 100 表示 100 元）
        return val * 100
    s = str(val).strip()
    if s == "" or s == "-":
        return None
    s = s.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return 0
    fen = (d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(fen)


def as_fen(val: Any) -> int:
    """算账层统一入分。

    - **int**（非 bool）= 已是分（db.load_* 必须 int() 后再传入，避免 SQLite float 分被当元）
    - **float / 带小数点的 str** = 元（xlsx 进料）
    - **纯整数字符串** = 分（adj 原值等）
    - None/空 → 0
    """
    if val is None:
        return 0
    if isinstance(val, bool):
        return int(val) * 100
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        # 仅当确为「元」浮点（xlsx）；库读路径不得传 float
        f = yuan_to_fen(val)
        return 0 if f is None else f
    s = str(val).strip()
    if s == "" or s == "-":
        return 0
    if s.lstrip("-").isdigit() and "." not in s and "e" not in s.lower():
        try:
            return int(s)
        except ValueError:
            return 0
    f = yuan_to_fen(s)
    return 0 if f is None else f


def fen_to_yuan(fen: Any) -> float:
    """分 → 元 float（供 profit/显示与历史路径兼容）。None → 0.0。"""
    if fen is None:
        return 0.0
    try:
        return float(Decimal(int(fen)) / Decimal(100))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def fen_to_yuan_or_none(fen: Any) -> float | None:
    """分 → 元；None 保持 None（台账空金额行）。"""
    if fen is None:
        return None
    return fen_to_yuan(fen)


def record_amounts_to_fen(table: str, record: dict) -> dict:
    """拷贝记录，将 std 金额列元→分（定位键已在 normalize 用元算好，勿改键）。"""
    cols = STD_MONEY_COLS.get(table) or ()
    if not cols:
        return record
    out = dict(record)
    for c in cols:
        if c in out:
            out[c] = yuan_to_fen(out[c])
    return out


def fen_to_yuan_str(fen: Any) -> str:
    """库内分 → 元文本（调整记录原值/管理端展示用）。None → ''。"""
    if fen is None:
        return ""
    try:
        d = Decimal(int(fen)) / Decimal(100)
    except (InvalidOperation, ValueError, TypeError):
        return ""
    # 去掉多余尾零，保持可读（1234.50 → 1234.5；100 → 100）
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def is_amount_field(field: str) -> bool:
    return field in AMOUNT_FIELD_NAMES
