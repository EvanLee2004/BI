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
import schema

from .constants import DETAIL_TABLES, VIEW_EXPENSE_COLUMNS, VIEW_EXPENSE_COLUMNS_BU, DETAIL_DATE_COLS, UNCLASSIFIED_WHERE, UNFILLED_DEPT_WHERE

# pure-move funcs from _impl.py

def detail_col_kind(table_key: str, col: str) -> str:
    """列筛选类型：number（金额元区间）/ date（起止）/ text（关键词+多选）。"""
    if table_key not in DETAIL_TABLES:
        return "text"
    phys = DETAIL_TABLES[table_key][0]
    if col in (money.STD_MONEY_COLS.get(phys) or ()):
        return "number"
    if col in DETAIL_DATE_COLS:
        return "date"
    return "text"


def detail_columns_meta(table_key: str, *, audience: str = "admin") -> list[dict]:
    """表头筛选用：[{name, kind}, …]。audience=admin|view|view_bu（任务书41·D）。"""
    if table_key not in DETAIL_TABLES:
        raise KeyError(f"未知明细表：{table_key}")
    cols = _detail_display_columns(table_key, audience=audience)
    return [{"name": c, "kind": detail_col_kind(table_key, c)} for c in cols]


def _detail_display_columns(table_key: str, *, audience: str = "admin") -> list[str]:
    """展示列：管理端全列；看端费用明细走白名单（顺序固定）。"""
    _table, cols, _search = DETAIL_TABLES[table_key]
    if table_key == "费用明细" and audience in ("view", "view_bu"):
        return list(VIEW_EXPENSE_COLUMNS_BU if audience == "view_bu" else VIEW_EXPENSE_COLUMNS)
    return list(cols)


def _parse_filters_arg(filters) -> dict:
    """filters：dict 或 JSON 字符串 → {列名: {q?, in?, min?, max?, from?, to?}}。非法→{}。"""
    import json as _json

    if not filters:
        return {}
    if isinstance(filters, str):
        s = filters.strip()
        if not s:
            return {}
        try:
            filters = _json.loads(s)
        except (TypeError, ValueError, _json.JSONDecodeError):
            return {}
    if not isinstance(filters, dict):
        return {}
    out = {}
    for k, v in filters.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if v is None or v == "" or v == {}:
            continue
        if not isinstance(v, dict):
            continue
        out[k.strip()] = v
    return out


def _append_number_filter(col: str, spec: dict, money_cols: set, where: list, args: list) -> None:
    """金额/数值区间筛选 → where/args（就地）。"""
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and lo != "":
        try:
            v = float(lo)
        except (TypeError, ValueError):
            v = None
        if v is not None:
            if col in money_cols:
                fen = money.yuan_to_fen(v)
                if fen is not None:
                    where.append(f"{col} >= ?")
                    args.append(fen)
            else:
                where.append(f"CAST({col} AS REAL) >= ?")
                args.append(v)
    if hi is not None and hi != "":
        try:
            v = float(hi)
        except (TypeError, ValueError):
            return
        if col in money_cols:
            fen = money.yuan_to_fen(v)
            if fen is not None:
                where.append(f"{col} <= ?")
                args.append(fen)
        else:
            where.append(f"CAST({col} AS REAL) <= ?")
            args.append(v)


def _append_date_filter(col: str, spec: dict, where: list, args: list) -> None:
    d0, d1 = spec.get("from") or spec.get("start"), spec.get("to") or spec.get("end")
    if d0:
        where.append(f"substr(CAST({col} AS TEXT),1,10) >= ?")
        args.append(str(d0)[:10])
    if d1:
        where.append(f"substr(CAST({col} AS TEXT),1,10) <= ?")
        args.append(str(d1)[:10])


def _append_text_filter(col: str, spec: dict, where: list, args: list) -> None:
    """关键词 LIKE + 去重值 IN（多选）。"""
    q = spec.get("q") or spec.get("keyword")
    if q is not None and str(q).strip():
        where.append(f"CAST({col} AS TEXT) LIKE ?")
        args.append("%" + str(q).strip() + "%")
    vals = spec.get("in") or spec.get("values")
    if vals is not None:
        if isinstance(vals, str):
            vals = [vals]
        clean = [str(x) for x in vals if x is not None and str(x) != ""]
        if clean:
            # 空串多选语义：显式 in 含 "" 时用 COALESCE
            ph = ",".join("?" * len(clean))
            where.append(f"CAST(COALESCE({col},'') AS TEXT) IN ({ph})")
            args.extend(clean)


