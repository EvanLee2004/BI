#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规范化：把各源读出的原始行洗成标准表记录（含归属月 + 行哈希定位键）。纯函数、无 IO。

回归红线约定（改读库后数字与 v6-final 一分不差）：
- 金额一律 loaders.parse_amount → float 存 REAL；空/解析不出按 0（与旧 profit 行为一致）。
- 智云四源日期规范成 ISO；解析不出/为空则存空串（profit 再解析仍得 None、行同样被剔除、体检计数一致）。
- 收单台账「收单日期/收单月份」**保留原文文本**（不转 ISO）——profit 的 ledger_row_date 依赖这两列的
  回退逻辑，转了会改行为；只另算一个 归属月 供库内查询。
- 定位键=行哈希（造数把同 ID 复制成 7 个金额/日期各异的变体，ID 不唯一→退行哈希；标准表用自增 id
  做主键、绝不塌行，定位键只作刀2匹配索引）。
"""
from __future__ import annotations

import hashlib
from typing import Any

import loaders


def _amt(raw: Any) -> float:
    return loaders.parse_amount(raw)


def _iso_and_month(raw: Any) -> tuple[str, str | None]:
    """智云日期 → (ISO 或 空串, 归属月 或 None)。空/解析不出 → ('', None) 或 (原文, None)。"""
    parts = loaders.parse_date_parts(raw)
    if parts:
        y, m, d = parts
        try:
            return f"{y:04d}-{m:02d}-{d:02d}", f"{y:04d}-{m:02d}"
        except (ValueError, TypeError):
            pass
    if raw is None:
        return "", None
    s = str(raw).strip()
    return s, None


def _hash(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _locator(natural: Any, *hash_parts: Any) -> str:
    """稳定定位键：有自然键用自然键文本（重抓金额变也不变→重放稳）；自然键空则回退行哈希兜底。
    见 04_设计变更_定位键策略。"""
    s = "" if natural is None else str(natural).strip()
    return s if s else _hash(*hash_parts)


# ---------------- 智云四源 ----------------
def norm_project_detail(rows: list[dict[str, str]], c: dict) -> list[dict]:
    out = []
    for r in rows:
        iso, ym = _iso_and_month(r.get(c["project_delivery_date"]))
        rev, cost = _amt(r.get(c["project_revenue"])), _amt(r.get(c["project_cost"]))
        so = str(r.get("订单号") or r.get("SO") or "").strip()
        sod = r.get("SOD") or ""  # 定位键=SOD（明细行级，稳定）
        out.append({
            "订单号": so, "客户": str(r.get("客户", "")).strip(),
            "业务线": str(r.get("业务线", "")).strip(),
            "整单交付日期": iso, "交付额": rev, "项目成本": cost,
            "归属月": ym, "原值_交付日期": iso, "原值_归属月": ym,
            "定位键": _locator(sod, so, iso, rev, cost),
        })
    return out


def norm_orders(rows: list[dict[str, str]], c: dict) -> list[dict]:
    out = []
    for r in rows:
        iso, ym = _iso_and_month(r.get(c["order_date"]))
        amt = _amt(r.get(c["order_amount"]))
        so = str(r.get("订单号") or r.get("SO") or "").strip()
        out.append({"订单号": so, "下单日期": iso, "下单预估额": amt,
                    "归属月": ym, "原值_归属月": ym, "定位键": _locator(so, so, iso, amt)})
    return out


def norm_receipts(rows: list[dict[str, str]], c: dict) -> list[dict]:
    out = []
    for r in rows:
        iso, ym = _iso_and_month(r.get(c["receipt_date"]))
        amt = _amt(r.get(c["receipt_amount"]))
        rid = str(r.get("回款记录ID") or "").strip()
        out.append({"回款ID": rid, "到账日期": iso, "到账金额": amt,
                    "归属月": ym, "原值_归属月": ym, "定位键": _locator(rid, rid, iso, amt)})
    return out


def norm_inhouse(rows: list[dict[str, str]], c: dict, cfg: dict) -> list[dict]:
    """仅 IN-HOUSE 行（03 设计）；过滤逻辑与 profit.compute_inhouse_cost 一致。"""
    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    tcol = c["inhouse_type"]
    out = []
    for r in rows:
        typ = str(r.get(tcol, "")).strip()
        if kw not in typ.upper():
            continue
        iso, ym = _iso_and_month(r.get(c["inhouse_date"]))
        amt = _amt(r.get(c["inhouse_amount"]))
        tid = str(r.get("任务明细ID") or "").strip()
        out.append({"任务ID": tid, "任务提交日期": iso, "结算金额": amt,
                    "译员类型": typ, "归属月": ym, "原值_归属月": ym,
                    "定位键": _locator(tid, tid, iso, amt)})
    return out


# ---------------- 收单台账 ----------------
def norm_ledger(header: list, rows: list[tuple], ledger_year: int, lcols: dict) -> list[dict]:
    """收单台账原始行 → 标准记录。**逐行原样保留（含全空行）**，保证行数与旧读法一致（体检面板行数红线）。
    收单日期/收单月份保留原文文本；归属月由 ledger_row_date 另算。"""
    import periods
    c_m, c_d, c_amt = lcols["收单月份"], lcols["收单日期"], lcols["含税金额"]
    c_bu, c_cat, c_fine = lcols["业务BU"], lcols["对应报表大类"], lcols["预算明细费用类型"]
    c_dept = lcols.get("预算归属部门")  # 软字段：老台账可能没有

    def _txt(row, i):
        v = row[i] if len(row) > i else None
        return None if v is None else str(v)

    out = []
    for row in rows:
        月份, 日期 = _txt(row, c_m), _txt(row, c_d)
        金额 = _amt(row[c_amt] if len(row) > c_amt else None)
        金额_store = None if (len(row) <= c_amt or row[c_amt] is None or str(row[c_amt]).strip() == "") else 金额
        bu, cat, fine = _txt(row, c_bu), _txt(row, c_cat), _txt(row, c_fine)
        dept = _txt(row, c_dept) if c_dept is not None else None
        parts = periods.ledger_row_date(row, ledger_year, lcols)
        ym = f"{parts[0]:04d}-{parts[1]:02d}" if parts else None
        out.append({
            "收单月份": 月份, "收单日期": 日期, "含税金额": 金额_store,
            "业务BU": bu, "对应报表大类": cat, "预算明细费用类型": fine,
            "预算归属部门": dept,
            "归属月": ym, "原值_归属月": ym,
            "定位键": _hash(月份, 日期, 金额_store, bu, cat, fine),  # 台账无自然ID，行哈希
        })
    return out
