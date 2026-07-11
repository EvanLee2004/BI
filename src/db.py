#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板.db 访问层：连接、建表、读标准表/手填表。

设计要点：
- 读回层**刻意返回与旧 loaders 完全相同的结构**，让 profit/columns/periods 原样计算，守刀1回归红线：
  * 智云四源 → list[dict]，键=config.columns 里的源列名（如「整单交付日期」「交付额/本币」）；
  * 收单台账 → (表头行, 数据行)，与 loaders.load_ledger 同形（逐行原样、含空行，保证行数一致）；
  * 手填 → {'YYYY-MM': {项目: 金额float}}，与 loaders.load_manual 同形。
- 金额存 REAL，读回后 profit.parse_amount(float) 与旧 parse_amount(str) 数值等价（已用回归脚本逐数字验证）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import loaders
import schema

DB_DEFAULT_REL = "看板.db"


def db_path(cfg: dict, root: Path | None = None) -> Path:
    """看板.db 路径：config.db_path（相对数据目录）或默认 数据/看板.db。"""
    rel = cfg.get("db_path", DB_DEFAULT_REL)
    p = Path(rel)
    if p.is_absolute():
        return p
    return loaders.data_dir(cfg, root) / rel


def connect(cfg: dict, root: Path | None = None) -> sqlite3.Connection:
    path = db_path(cfg, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys=ON")
    schema.create_all(conn)
    return conn


# ---------------- 读标准表 → loaders 同构 ----------------
def load_project_detail(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, str]]:
    c = cfg["columns"]
    rows = conn.execute(
        "SELECT 订单号,客户,业务线,销售,整单交付日期,交付额,项目成本 FROM std_收入明细 WHERE 已删除=0 ORDER BY id").fetchall()
    out = []
    for 订单号, 客户, 业务线, 销售, 交付日期, 交付额, 项目成本 in rows:
        out.append({
            "订单号": _s(订单号), "客户": _s(客户), "业务线": _s(业务线), "销售": _s(销售),
            c["project_delivery_date"]: _s(交付日期),
            c["project_revenue"]: 交付额,
            c["project_cost"]: 项目成本,
        })
    return out


