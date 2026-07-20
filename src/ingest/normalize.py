#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规范化：把各源读出的原始行洗成标准表记录（含归属月 + 行哈希定位键）。纯函数、无 IO。

回归红线约定（改读库后数字与 v6-final 一分不差）：
- 金额一律 loaders.parse_amount → float **元**（定位键哈希用元字符串）；入库前 ingest._insert 再转 INTEGER 分。
- 智云四源日期规范成 ISO；解析不出/为空则存空串（profit 再解析仍得 None、行同样被剔除、体检计数一致）。
- 收单台账「收单日期/收单月份」**保留原文文本**（不转 ISO）——profit 的 ledger_row_date 依赖这两列的
  回退逻辑，转了会改行为；只另算一个 归属月 供库内查询。
- 定位键=自然键优先，否则行哈希（台账哈希含金额元字符串——分存储不改哈希输入，避免调整失配）。
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
    # 定位键短指纹，非密码学用途（冲突可接受）；SHA-1 足够稳定短 — bandit B324 误报
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]  # nosec B324


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
        # 任务书64·D4：业务线走 config.columns.project_line，不硬编码列名
        line_col = c.get("project_line") or "业务线"
        out.append(
            {
                "订单号": so,
                "客户": str(r.get("客户", "")).strip(),
                "业务线": str(r.get(line_col, "") or r.get("业务线", "")).strip(),
                "销售": str(r.get("销售") or "").strip(),
                "整单交付日期": iso,
                "交付额": rev,
                "项目成本": cost,
                "归属月": ym,
                "原值_交付日期": iso,
                "原值_归属月": ym,
                "定位键": _locator(sod, so, iso, rev, cost),
            }
        )
    return out


def norm_orders(rows: list[dict[str, str]], c: dict) -> list[dict]:
    out = []
    for r in rows:
        iso, ym = _iso_and_month(r.get(c["order_date"]))
        amt = _amt(r.get(c["order_amount"]))
        so = str(r.get("订单号") or r.get("SO") or "").strip()
        out.append(
            {
                "订单号": so,
                "下单日期": iso,
                "下单预估额": amt,
                "部门": str(r.get("部门") or "").strip(),
                "销售": str(r.get("销售") or "").strip(),
                "客户": str(r.get("客户") or r.get("客户名称") or "").strip(),
                "归属月": ym,
                "原值_归属月": ym,
                "定位键": _locator(so, so, iso, amt),
            }
        )
    return out


def norm_receipts(rows: list[dict[str, str]], c: dict) -> list[dict]:
    out = []
    for r in rows:
        iso, ym = _iso_and_month(r.get(c["receipt_date"]))
        amt = _amt(r.get(c["receipt_amount"]))
        rid = str(r.get("回款记录ID") or "").strip()
        out.append(
            {
                "回款ID": rid,
                "到账日期": iso,
                "到账金额": amt,
                "客户": str(r.get("客户") or "").strip(),
                "销售": str(r.get("销售") or "").strip(),
                "归属月": ym,
                "原值_归属月": ym,
                "定位键": _locator(rid, rid, iso, amt),
            }
        )
    return out


def norm_inhouse(rows: list[dict[str, str]], c: dict, cfg: dict) -> list[dict]:
    """仅 IN-HOUSE 行（03 设计）；过滤逻辑与 profit.compute_inhouse_cost 一致。
    A2：补「译员姓名」（供应商姓名）；「销售」列仍落库但不可信、不进销售名池。"""
    kw = str(cfg.get("inhouse_keyword", "IN-HOUSE")).upper()
    tcol = c["inhouse_type"]
    ncol = c.get("inhouse_name") or "供应商姓名"
    out = []
    for r in rows:
        typ = str(r.get(tcol, "")).strip()
        if kw not in typ.upper():
            continue
        iso, ym = _iso_and_month(r.get(c["inhouse_date"]))
        amt = _amt(r.get(c["inhouse_amount"]))
        tid = str(r.get("任务明细ID") or "").strip()
        # 译员姓名：配置列优先；缺列时尝试常见别名（旧导出兼容）
        name = str(r.get(ncol) or r.get("供应商姓名") or r.get("译员姓名") or "").strip()
        out.append(
            {
                "任务ID": tid,
                "任务提交日期": iso,
                "结算金额": amt,
                "译员类型": typ,
                "译员姓名": name,
                "销售": str(r.get("销售") or "").strip(),
                "归属月": ym,
                "原值_归属月": ym,
                "定位键": _locator(tid, tid, iso, amt),
            }
        )
    return out


