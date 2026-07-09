#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收单台账列定位 + 直接读列分类（无映射表兜底）。

「业务BU/利润归属中心」「对应报表大类」两列由财务在收单台账里逐行直填，本管道只读直接值——
没填就是"未分类"，不查任何映射表兜底（倒逼分类在源头落实）。列**按表头文字找、不认死列号**，
列被插入/改名（如"业务BU"→"利润归属中心"）只需在别名表里加一个候选名；一个候选都对不上直接报错，
绝不静默拿错列算出好看但错误的数字。（逻辑沿用 v1.3 已验证的 mapping.py。）
"""
from __future__ import annotations

from typing import Any, Sequence

import loaders

LEDGER_COLUMN_ALIASES: dict[str, list[str]] = {
    "收单月份": ["收单月份"],
    "收单日期": ["收单日期"],
    "含税金额": ["含税金额"],
    "业务BU": ["业务BU", "利润归属中心"],
    "对应报表大类": ["对应报表大类"],
    "预算明细费用类型": ["预算明细费用类型"],
    "预算归属部门": ["预算归属部门"],
}

# 软字段：老台账没这列不算错，跳过即可（下游用 lcols.get() 判在不在）
SOFT_LEDGER_FIELDS = {"预算归属部门"}


def resolve_ledger_columns(header_row: Sequence[Any]) -> dict[str, int]:
    header = [str(h).strip() if h is not None else "" for h in header_row]
    resolved: dict[str, int] = {}
    missing: list[str] = []
    for field, aliases in LEDGER_COLUMN_ALIASES.items():
        hits = [a for a in aliases if a in header]
        if not hits:
            if field not in SOFT_LEDGER_FIELDS:
                missing.append(f"「{field}」（试过的表头文字：{'/'.join(aliases)}）")
            continue
        if any(header.count(a) > 1 for a in hits) or len(hits) > 1:
            raise ValueError(
                f"收单台账表头里「{field}」出现多列（命中：{hits}），无法确定读哪一列，请先在源表里改名去重。\n实际表头：{header}")
        resolved[field] = header.index(hits[0])
    if missing:
        raise ValueError(
            "收单台账表头里缺这些必需列，可能被改名/删掉了，需人工核实实际表头再继续：\n  "
            + "\n  ".join(missing)
            + f"\n实际表头：{header}"
        )
    return resolved


def classify_expense_category(row: tuple, cfg: dict, cols: dict[str, int]) -> tuple[str, bool]:
    """返回 (报表大类, 是否未分类)。行里没直接填就是未分类。"""
    c = cols["对应报表大类"]
    direct = row[c] if len(row) > c else None
    if direct not in (None, ""):
        return str(direct).strip(), False
    return cfg["unclassified_label_expense"], True


def classify_bu(row: tuple, cfg: dict, cols: dict[str, int]) -> tuple[str, bool]:
    c = cols["业务BU"]
    direct = row[c] if len(row) > c else None
    if direct not in (None, ""):
        return str(direct).strip(), False
    return cfg["unclassified_label_bu"], True


def build_unclassified_summary(
    ledger_rows: list[tuple], cfg: dict, cols: dict[str, int], amount_filter: Any = None
) -> dict[str, Any]:
    """统计"未分类"金额/笔数（费用大类 + BU 各一份）。amount_filter(row)->bool 按期间过滤，None=不过滤。"""
    exp_count = exp_amount = 0
    bu_count = bu_amount = 0
    c_amt = cols["含税金额"]
    for row in ledger_rows:
        amt_f = loaders.parse_amount(row[c_amt] if len(row) > c_amt else None)
        if amt_f == 0.0:
            continue
        if amount_filter is not None and not amount_filter(row):
            continue
        if classify_expense_category(row, cfg, cols)[0] == cfg["unclassified_label_expense"]:
            exp_count += 1
            exp_amount += amt_f
        if classify_bu(row, cfg, cols)[0] == cfg["unclassified_label_bu"]:
            bu_count += 1
            bu_amount += amt_f
    return {
        "expense": {"count": exp_count, "amount": round(exp_amount, 2)},
        "bu": {"count": bu_count, "amount": round(bu_amount, 2)},
    }