def load_orders(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute("SELECT 下单日期,下单预估额,订单号,部门,销售 FROM std_下单 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["order_date"]: _s(d), c["order_amount"]: a, "订单号": _s(o), "部门": _s(dep), "销售": _s(sal)}
            for d, a, o, dep, sal in rows]


def load_receipts(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute("SELECT 到账日期,到账金额,回款ID,客户,销售 FROM std_回款 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["receipt_date"]: _s(d), c["receipt_amount"]: a, "回款记录ID": _s(rid), "客户": _s(cu), "销售": _s(sal)}
            for d, a, rid, cu, sal in rows]


def load_inhouse(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute(
        "SELECT 任务提交日期,结算金额,译员类型,任务ID,销售 FROM std_内部译员 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["inhouse_date"]: _s(d), c["inhouse_amount"]: a, c["inhouse_type"]: _s(t), "任务明细ID": _s(tid), "销售": _s(sal)}
            for d, a, t, tid, sal in rows]


# 台账列在标准表里的固定顺序（读回时据此拼回 (表头, 数据行)）
LEDGER_STD_COLS = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门"]


def load_ledger(cfg: dict, conn: sqlite3.Connection) -> tuple[list, list[tuple]]:
    """返回 (表头行, 数据行)，与 loaders.load_ledger 同形。含税金额列返回 REAL（float）。
    逐行原样（含全空行）按 id 顺序返回，保证行数与旧读法一致（体检面板行数回归红线）。"""
    header = list(LEDGER_STD_COLS)
    rows = conn.execute(
        "SELECT 收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型,预算归属部门 FROM std_费用明细 WHERE 已删除=0 ORDER BY id"
    ).fetchall()
    # 值原样返回：文本列给 str（None→None 保留空行语义），金额列给 float/None
    body: list[tuple] = list(rows)
    return header, body


# ---------------- 读手填表 → loaders.load_manual 同构 ----------------
def load_manual(cfg: dict, conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for 归属月, 项目, 金额 in conn.execute("SELECT 归属月,项目,金额 FROM manual_手填").fetchall():
        if 归属月 is None or 项目 is None or 金额 is None:
            continue
        out.setdefault(str(归属月), {})[str(项目)] = float(金额)
    return out


def _s(v: Any) -> str:
    """标准表文本列读回：None→""（与旧 loaders 把空单元格转成 "" 一致）。"""
    return "" if v is None else str(v)


# ---------------- 明细查询（管理员端 /api/detail）----------------
# 表键 → (物理表, 展示列, 可搜索文本列)
DETAIL_TABLES: dict[str, tuple[str, list[str], list[str]]] = {
    "收入明细": ("std_收入明细", ["定位键", "订单号", "客户", "业务线", "销售", "整单交付日期", "交付额", "项目成本", "归属月"],
                ["订单号", "客户", "业务线", "销售"]),
    "下单": ("std_下单", ["定位键", "订单号", "下单日期", "下单预估额", "部门", "销售", "归属月"], ["订单号", "部门", "销售"]),
    "回款": ("std_回款", ["定位键", "回款ID", "到账日期", "到账金额", "客户", "销售", "归属月"], ["回款ID", "客户", "销售"]),
    "内部译员": ("std_内部译员", ["定位键", "任务ID", "任务提交日期", "结算金额", "译员类型", "销售", "归属月"], ["任务ID", "译员类型", "销售"]),
    "费用明细": ("std_费用明细", ["定位键", "收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门", "归属月"],
                ["业务BU", "对应报表大类", "预算明细费用类型"]),
}


def adjustable_fields() -> dict[str, list[str]]:
    """{表键: 可调整字段列表}——R1：由 schema 黑名单制自动推导，管理员端字段下拉从服务端下发。"""
    return {k: list(schema.ADJUSTABLE_FIELDS[v[0]]) for k, v in DETAIL_TABLES.items()}


# 异常清单的 WHERE 口径（异常处理中心与排名「（未填）」/体检「未填分类」共用，改一处两边同步）
UNCLASSIFIED_WHERE = "(对应报表大类 IS NULL OR TRIM(对应报表大类)='') AND 含税金额 IS NOT NULL AND 含税金额<>0"
UNFILLED_DEPT_WHERE = "(部门 IS NULL OR TRIM(部门)='') AND 下单预估额 IS NOT NULL AND 下单预估额<>0"


def query_detail(conn: sqlite3.Connection, table_key: str, month: str | None = None,
                 q: str | None = None, page: int = 1, page_size: int = 50,
                 unclassified: bool = False, unfilled_dept: bool = False) -> dict:
    """明细分页查询（带按月 + 关键词筛选）。仅读未删除行。表键须在白名单内（防注入）。
    unclassified=True 仅对「费用明细」有效：只返回「对应报表大类」为空且金额非零的行
    （= 页面"费用未分类（台账）"只读清单所列那批，提示到源头收单台账补填；口径与 build_unclassified_summary 一致）。
    unfilled_dept=True 仅对「下单」有效：只返回「部门」为空且金额非零的行
    （= 异常处理「下单未填部门」清单；口径与排名「（未填）」组一致，测试守卫）。"""
    if table_key not in DETAIL_TABLES:
        raise KeyError(f"未知明细表：{table_key}（可选：{list(DETAIL_TABLES)}）")
    table, cols, searchable = DETAIL_TABLES[table_key]
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
    if month:
        where.append("归属月=?")
        args.append(month)
    if q:
        like = "%" + q.strip() + "%"
        ors = " OR ".join(f"{c} LIKE ?" for c in searchable)
        where.append(f"({ors})")
        args += [like] * len(searchable)
    wsql = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {wsql}", args).fetchone()[0]
    page = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset = (page - 1) * page_size
    coln = ",".join(cols)
    rows = conn.execute(
        f"SELECT {coln} FROM {table} WHERE {wsql} ORDER BY id LIMIT ? OFFSET ?",
        args + [page_size, offset]).fetchall()
    return {
        "table": table_key, "columns": cols,
        "rows": [dict(zip(cols, r)) for r in rows],
        "total": total, "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def list_order_depts(conn: sqlite3.Connection) -> list[str]:
    """下单表里实际出现过的部门（非空去重，异常处理「下单未填部门」归类下拉用，不硬编码）。"""
    return sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT 部门 FROM std_下单 WHERE 已删除=0 AND 部门 IS NOT NULL AND TRIM(部门)<>''"))


def list_salespeople(conn: sqlite3.Connection) -> list[dict]:
    """四源「销售」去重汇总（管理端 BU 拖拽归属池）。
    返回 [{"name": 销售名, "rows": 四源合计行数}, …] 按行数降序、同名序。
    空/纯空白不算；名字 trim 后聚合。"""
    sql = """
    SELECT TRIM(销售) AS n, COUNT(*) AS c FROM (
      SELECT 销售 FROM std_收入明细 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
      UNION ALL
      SELECT 销售 FROM std_下单 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
      UNION ALL
      SELECT 销售 FROM std_回款 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
      UNION ALL
      SELECT 销售 FROM std_内部译员 WHERE 已删除=0 AND 销售 IS NOT NULL AND TRIM(销售)<>''
    ) GROUP BY TRIM(销售) ORDER BY c DESC, n COLLATE NOCASE
    """
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.OperationalError:
        # 极老库缺某表/列：降级空池，不炸管理端
        return []
    return [{"name": r[0], "rows": int(r[1])} for r in rows if r[0]]


def exceptions_summary(conn: sqlite3.Connection) -> dict:
    """异常处理中心「总览」计数（新增一类异常=这里加一个键+前端注册一张卡）。
    体检黄红/警不在此（运行信号留在顶栏体检条，总览只引用 /api/health）。"""
    n_dept = conn.execute(f"SELECT COUNT(*) FROM std_下单 WHERE 已删除=0 AND {UNFILLED_DEPT_WHERE}").fetchone()[0]
    n_uc = conn.execute(f"SELECT COUNT(*) FROM std_费用明细 WHERE 已删除=0 AND {UNCLASSIFIED_WHERE}").fetchone()[0]
    n_exp = conn.execute("SELECT COUNT(*) FROM adj_调整记录 WHERE 状态='过期疑似'").fetchone()[0]
    run = latest_run(conn) or {}
    n_missing = int(((run.get("体检") or {}).get("adjust") or {}).get("missing", 0) or 0)
    return {"order_unfilled_dept": n_dept, "expense_unclassified": n_uc,
            "adjust_expired": n_exp, "adjust_missing": n_missing}


def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 调整记录（写：明细编辑；管理员端 /api/adjust）----------------
def add_adjustment(conn: sqlite3.Connection, 经手人: str, 目标表: str, 定位键: str,
                   字段: str, 新值: str, 原因: str = "", 类型: str = "改值") -> int:
    """新增一条调整记录（状态=生效）。原值由服务端从库取。目标表/字段严格白名单（防注入）。
    定位键护栏：匹配 0 行拒（键不存在）、匹配多行拒（内容完全相同的重复行，改一条会波及全部——
    真实台账已实测有撞车行；R2 raw 批次层给行级定位后放开）。"""
    import schema
    if 目标表 not in schema.STD_TABLE_NAMES:
        raise ValueError(f"未知目标表：{目标表}")
    if 类型 not in ("改值", "剔除"):
        raise ValueError(f"未知类型：{类型}")
    matches = conn.execute(
        f"SELECT COUNT(*) FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()[0]
    if matches == 0:
        raise ValueError(f"定位键在 {目标表} 中不存在（或已删除）：{定位键}")
    if matches > 1:
        raise ValueError(
            f"该行与另外 {matches - 1} 行内容完全相同（定位键重复），暂不支持调整/剔除——"
            f"改一条会同时改动全部相同行。请先在源表里让这些行可区分（如备注加字），或等行级定位（R2）上线。")
    原值 = ""
    if 类型 == "改值":
        if 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
            raise ValueError(f"字段不可调整：{目标表}.{字段}")
        原值_raw = conn.execute(
            f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()[0]
        原值 = "" if 原值_raw is None else str(原值_raw)
    cur = conn.execute(
        "INSERT INTO adj_调整记录(创建时间,经手人,目标表,定位键,字段,原值,新值,原因,类型,状态)"
        " VALUES(?,?,?,?,?,?,?,?,?, '生效')",
        (_now(), 经手人, 目标表, 定位键, 字段 or "", 原值, str(新值), 原因, 类型))
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
    row = conn.execute(
        "SELECT 目标表,定位键,字段,类型,状态 FROM adj_调整记录 WHERE id=?", (adj_id,)).fetchone()
    if not row:
        raise ValueError(f"调整不存在：id={adj_id}")
    目标表, 定位键, 字段, 类型, 状态 = row
    if 状态 != "过期疑似":
        raise ValueError("仅「过期疑似」的调整可坚持（生效中无需处理，已撤销请重新添加）")
    if 类型 != "改值":
        raise ValueError("仅「改值」类调整可坚持（剔除类过期疑似=同键重复行，请人工处理）")
    if 目标表 not in schema.STD_TABLE_NAMES or 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
        raise ValueError(f"字段不可调整：{目标表}.{字段}")
    cur = conn.execute(
        f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()
    if cur is None:
        raise ValueError("源头行已不存在，无法坚持——只能撤销该调整")
    源头现值 = "" if cur[0] is None else str(cur[0])
    conn.execute("UPDATE adj_调整记录 SET 原值=?, 状态='生效' WHERE id=?", (源头现值, adj_id))
    conn.commit()


def list_adjustments(conn: sqlite3.Connection) -> list[dict]:
    cols = ["id", "创建时间", "经手人", "目标表", "定位键", "字段", "原值", "新值", "原因", "类型", "状态"]
    rows = conn.execute(f"SELECT {','.join(cols)} FROM adj_调整记录 ORDER BY id DESC").fetchall()
    return [dict(zip(cols, r)) for r in rows]


# ---------------- 手填（写：留痕 manual_历史；管理员端 /api/manual）----------------
def get_manual(conn: sqlite3.Connection, month: str | None = None) -> list[dict]:
    cols = ["归属月", "项目", "金额", "填写时间", "经手人"]
    if month:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_手填 WHERE 归属月=? ORDER BY 项目", (month,)).fetchall()
    else:
        rows = conn.execute(f"SELECT {','.join(cols)} FROM manual_手填 ORDER BY 归属月,项目").fetchall()
    return [dict(zip(cols, r)) for r in rows]


def set_manual(conn: sqlite3.Connection, 归属月: str, 项目: str, 金额: float, 经手人: str) -> None:
    """写手填：先记 manual_历史（旧值→新值），再 REPLACE 覆盖 manual_手填。"""
    old = conn.execute("SELECT 金额 FROM manual_手填 WHERE 归属月=? AND 项目=?", (归属月, 项目)).fetchone()
    旧值 = old[0] if old else None
    now = _now()
    conn.execute("INSERT INTO manual_历史(时间,经手人,归属月,项目,旧值,新值) VALUES(?,?,?,?,?,?)",
                 (now, 经手人, 归属月, 项目, 旧值, float(金额)))
    conn.execute("INSERT OR REPLACE INTO manual_手填(归属月,项目,金额,填写时间,经手人) VALUES(?,?,?,?,?)",
                 (归属月, 项目, float(金额), now, 经手人))
    conn.commit()


# ---------------- 年度预算（写：留痕 manual_预算历史；管理员端 /api/budget）----------------
BUDGET_METRICS = ("下单年预算", "回款年预算", "费用年预算")  # 指标白名单（陆总0708拍板：只做这两个经营目标数）


def load_budget(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """{年份: {指标: 金额}}，只取范围=全公司（BU 预算数据结构已留位、呈现后置）。"""
    out: dict[str, dict[str, float]] = {}
    for 年份, 指标, 金额 in conn.execute(
            "SELECT 年份,指标,金额 FROM manual_预算 WHERE 范围='全公司'").fetchall():
        if 年份 is None or 指标 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(指标)] = float(金额)
    return out


def load_dept_budget(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """{年份: {部门: 金额}}，取 指标='费用年预算' 且 范围≠全公司 的行（部门费用预算执行卡用）。"""
    out: dict[str, dict[str, float]] = {}
    for 年份, 范围, 金额 in conn.execute(
            "SELECT 年份,范围,金额 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'").fetchall():
        if 年份 is None or 范围 is None or 金额 is None:
            continue
        out.setdefault(str(年份), {})[str(范围)] = float(金额)
    return out


def list_budget_depts(conn: sqlite3.Connection) -> list[str]:
    """部门费用预算矩阵的行清单：台账里实际出现过的预算归属部门 ∪ 已填过预算的部门（不硬编码）。"""
    depts = {r[0] for r in conn.execute(
        "SELECT DISTINCT 预算归属部门 FROM std_费用明细 WHERE 已删除=0 AND 预算归属部门 IS NOT NULL AND TRIM(预算归属部门)<>''")}
    depts |= {r[0] for r in conn.execute(
        "SELECT DISTINCT 范围 FROM manual_预算 WHERE 指标='费用年预算' AND 范围<>'全公司'")}
    return sorted(depts)


def get_budget(conn: sqlite3.Connection, year: str | None = None) -> list[dict]:
    cols = ["年份", "指标", "范围", "金额", "填写时间", "经手人"]
    if year:
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM manual_预算 WHERE 年份=? ORDER BY 指标", (str(year),)).fetchall()
    else:
        rows = conn.execute(f"SELECT {','.join(cols)} FROM manual_预算 ORDER BY 年份,指标").fetchall()
    return [dict(zip(cols, r)) for r in rows]


def set_budget(conn: sqlite3.Connection, 年份: str, 指标: str, 金额: float, 经手人: str,
               范围: str = "全公司") -> None:
    """写年度预算：先记 manual_预算历史（旧值→新值），再 REPLACE 覆盖（年中改数留痕可查）。"""
    old = conn.execute("SELECT 金额 FROM manual_预算 WHERE 年份=? AND 指标=? AND 范围=?",
                       (年份, 指标, 范围)).fetchone()
    旧值 = old[0] if old else None
    now = _now()
    conn.execute("INSERT INTO manual_预算历史(时间,经手人,年份,指标,范围,旧值,新值) VALUES(?,?,?,?,?,?,?)",
                 (now, 经手人, 年份, 指标, 范围, 旧值, float(金额)))
    conn.execute("INSERT OR REPLACE INTO manual_预算(年份,指标,范围,金额,填写时间,经手人) VALUES(?,?,?,?,?,?)",
                 (年份, 指标, 范围, float(金额), now, 经手人))
    conn.commit()


def latest_run(conn: sqlite3.Connection) -> dict | None:
    """最近一次运行日志（体检状态条数据源）。"""
    row = conn.execute(
        "SELECT 时间,触发方式,结果,体检JSON FROM meta_运行日志 ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    import json as _json
    时间, 触发方式, 结果, 体检JSON = row
    try:
        体检 = _json.loads(体检JSON) if 体检JSON else {}
    except (ValueError, TypeError):
        体检 = {}
    return {"时间": 时间, "触发方式": 触发方式, "结果": 结果, "体检": 体检}
