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
        "SELECT 订单号,客户,业务线,整单交付日期,交付额,项目成本 FROM std_收入明细 WHERE 已删除=0 ORDER BY id").fetchall()
    out = []
    for 订单号, 客户, 业务线, 交付日期, 交付额, 项目成本 in rows:
        out.append({
            "订单号": _s(订单号), "客户": _s(客户), "业务线": _s(业务线),
            c["project_delivery_date"]: _s(交付日期),
            c["project_revenue"]: 交付额,
            c["project_cost"]: 项目成本,
        })
    return out


def load_orders(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute("SELECT 下单日期,下单预估额,订单号 FROM std_下单 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["order_date"]: _s(d), c["order_amount"]: a, "订单号": _s(o)} for d, a, o in rows]


def load_receipts(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute("SELECT 到账日期,到账金额,回款ID FROM std_回款 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["receipt_date"]: _s(d), c["receipt_amount"]: a, "回款记录ID": _s(rid)} for d, a, rid in rows]


def load_inhouse(cfg: dict, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    c = cfg["columns"]
    rows = conn.execute(
        "SELECT 任务提交日期,结算金额,译员类型,任务ID FROM std_内部译员 WHERE 已删除=0 ORDER BY id").fetchall()
    return [{c["inhouse_date"]: _s(d), c["inhouse_amount"]: a, c["inhouse_type"]: _s(t), "任务明细ID": _s(tid)}
            for d, a, t, tid in rows]


# 台账列在标准表里的固定顺序（读回时据此拼回 (表头, 数据行)）
LEDGER_STD_COLS = ["收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型"]


def load_ledger(cfg: dict, conn: sqlite3.Connection) -> tuple[list, list[tuple]]:
    """返回 (表头行, 数据行)，与 loaders.load_ledger 同形。含税金额列返回 REAL（float）。
    逐行原样（含全空行）按 id 顺序返回，保证行数与旧读法一致（体检面板行数回归红线）。"""
    header = list(LEDGER_STD_COLS)
    rows = conn.execute(
        "SELECT 收单月份,收单日期,含税金额,业务BU,对应报表大类,预算明细费用类型 FROM std_费用明细 WHERE 已删除=0 ORDER BY id"
    ).fetchall()
    # 值原样返回：文本列给 str（None→None 保留空行语义），金额列给 float/None
    body: list[tuple] = []
    for 月份, 日期, 金额, bu, 大类, 细类 in rows:
        body.append((月份, 日期, 金额, bu, 大类, 细类))
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
    "收入明细": ("std_收入明细", ["定位键", "订单号", "客户", "业务线", "整单交付日期", "交付额", "项目成本", "归属月"],
                ["订单号", "客户", "业务线"]),
    "下单": ("std_下单", ["定位键", "订单号", "下单日期", "下单预估额", "归属月"], ["订单号"]),
    "回款": ("std_回款", ["定位键", "回款ID", "到账日期", "到账金额", "归属月"], ["回款ID"]),
    "内部译员": ("std_内部译员", ["定位键", "任务ID", "任务提交日期", "结算金额", "译员类型", "归属月"], ["任务ID", "译员类型"]),
    "费用明细": ("std_费用明细", ["定位键", "收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "归属月"],
                ["业务BU", "对应报表大类", "预算明细费用类型"]),
}


def query_detail(conn: sqlite3.Connection, table_key: str, month: str | None = None,
                 q: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """明细分页查询（带按月 + 关键词筛选）。仅读未删除行。表键须在白名单内（防注入）。"""
    if table_key not in DETAIL_TABLES:
        raise KeyError(f"未知明细表：{table_key}（可选：{list(DETAIL_TABLES)}）")
    table, cols, searchable = DETAIL_TABLES[table_key]
    where = ["已删除=0"]
    args: list = []
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


def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 调整记录（写：明细编辑；管理员端 /api/adjust）----------------
def add_adjustment(conn: sqlite3.Connection, 经手人: str, 目标表: str, 定位键: str,
                   字段: str, 新值: str, 原因: str = "", 类型: str = "改值") -> int:
    """新增一条调整记录（状态=生效）。原值由服务端从库取。目标表/字段严格白名单（防注入）。"""
    import schema
    if 目标表 not in schema.STD_TABLE_NAMES:
        raise ValueError(f"未知目标表：{目标表}")
    if 类型 not in ("改值", "剔除"):
        raise ValueError(f"未知类型：{类型}")
    原值 = ""
    if 类型 == "改值":
        if 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
            raise ValueError(f"字段不可调整：{目标表}.{字段}")
        row = conn.execute(f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()
        if row is None:
            raise ValueError(f"定位键在 {目标表} 中不存在（或已删除）：{定位键}")
        原值 = "" if row[0] is None else str(row[0])
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


# ---------------- 可疑单（管理员端 /api/suspects）----------------
def list_suspects(conn: sqlite3.Connection, status: str = "待确认") -> list[dict]:
    cols = ["id", "发现时间", "目标表", "定位键", "规则", "摘要", "建议字段", "当前值", "状态"]
    rows = conn.execute(
        f"SELECT {','.join(cols)} FROM suspect_待确认 WHERE 状态=? ORDER BY id DESC", (status,)).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def resolve_suspect(conn: sqlite3.Connection, sid: int, action: str, 经手人: str,
                    新归属月: str | None = None) -> dict:
    """处理可疑单：'正常'→已确认正常；'调整'→代写一条调整记录把该行日期挪到 新归属月 末日、标已调整。"""
    import calendar
    import schema
    row = conn.execute("SELECT 目标表,定位键,规则 FROM suspect_待确认 WHERE id=?", (sid,)).fetchone()
    if not row:
        raise ValueError(f"可疑单不存在：{sid}")
    目标表, 定位键, _规则 = row
    if action == "正常":
        conn.execute("UPDATE suspect_待确认 SET 状态='已确认正常' WHERE id=?", (sid,))
        conn.commit()
        return {"action": "正常", "id": sid}
    if action == "调整":
        if not 新归属月 or len(新归属月) != 7:
            raise ValueError("调整需提供 新归属月（YYYY-MM）")
        date_field = schema.PERIOD_DATE_FIELD.get(目标表)
        if not date_field:
            raise ValueError(f"{目标表} 无可挪月的日期字段")
        y, m = int(新归属月[:4]), int(新归属月[5:7])
        新值 = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"  # 挪到该月最后一天
        aid = add_adjustment(conn, 经手人, 目标表, 定位键, date_field, 新值, f"可疑单挪月→{新归属月}", "改值")
        conn.execute("UPDATE suspect_待确认 SET 状态='已调整' WHERE id=?", (sid,))
        conn.commit()
        return {"action": "调整", "id": sid, "adj_id": aid, "新值": 新值}
    raise ValueError(f"未知处理动作：{action}")


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