def _build_column_filters(table_key: str, phys: str, have: set, filters: dict | None) -> tuple[list[str], list]:
    """白名单列 + 参数化 WHERE 片段。金额筛选用元→分。多列 AND。"""
    fdict = _parse_filters_arg(filters)
    if not fdict:
        return [], []
    allowed = set(DETAIL_TABLES[table_key][1])
    money_cols = set(money.STD_MONEY_COLS.get(phys) or ())
    where: list[str] = []
    args: list = []
    for col, spec in fdict.items():
        if col not in allowed or col not in have:
            continue
        if not isinstance(spec, dict):
            continue
        kind = detail_col_kind(table_key, col)
        if kind == "number":
            _append_number_filter(col, spec, money_cols, where, args)
        elif kind == "date":
            _append_date_filter(col, spec, where, args)
        else:
            _append_text_filter(col, spec, where, args)
    return where, args


def adjustable_fields() -> dict[str, list[str]]:
    """{表键: 可调整字段列表}——R1：由 schema 黑名单制自动推导，管理员端字段下拉从服务端下发。"""
    return {k: list(schema.ADJUSTABLE_FIELDS[v[0]]) for k, v in DETAIL_TABLES.items()}


def _append_detail_flags(
    table_key: str, have: set, where: list, args: list, *, unclassified: bool, unfilled_dept: bool, bu, hide_salary: bool
) -> None:
    if unclassified:
        if table_key != "费用明细":
            raise KeyError("unclassified 仅支持 费用明细 表")
        where.append(UNCLASSIFIED_WHERE)
    if unfilled_dept:
        if table_key != "下单":
            raise KeyError("unfilled_dept 仅支持 下单 表")
        where.append(UNFILLED_DEPT_WHERE)
    if bu:
        if table_key != "费用明细":
            raise KeyError("bu 筛选仅支持 费用明细 表")
        where.append("业务BU=?")
        args.append(str(bu).strip())
    if hide_salary and table_key == "费用明细" and "对应报表大类" in have:
        # 任务书37·B8：整体账号默认隐藏「工资」大类（管理员/开关打开不受影响）
        where.append("(对应报表大类 IS NULL OR TRIM(对应报表大类)<>'工资')")


def _append_detail_period(where: list, args: list, month, year, month_from, month_to) -> None:
    """归属月：区间优先于单月/年。"""
    mf = (month_from or "").strip() or None
    mt = (month_to or "").strip() or None
    if mf or mt:
        import re as _re

        ym_re = _re.compile(r"^\d{4}-\d{2}$")
        if mf and not ym_re.match(mf):
            raise KeyError("month_from 须为 YYYY-MM")
        if mt and not ym_re.match(mt):
            raise KeyError("month_to 须为 YYYY-MM")
        if mf and mt:
            if mf > mt:
                mf, mt = mt, mf
            where.append("归属月 BETWEEN ? AND ?")
            args.extend([mf, mt])
        elif mf:
            where.append("归属月 >= ?")
            args.append(mf)
        else:
            where.append("归属月 <= ?")
            args.append(mt)
        return
    if month:
        where.append("归属月=?")
        args.append(month)
        return
    if year:
        y = str(year).strip()
        if not (y.isdigit() and len(y) == 4):
            raise KeyError("year 须为 4 位数字")
        where.append("归属月 LIKE ?")
        args.append(f"{y}-%")


def _detail_base_where(
    table_key: str,
    table: str,
    have: set,
    searchable: list[str],
    month: str | None,
    q: str | None,
    unclassified: bool,
    unfilled_dept: bool,
    year: str | None,
    bu: str | None,
    filters=None,
    *,
    hide_salary: bool = False,
    month_from: str | None = None,
    month_to: str | None = None,
) -> tuple[list[str], list]:
    """query_detail / distinct 共用 WHERE（含任务书37 列筛 + 工资大类可选隐藏）。
    month_from/month_to：归属月闭区间 YYYY-MM（任务书41·E）；与单月 month 互斥时区间优先。"""
    where = ["已删除=0"]
    args: list = []
    _append_detail_flags(
        table_key, have, where, args, unclassified=unclassified, unfilled_dept=unfilled_dept, bu=bu, hide_salary=hide_salary
    )
    _append_detail_period(where, args, month, year, month_from, month_to)
    if q:
        like = "%" + q.strip() + "%"
        use_cols = [c for c in searchable if c in have]
        if use_cols:
            ors = " OR ".join(f"{c} LIKE ?" for c in use_cols)
            where.append(f"({ors})")
            args += [like] * len(use_cols)
    fw, fa = _build_column_filters(table_key, table, have, filters)
    where.extend(fw)
    args.extend(fa)
    return where, args


