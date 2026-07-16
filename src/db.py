#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板.db 访问层：连接、建表、读标准表/手填表。

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

DB_DEFAULT_REL = "看板.db"


def db_path(cfg: dict, root: Path | None = None) -> Path:
    """看板.db 路径：config.db_path（相对数据目录）或默认 数据/看板.db。"""
    rel = cfg.get("db_path", DB_DEFAULT_REL)
    p = Path(rel)
    if p.is_absolute():
        return p
    return loaders.data_dir(cfg, root) / rel


# SQLite 生产标配（任务书33·A2）：WAL 写不挡读；busy 等锁；NORMAL 平衡安全/速度
_BUSY_TIMEOUT_MS = 5000


def connect(cfg: dict, root: Path | None = None) -> sqlite3.Connection:
    path = db_path(cfg, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：更新线程与请求线程可共用连接模式（各自仍应独立 connect）
    conn = sqlite3.connect(str(path), timeout=_BUSY_TIMEOUT_MS / 1000.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    schema.create_all(conn)
    return conn


# ---------------- 读标准表 → loaders 同构 ----------------
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


# 台账列在标准表里的固定顺序（读回时据此拼回 (表头, 数据行)）
LEDGER_STD_COLS = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]


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


# ---------------- 读手填表 → 金额单位：分 ----------------
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


# ---------------- 明细查询（管理员端 /api/detail）----------------
# 表键 → (物理表, 展示列, 可搜索文本列)
DETAIL_TABLES: dict[str, tuple[str, list[str], list[str]]] = {
    # searchable 含定位键/订单号（陆总现场要按单号或定位键搜）
    "收入明细": (
        "std_收入明细",
        ["定位键", "订单号", "客户", "业务线", "销售", "整单交付日期", "交付额", "项目成本", "归属月"],
        ["定位键", "订单号", "客户", "业务线", "销售"],
    ),
    "下单": (
        "std_下单",
        ["定位键", "订单号", "下单日期", "下单预估额", "部门", "销售", "归属月"],
        ["定位键", "订单号", "部门", "销售"],
    ),
    "回款": (
        "std_回款",
        ["定位键", "回款ID", "到账日期", "到账金额", "客户", "销售", "归属月"],
        ["定位键", "回款ID", "客户", "销售"],
    ),
    # 列头「销售」实为项目关联销售（非费用归属），管理端表头旁见 note
    # A2：主列/筛选=译员姓名（供应商姓名）；销售列保留次要展示（任务关联销售不可信）
    "内部译员": (
        "std_内部译员",
        ["定位键", "任务ID", "任务提交日期", "结算金额", "译员类型", "译员姓名", "销售", "归属月"],
        ["定位键", "任务ID", "译员类型", "译员姓名", "销售"],
    ),
    # A5：费用明细全列（含事项≈摘要）；系统列归属月置末 —— 管理端「数据调整」用全列
    "费用明细": (
        "std_费用明细",
        [
            "定位键",
            "收单月份",
            "收单日期",
            "含税金额",
            "业务BU",
            "对应报表大类",
            "预算明细费用类型",
            "预算归属部门",
            "事项",
            "提单人",
            "提单人部门",
            "业务员",
            "配音费合同号",
            "归属月",
        ],
        ["定位键", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门", "事项", "提单人", "业务员"],
    ),
}

# 任务书41·D / 46·阶段0：看端（整体页+BU 页）费用明细白名单与列序；口径人=业务员（非提单人）
# 隐藏：定位键/收单月份/归属月/提单人/提单人部门/配音费合同号。管理端仍用 DETAIL_TABLES 全列。
# 归属月计算仍依赖库内「收单月份」列——只动展示，norm_ledger 零改动。
VIEW_EXPENSE_COLUMNS: list[str] = [
    "收单日期",
    "事项",
    "含税金额",
    "对应报表大类",
    "预算明细费用类型",
    "业务员",
    "预算归属部门",
    "业务BU",
]
# BU 页可省「业务BU」（本页全是自己）
VIEW_EXPENSE_COLUMNS_BU: list[str] = [c for c in VIEW_EXPENSE_COLUMNS if c != "业务BU"]
# 看端禁止出现的隐藏列（供数 JSON / 表头 / 导出走白名单；本常量供测试与文档）
VIEW_EXPENSE_HIDDEN: list[str] = [
    "定位键",
    "收单月份",
    "归属月",
    "提单人",
    "提单人部门",
    "配音费合同号",
]

# 任务书37·B7：逐列筛选类型（日期列；金额列走 money.STD_MONEY_COLS）
DETAIL_DATE_COLS = frozenset(
    {
        "整单交付日期",
        "下单日期",
        "到账日期",
        "任务提交日期",
        "收单日期",
    }
)


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
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and lo != "":
                try:
                    v = float(lo)
                except (TypeError, ValueError):
                    continue
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
                    continue
                if col in money_cols:
                    fen = money.yuan_to_fen(v)
                    if fen is not None:
                        where.append(f"{col} <= ?")
                        args.append(fen)
                else:
                    where.append(f"CAST({col} AS REAL) <= ?")
                    args.append(v)
        elif kind == "date":
            d0, d1 = spec.get("from") or spec.get("start"), spec.get("to") or spec.get("end")
            if d0:
                where.append(f"substr(CAST({col} AS TEXT),1,10) >= ?")
                args.append(str(d0)[:10])
            if d1:
                where.append(f"substr(CAST({col} AS TEXT),1,10) <= ?")
                args.append(str(d1)[:10])
        else:
            # text：关键词 LIKE + 去重值 IN（多选）
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
    return where, args


def adjustable_fields() -> dict[str, list[str]]:
    """{表键: 可调整字段列表}——R1：由 schema 黑名单制自动推导，管理员端字段下拉从服务端下发。"""
    return {k: list(schema.ADJUSTABLE_FIELDS[v[0]]) for k, v in DETAIL_TABLES.items()}


# 异常清单的 WHERE 口径（异常处理中心与排名「（未填）」/体检「未填分类」共用，改一处两边同步）
UNCLASSIFIED_WHERE = "(对应报表大类 IS NULL OR TRIM(对应报表大类)='') AND 含税金额 IS NOT NULL AND 含税金额<>0"
UNFILLED_DEPT_WHERE = "(部门 IS NULL OR TRIM(部门)='') AND 下单预估额 IS NOT NULL AND 下单预估额<>0"


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
    elif month:
        where.append("归属月=?")
        args.append(month)
    elif year:
        y = str(year).strip()
        if not (y.isdigit() and len(y) == 4):
            raise KeyError("year 须为 4 位数字")
        where.append("归属月 LIKE ?")
        args.append(f"{y}-%")
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
) -> dict:
    """明细分页查询（按年/月 + 关键词 + 可选 BU + 任务书37 列筛）。仅读未删除行。表键白名单防注入。
    unclassified=True 仅「费用明细」：对应报表大类为空且金额非零。
    unfilled_dept=True 仅「下单」：部门为空且金额非零。
    year=YYYY → 归属月 LIKE 'YYYY-%'（A5 年维度）；month 仍为完整归属月 YYYY-MM。
    month_from/month_to：归属月闭区间（任务书41·E 真筛，SQL BETWEEN）。
    bu=非空 → 费用明细 业务BU 精确匹配（A5 BU 隔离，调用方负责鉴权后再传入）。
    filters：{列: {q/in/min/max/from/to}}，后端 SQL AND，禁止前端拉全表。
    hide_salary：费用明细隐藏对应报表大类=工资（整体账号默认）。
    audience：admin=管理端全列；view/view_bu=看端白名单（任务书41·D）。"""
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
    page_size = max(1, min(500, int(page_size)))
    offset = (page - 1) * page_size
    coln = ",".join(cols)
    rows = conn.execute(
        f"SELECT {coln} FROM {table} WHERE {wsql} ORDER BY id LIMIT ? OFFSET ?", args + [page_size, offset]
    ).fetchall()
    # 管理端明细：金额列转元 float 展示（录入/阅读习惯=元；库内仍是分）
    money_cols = set(money.STD_MONEY_COLS.get(table) or ())
    out_rows = []
    for r in rows:
        d = dict(zip(cols, r))
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


# ---------------- 配置变更留痕（C3·只追加·永不清空；不存密码等敏感值）----------------
CONFIG_CHANGE_CATEGORIES = ("销售归属", "BU配置", "分摊", "账号", "设置", "密码", "更新")


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
    return [dict(zip(cols, r)) for r in rows]


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


def _now() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 调整记录（写：明细编辑；管理员端 /api/adjust）----------------
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
    out = [dict(zip(cols, r)) for r in rows]
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


# ---------------- 手填（写：留痕 manual_历史；管理员端 /api/manual）----------------
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


# ---------- 费用去税率（陆总0714·按费用类别手填，默认0=不去税） ----------
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
        out = [dict(zip(cols, r)) for r in rows]
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
        out = [dict(zip(cols, r)) for r in rows]
    for d in out:
        if d.get("金额") is not None:
            d["金额"] = money.fen_to_yuan(d["金额"])
    return out


# ---------------- 年度预算 / 业务目标（写：留痕 manual_预算历史；管理员端 /api/budget）----------------
# 经营目标（金额/毛利率%）+ 部门费用管控；H1=上半年目标
BUDGET_METRICS = (
    "下单年预算",
    "回款年预算",
    "毛利率年目标",
    "下单H1目标",
    "回款H1目标",
    "毛利率H1目标",
    # A4·陆总#3：新增税前利润率目标（勿改既有键名）
    "税前利润率年目标",
    "税前利润率H1目标",
    "费用年预算",
)
# 比率指标不得走 yuan_to_fen（见 money.BUDGET_RATE_METRICS）
BUDGET_RATE_METRICS = money.BUDGET_RATE_METRICS


def load_budget(conn: sqlite3.Connection, scope: str = "全公司") -> dict[str, dict]:
    """{年份: {指标: 金额分 或 比率百分数}}。比率≠钱，见 BUDGET_RATE_METRICS。"""
    out: dict[str, dict] = {}
    for 年份, 指标, 金额 in conn.execute(
        "SELECT 年份,指标,金额 FROM manual_预算 WHERE 范围=? AND 指标<>'费用年预算'", (scope,)
    ).fetchall():
        if 年份 is None or 指标 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(指标)] = money.budget_value_from_store(str(指标), 金额)
    return out