# ---------------- 收单台账 ----------------
def _ledger_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not str(v).strip()) or str(v).strip() == ""


def _ledger_cell(row, i):
    if i is None:
        return None
    v = row[i] if len(row) > i else None
    return None if v is None else v


def ledger_row_is_empty(row, lcols: dict) -> bool:
    """表尾格式化空行：全部业务字段空（任务书35）。文件路径与入库清洗共用。"""
    c_m, c_d, c_amt = lcols["收单月份"], lcols["收单日期"], lcols["含税金额"]
    c_bu, c_cat, c_fine = lcols["业务BU"], lcols["对应报表大类"], lcols["预算明细费用类型"]
    c_dept = lcols.get("预算归属部门")
    soft = [lcols.get(k) for k in ("事项", "提单人", "提单人部门", "业务员", "配音费合同号")]
    cells = [
        _ledger_cell(row, c_m),
        _ledger_cell(row, c_d),
        _ledger_cell(row, c_amt),
        _ledger_cell(row, c_bu),
        _ledger_cell(row, c_cat),
        _ledger_cell(row, c_fine),
        _ledger_cell(row, c_dept) if c_dept is not None else None,
    ]
    for i in soft:
        cells.append(_ledger_cell(row, i) if i is not None else None)
    return all(_ledger_blank(x) for x in cells)


def filter_ledger_empty_rows(header: list, rows: list[tuple], lcols: dict | None = None) -> list[tuple]:
    """去掉全空格式化行；lcols 缺省时按表头解析。"""
    import columns as _columns

    lc = lcols or _columns.resolve_ledger_columns(header)
    return [r for r in rows if not ledger_row_is_empty(r, lc)]


def norm_ledger(header: list, rows: list[tuple], ledger_year: int, lcols: dict) -> list[dict]:
    """收单台账原始行 → 标准记录。

    任务书35：表尾「有格式但全空」行（全部业务字段空）直接跳过，不进 std_费用明细。
    收单日期/收单月份保留原文文本；归属月由 ledger_row_date 另算。
    """
    import periods

    c_m, c_d, c_amt = lcols["收单月份"], lcols["收单日期"], lcols["含税金额"]
    c_bu, c_cat, c_fine = lcols["业务BU"], lcols["对应报表大类"], lcols["预算明细费用类型"]
    c_dept = lcols.get("预算归属部门")  # 软字段：老台账可能没有

    def _txt(row, i):
        if i is None:
            return None
        v = row[i] if len(row) > i else None
        return None if v is None else str(v)

    # soft columns by Chinese header index if present in lcols soft keys
    c_item = lcols.get("事项")
    c_sub = lcols.get("提单人")
    c_subd = lcols.get("提单人部门")
    c_sales = lcols.get("业务员")
    c_po = lcols.get("配音费合同号")

    out = []
    for row in rows:
        if ledger_row_is_empty(row, lcols):
            continue
        月份, 日期 = _txt(row, c_m), _txt(row, c_d)
        金额 = _amt(row[c_amt] if len(row) > c_amt else None)
        金额_store = None if (len(row) <= c_amt or row[c_amt] is None or str(row[c_amt]).strip() == "") else 金额
        bu, cat, fine = _txt(row, c_bu), _txt(row, c_cat), _txt(row, c_fine)
        dept = _txt(row, c_dept) if c_dept is not None else None
        事项, 提单人 = _txt(row, c_item), _txt(row, c_sub)
        提单人部门, 业务员 = _txt(row, c_subd), _txt(row, c_sales)
        配音费合同号 = _txt(row, c_po)
        parts = periods.ledger_row_date(row, ledger_year, lcols)
        ym = f"{parts[0]:04d}-{parts[1]:02d}" if parts else None
        out.append(
            {
                "收单月份": 月份,
                "收单日期": 日期,
                "含税金额": 金额_store,
                "业务BU": bu,
                "对应报表大类": cat,
                "预算明细费用类型": fine,
                "预算归属部门": dept,
                "事项": 事项,
                "提单人": 提单人,
                "提单人部门": 提单人部门,
                "业务员": 业务员,
                "配音费合同号": 配音费合同号,
                "归属月": ym,
                "原值_归属月": ym,
                "定位键": _hash(月份, 日期, 金额_store, bu, cat, fine),  # 台账无自然ID，行哈希
            }
        )
    return out