def query_detail(
    conn: sqlite3.Connection,
    table_key: str,
    month: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    unclassified: bool = False,
    unfilled_dept: bool = False,
    year: str | None = None,
    bu: str | None = None,
    filters=None,
    *,
    hide_salary: bool = False,
    audience: str = "admin",
    month_from: str | None = None,
    month_to: str | None = None,
    max_page_size: int = 500,
) -> dict:
    """明细分页查询（按年/月 + 关键词 + 可选 BU + 任务书37 列筛）。仅读未删除行。表键白名单防注入。
    unclassified=True 仅「费用明细」：对应报表大类为空且金额非零。
    unfilled_dept=True 仅「下单」：部门为空且金额非零。
    year=YYYY → 归属月 LIKE 'YYYY-%'（A5 年维度）；month 仍为完整归属月 YYYY-MM。
    month_from/month_to：归属月闭区间（任务书41·E 真筛，SQL BETWEEN）。
    bu=非空 → 费用明细 业务BU 精确匹配（A5 BU 隔离，调用方负责鉴权后再传入）。
    filters：{列: {q/in/min/max/from/to}}，后端 SQL AND，禁止前端拉全表。
    hide_salary：费用明细隐藏对应报表大类=工资（整体账号默认）。
    audience：admin=管理端全列；view/view_bu=看端白名单（任务书41·D）。
    max_page_size：列表默认 500；导出可传 5000（防静默截断）。"""
    if table_key not in DETAIL_TABLES:
        raise KeyError(f"未知明细表：{table_key}（可选：{list(DETAIL_TABLES)}）")
    table, _full_cols, searchable = DETAIL_TABLES[table_key]
    # 缺列兼容（旧库未补齐 A5 列时降级）
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    cols = _detail_display_columns(table_key, audience=audience)
    if audience == "admin":
        cols = [c for c in cols if c in have or c in ("定位键", "归属月")]
    else:
        cols = [c for c in cols if c in have]
    where, args = _detail_base_where(
        table_key,
        table,
        have,
        searchable,
        month,
        q,
        unclassified,
        unfilled_dept,
        year,
        bu,
        filters,
        hide_salary=hide_salary,
        month_from=month_from,
        month_to=month_to,
    )
    wsql = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {wsql}", args).fetchone()[0]
    page = max(1, int(page))
    cap = max(1, min(10000, int(max_page_size or 500)))
    page_size = max(1, min(cap, int(page_size)))
    offset = (page - 1) * page_size
    coln = ",".join(cols)
    rows = conn.execute(
        f"SELECT {coln} FROM {table} WHERE {wsql} ORDER BY id LIMIT ? OFFSET ?", args + [page_size, offset]
    ).fetchall()
    # 管理端明细：金额列转元 float 展示（录入/阅读习惯=元；库内仍是分）
    money_cols = set(money.STD_MONEY_COLS.get(table) or ())
    out_rows = []
    for r in rows:
        d = dict(zip(cols, r, strict=False))
        for mc in money_cols:
            if mc in d and d[mc] is not None:
                d[mc] = money.fen_to_yuan(d[mc])
        out_rows.append(d)
    col_meta = [{"name": c, "kind": detail_col_kind(table_key, c)} for c in cols]
    return {
        "table": table_key,
        "columns": cols,
        "column_meta": col_meta,
        "rows": out_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def query_detail_distinct(
    conn: sqlite3.Connection,
    table_key: str,
    column: str,
    month: str | None = None,
    q: str | None = None,
    year: str | None = None,
    bu: str | None = None,
    filters=None,
    *,
    hide_salary: bool = False,
    limit: int = 200,
    audience: str = "admin",
    month_from: str | None = None,
    month_to: str | None = None,
) -> dict:
    """文本列去重值（Excel 式多选下拉）。列白名单；limit 默认 200。"""
    if table_key not in DETAIL_TABLES:
        raise KeyError(f"未知明细表：{table_key}")
    table, cols, searchable = DETAIL_TABLES[table_key]
    allow = set(_detail_display_columns(table_key, audience=audience)) | set(cols)
    if column not in allow:
        raise KeyError(f"列不在表白名单：{column}")
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in have:
        return {"column": column, "values": [], "total": 0}
    # 构建 WHERE 时排除本列自己的 in/q，避免下拉自我收窄（其它列筛仍生效）
    fdict = _parse_filters_arg(filters)
    if column in fdict:
        fdict = {k: v for k, v in fdict.items() if k != column}
    where, args = _detail_base_where(
        table_key,
        table,
        have,
        searchable,
        month,
        q,
        False,
        False,
        year,
        bu,
        fdict,
        hide_salary=hide_salary,
        month_from=month_from,
        month_to=month_to,
    )
    wsql = " AND ".join(where)
    limit = max(1, min(1000, int(limit)))
    sql = (
        f"SELECT DISTINCT CAST(COALESCE({column},'') AS TEXT) AS v FROM {table} "
        f"WHERE {wsql} ORDER BY v LIMIT ?"
    )
    vals = [r[0] for r in conn.execute(sql, args + [limit]).fetchall()]
    total = conn.execute(
        f"SELECT COUNT(DISTINCT CAST(COALESCE({column},'') AS TEXT)) FROM {table} WHERE {wsql}", args
    ).fetchone()[0]
    return {"column": column, "values": vals, "total": total, "limit": limit}