def load_dept_budget(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """{年份: {部门: 金额分}}，取 指标='费用年预算' 且 范围≠全公司 的行。"""
    out: dict[str, dict[str, int]] = {}
    for 年份, 范围, 金额 in conn.execute(
        "SELECT 年份,范围,金额 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'"
    ).fetchall():
        if 年份 is None or 范围 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(范围)] = int(金额)
    return out


def list_budget_depts(conn: sqlite3.Connection) -> list[str]:
    """部门费用预算矩阵的行清单：台账里实际出现过的预算归属部门 ∪ 已填过预算的部门（不硬编码）。"""
    depts = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT 预算归属部门 FROM std_费用明细 WHERE 已删除=0 AND 预算归属部门 IS NOT NULL AND TRIM(预算归属部门)<>''"
        )
    }
    depts |= {
        r[0] for r in conn.execute("SELECT DISTINCT 范围 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'")
    }
    return sorted(depts)


def get_budget(conn: sqlite3.Connection, year: str | None = None) -> list[dict]:
    cols = ["年份", "指标", "范围", "金额", "填写时间", "经手人"]
    if year:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_预算 WHERE 年份=? ORDER BY 指标", (str(year),)
        ).fetchall()
    else:
        rows = conn.execute(f"SELECT {','.join(cols)} FROM manual_预算 ORDER BY 年份,指标").fetchall()
    out = [dict(zip(cols, r)) for r in rows]
    for d in out:
        if d.get("金额") is not None:
            # 管理端：金额→元；比率→百分数
            d["金额"] = money.budget_value_from_store(str(d.get("指标") or ""), d["金额"])
            if str(d.get("指标") or "") not in BUDGET_RATE_METRICS:
                d["金额"] = money.fen_to_yuan(d["金额"])
    return out


def set_budget(conn: sqlite3.Connection, 年份: str, 指标: str, 金额: float, 经手人: str, 范围: str = "全公司") -> None:
    """写年度预算。金额入参元→分；比率入参百分数→百分位点（绝不用 yuan_to_fen）。"""
    old = conn.execute("SELECT 金额 FROM manual_预算 WHERE 年份=? AND 指标=? AND 范围=?", (年份, 指标, 范围)).fetchone()
    旧值 = old[0] if old else None
    now = _now()
    stored = money.budget_value_to_store(str(指标), 金额)
    conn.execute(
        "INSERT INTO manual_预算历史(时间,经手人,年份,指标,范围,旧值,新值) VALUES(?,?,?,?,?,?,?)",
        (now, 经手人, 年份, 指标, 范围, 旧值, stored),
    )
    conn.execute(
        "INSERT OR REPLACE INTO manual_预算(年份,指标,范围,金额,填写时间,经手人) VALUES(?,?,?,?,?,?)",
        (年份, 指标, 范围, stored, now, 经手人),
    )
    conn.commit()


def latest_run(conn: sqlite3.Connection) -> dict | None:
    """最近一次运行日志（体检状态条数据源）。"""
    row = conn.execute("SELECT 时间,触发方式,结果,体检JSON FROM meta_运行日志 ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    import json as _json

    时间, 触发方式, 结果, 体检JSON = row
    try:
        体检 = _json.loads(体检JSON) if 体检JSON else {}
    except (ValueError, TypeError):
        体检 = {}
    return {"时间": 时间, "触发方式": 触发方式, "结果": 结果, "体检": 体检}
