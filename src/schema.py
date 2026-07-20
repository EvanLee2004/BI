#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板.db 唯一表定义（建表 SQL + 字段常量都从这里出，杜绝三处各自解析的旧病）。

约定（03 详细设计 一 · 任务书33·A3 修订）：
- **金额一律 INTEGER 分**（进料口元→Decimal 四舍五入）。
- **算账层 profit 全程 int 分**；显示层（fmt_wan 等）最后一步转万元串。
- 日期一律 TEXT ISO；归属月 TEXT `YYYY-MM`。
- **标准表（std_*）每次更新全量重建**；定位键在 normalize 用**元**算出后再转分入库。
- **人工表重建时永不清空**；金额列同为分。
- **adj 金额 原值/新值 TEXT 存分字符串**（v3 起；管理端列表转元展示）。
- **预算比率指标**（毛利率/税前利润率）存百分位点，不用 yuan_to_fen。
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3  # 1→2：金额列元→分；2→3：adj 金额 原值/新值 元文本→分文本

# ---- 标准数据表（程序生成·每次全量重建·永不手改） ----
# 金额列 INTEGER 分；db.load 返回 int 分给 profit。
# 公共尾列：原值_归属月 / 已删除
STD_TABLES: dict[str, str] = {
    "std_收入明细": """
        CREATE TABLE IF NOT EXISTS std_收入明细 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,                 -- SOD（明细行级）；见 04_设计变更_定位键策略
            订单号 TEXT, 客户 TEXT, 业务线 TEXT, 销售 TEXT,
            整单交付日期 TEXT, 交付额 INTEGER, 项目成本 INTEGER,
            归属月 TEXT,
            原值_交付日期 TEXT,          -- 规范化前的原始交付日期（重放不改）
            原值_归属月 TEXT,
            已删除 INTEGER DEFAULT 0
        )""",
    "std_下单": """
        CREATE TABLE IF NOT EXISTS std_下单 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            订单号 TEXT, 下单日期 TEXT, 下单预估额 INTEGER, 部门 TEXT, 销售 TEXT, 客户 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_回款": """
        CREATE TABLE IF NOT EXISTS std_回款 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            回款ID TEXT, 到账日期 TEXT, 到账金额 INTEGER, 客户 TEXT, 销售 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_内部译员": """
        CREATE TABLE IF NOT EXISTS std_内部译员 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            任务ID TEXT, 任务提交日期 TEXT, 结算金额 INTEGER, 译员类型 TEXT,
            译员姓名 TEXT, 销售 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_费用明细": """
        CREATE TABLE IF NOT EXISTS std_费用明细 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            收单月份 TEXT, 收单日期 TEXT, 含税金额 INTEGER,
            业务BU TEXT, 对应报表大类 TEXT, 预算明细费用类型 TEXT,
            预算归属部门 TEXT,
            事项 TEXT, 提单人 TEXT, 提单人部门 TEXT, 业务员 TEXT, 配音费合同号 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
}

# R1 全字段可调=黑名单制：可调整字段 = 各 std 表全部列 − 黑名单（派生/系统字段锁死）。
# 黑名单：id（主键）、定位键（调整匹配索引）、归属月（由日期字段派生）、原值_*（重放基准）、已删除（软删标记）。
# 重放先把 std 重建成原始值，故重放当刻"当前值"即原始值；日期改值会连带重算 归属月（PERIOD_DATE_FIELD）。
NON_ADJUSTABLE = ("id", "定位键", "归属月", "已删除")


def _std_columns() -> dict[str, list[str]]:
    """从 STD_TABLES 的 DDL 推导各表全部列名（按建表顺序）。"""
    conn = sqlite3.connect(":memory:")
    try:
        cols: dict[str, list[str]] = {}
        for name, ddl in STD_TABLES.items():
            conn.execute(ddl)
            cols[name] = [r[1] for r in conn.execute(f"PRAGMA table_info({name})")]
        return cols
    finally:
        conn.close()


ADJUSTABLE_FIELDS: dict[str, tuple[str, ...]] = {
    t: tuple(c for c in cols if c not in NON_ADJUSTABLE and not c.startswith("原值_"))
    for t, cols in _std_columns().items()
}

# 各标准表"归属月由哪个日期字段决定"——改值改了该日期字段就要重算归属月
PERIOD_DATE_FIELD: dict[str, str] = {
    "std_收入明细": "整单交付日期",
    "std_下单": "下单日期",
    "std_回款": "到账日期",
    "std_内部译员": "任务提交日期",
}

# ---- 人工数据表（重建时永不清空） ----
HUMAN_TABLES: dict[str, str] = {
    "adj_调整记录": """
        CREATE TABLE IF NOT EXISTS adj_调整记录 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            创建时间 TEXT, 经手人 TEXT,
            目标表 TEXT, 定位键 TEXT, 字段 TEXT,
            原值 TEXT, 新值 TEXT, 原因 TEXT,
            类型 TEXT CHECK(类型 IN ('改值','剔除')),
            状态 TEXT DEFAULT '生效' CHECK(状态 IN ('生效','过期疑似','已撤销'))
        )""",
    "manual_手填": """
        CREATE TABLE IF NOT EXISTS manual_手填 (
            归属月 TEXT, 项目 TEXT, 金额 INTEGER, 填写时间 TEXT, 经手人 TEXT,
            PRIMARY KEY (归属月, 项目)
        )""",
    # 按 BU 范围手填（与全公司 manual_手填 并存；公司页仍用全公司表）
    "manual_手填BU": """
        CREATE TABLE IF NOT EXISTS manual_手填BU (
            归属月 TEXT, 范围 TEXT, 项目 TEXT, 金额 INTEGER, 填写时间 TEXT, 经手人 TEXT,
            PRIMARY KEY (归属月, 范围, 项目)
        )""",
    # 公共费用分摊比例（迭代20·按月）：每月每 BU 一行 0~100 百分数；无行=该月该 BU 不分摊
    "manual_分摊比例": """
        CREATE TABLE IF NOT EXISTS manual_分摊比例 (
            归属月 TEXT, BU TEXT, 比例 REAL, 填写时间 TEXT, 经手人 TEXT,
            PRIMARY KEY (归属月, BU)
        )""",
    "manual_费用去税率": """
        CREATE TABLE IF NOT EXISTS manual_费用去税率 (
            费用类别 TEXT PRIMARY KEY, 税率 REAL, 填写时间 TEXT, 经手人 TEXT
        )""",
    "manual_历史": """
        CREATE TABLE IF NOT EXISTS manual_历史 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 经手人 TEXT,
            归属月 TEXT, 项目 TEXT, 旧值 INTEGER, 新值 INTEGER
        )""",
    # 任务书63·H-04：分摊比例/去税率写删只追加历史（对齐 manual_历史；生效表仍可 DELETE）
    "manual_分摊比例历史": """
        CREATE TABLE IF NOT EXISTS manual_分摊比例历史 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 经手人 TEXT,
            归属月 TEXT, BU TEXT, 旧值 REAL, 新值 REAL
        )""",
    "manual_去税率历史": """
        CREATE TABLE IF NOT EXISTS manual_去税率历史 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 经手人 TEXT,
            费用类别 TEXT, 旧值 REAL, 新值 REAL
        )""",
    "manual_预算": """
        CREATE TABLE IF NOT EXISTS manual_预算 (
            年份 TEXT, 指标 TEXT, 范围 TEXT DEFAULT '全公司',
            金额 INTEGER, 填写时间 TEXT, 经手人 TEXT,
            PRIMARY KEY (年份, 指标, 范围)
        )""",
    "manual_预算历史": """
        CREATE TABLE IF NOT EXISTS manual_预算历史 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 经手人 TEXT,
            年份 TEXT, 指标 TEXT, 范围 TEXT, 旧值 INTEGER, 新值 INTEGER
        )""",
    "meta_schema": """
        CREATE TABLE IF NOT EXISTS meta_schema (
            key TEXT PRIMARY KEY, value TEXT
        )""",
    "meta_运行日志": """
        CREATE TABLE IF NOT EXISTS meta_运行日志 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 触发方式 TEXT,
            结果 TEXT CHECK(结果 IN ('绿','黄','红')),
            体检JSON TEXT
        )""",
    # C3 配置变更留痕（迭代16）：管理端一切配置写接口都往这里追加一条人读摘要（只追加、永不清空、
    # 绝不存密码等敏感值——密码类只记「账号X改密码」不记内容）。供管理端「操作记录」页倒序回看。
    "manual_配置变更": """
        CREATE TABLE IF NOT EXISTS manual_配置变更 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 操作账号 TEXT, 类别 TEXT, 摘要 TEXT
        )""",
}

STD_TABLE_NAMES = tuple(STD_TABLES.keys())
HUMAN_TABLE_NAMES = tuple(HUMAN_TABLES.keys())


# 版本升级时给存量库补列（不丢人工表）：表 → [(列名, 列定义)]
_ADD_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "std_收入明细": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0"), ("销售", "TEXT")],
    "std_下单": [
        ("原值_归属月", "TEXT"),
        ("已删除", "INTEGER DEFAULT 0"),
        ("部门", "TEXT"),
        ("销售", "TEXT"),
        ("客户", "TEXT"),
    ],
    "std_回款": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0"), ("客户", "TEXT"), ("销售", "TEXT")],
    "std_内部译员": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0"), ("销售", "TEXT"), ("译员姓名", "TEXT")],
    "std_费用明细": [
        ("原值_归属月", "TEXT"),
        ("已删除", "INTEGER DEFAULT 0"),
        ("预算归属部门", "TEXT"),
        ("事项", "TEXT"),
        ("提单人", "TEXT"),
        ("提单人部门", "TEXT"),
        ("业务员", "TEXT"),
        ("配音费合同号", "TEXT"),
    ],
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """给存量库补齐后加的列（幂等）——升级 app 不清人工表。"""
    cur = conn.cursor()
    for table, cols in _ADD_COLUMNS.items():
        have = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in have:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


# 任务书64·D2：std 表覆盖性索引（只加速查询，不改结果）
STD_INDEXES: list[str] = [
    # 定位键（调整/重放/重复审计）
    "CREATE INDEX IF NOT EXISTS idx_std_收入明细_定位键 ON std_收入明细(定位键)",
    "CREATE INDEX IF NOT EXISTS idx_std_下单_定位键 ON std_下单(定位键)",
    "CREATE INDEX IF NOT EXISTS idx_std_回款_定位键 ON std_回款(定位键)",
    "CREATE INDEX IF NOT EXISTS idx_std_内部译员_定位键 ON std_内部译员(定位键)",
    "CREATE INDEX IF NOT EXISTS idx_std_费用明细_定位键 ON std_费用明细(定位键)",
    # (已删除, 归属月) 利润扫描主路径
    "CREATE INDEX IF NOT EXISTS idx_std_收入明细_删月 ON std_收入明细(已删除, 归属月)",
    "CREATE INDEX IF NOT EXISTS idx_std_下单_删月 ON std_下单(已删除, 归属月)",
    "CREATE INDEX IF NOT EXISTS idx_std_回款_删月 ON std_回款(已删除, 归属月)",
    "CREATE INDEX IF NOT EXISTS idx_std_内部译员_删月 ON std_内部译员(已删除, 归属月)",
    "CREATE INDEX IF NOT EXISTS idx_std_费用明细_删月 ON std_费用明细(已删除, 归属月)",
    # 明细筛选高频列
    "CREATE INDEX IF NOT EXISTS idx_std_收入明细_销售 ON std_收入明细(已删除, 销售)",
    "CREATE INDEX IF NOT EXISTS idx_std_收入明细_客户 ON std_收入明细(已删除, 客户)",
    "CREATE INDEX IF NOT EXISTS idx_std_下单_部门 ON std_下单(已删除, 部门)",
    "CREATE INDEX IF NOT EXISTS idx_std_下单_销售 ON std_下单(已删除, 销售)",
    "CREATE INDEX IF NOT EXISTS idx_std_回款_销售 ON std_回款(已删除, 销售)",
    "CREATE INDEX IF NOT EXISTS idx_std_回款_客户 ON std_回款(已删除, 客户)",
    "CREATE INDEX IF NOT EXISTS idx_std_费用明细_BU ON std_费用明细(已删除, 业务BU)",
    "CREATE INDEX IF NOT EXISTS idx_std_费用明细_部门 ON std_费用明细(已删除, 预算归属部门)",
]


def create_all(conn: sqlite3.Connection) -> None:
    """建齐所有表（幂等）+ 索引 + 给存量库补后加的列 + 金额分迁移 + 清掉已废弃表。"""
    cur = conn.cursor()
    for ddl in {**STD_TABLES, **HUMAN_TABLES}.values():
        cur.execute(ddl)
    for idx in STD_INDEXES:
        cur.execute(idx)
    _ensure_columns(conn)
    cur.execute("DROP TABLE IF EXISTS suspect_待确认")  # R0：可疑单机制整套删除，存量库顺手清表
    migrate_money_to_fen_if_needed(conn)
    conn.commit()


def _schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT value FROM meta_schema WHERE key='version'").fetchone()
        if row and str(row[0]).strip().isdigit():
            return int(row[0])
    except sqlite3.OperationalError:
        pass
    return 0


def _set_schema_version(conn: sqlite3.Connection, ver: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta_schema(key, value) VALUES('version', ?)",
        (str(ver),),
    )


def _db_file_path(conn: sqlite3.Connection):
    """主库文件路径；:memory: 或无文件 → None。"""
    from pathlib import Path

    for _seq, name, file in conn.execute("PRAGMA database_list"):
        if name == "main" and file:
            p = Path(file)
            if p.exists() and str(p) != ":memory:":
                return p
    return None


def _backup_db_before_migrate(conn: sqlite3.Connection) -> str | None:
    """迁移前多一份备份（同目录 看板.db.bak-fen-YYYYMMDDHHMMSS）。返回路径或 None。"""
    import datetime
    import shutil
    from pathlib import Path

    path = _db_file_path(conn)
    if path is None:
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    bak = path.with_name(f"{path.name}.bak-fen-{stamp}")
    try:
        # WAL 下尽量 checkpoint 再拷，避免丢尾部
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        shutil.copy2(path, bak)
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                shutil.copy2(side, Path(str(bak) + suffix))
        return str(bak)
    except OSError:
        return None


def _has_money_data(conn: sqlite3.Connection) -> bool:
    """是否已有金额类数据（无版本号时用于判定是否需按元→分迁移）。"""
    checks = [
        "SELECT 1 FROM std_收入明细 WHERE 交付额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM std_下单 WHERE 下单预估额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM std_回款 WHERE 到账金额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM std_内部译员 WHERE 结算金额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM std_费用明细 WHERE 含税金额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM manual_手填 WHERE 金额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM manual_手填BU WHERE 金额 IS NOT NULL LIMIT 1",
        "SELECT 1 FROM manual_预算 WHERE 金额 IS NOT NULL LIMIT 1",
    ]
    for sql in checks:
        try:
            if conn.execute(sql).fetchone():
                return True
        except sqlite3.OperationalError:
            continue
    return False


def _yuan_cell_to_fen(val) -> int | None:
    """存量 REAL 元 → 分（Decimal；已是极大整数且像分的不二次放大——仅迁移路径）。"""
    import money

    if val is None:
        return None
    # 已是 int 且无小数：生产库迁移前金额多为 float 元；若误已是分则不应再 *100。
    # 版本门控保证只跑一次，按元处理。
    return money.yuan_to_fen(val)


# 表 → 需元→分 的列
_MIGRATE_MONEY_COLS: dict[str, tuple[str, ...]] = {
    "std_收入明细": ("交付额", "项目成本"),
    "std_下单": ("下单预估额",),
    "std_回款": ("到账金额",),
    "std_内部译员": ("结算金额",),
    "std_费用明细": ("含税金额",),
    "manual_手填": ("金额",),
    "manual_手填BU": ("金额",),
    "manual_历史": ("旧值", "新值"),
    "manual_预算": ("金额",),
    "manual_预算历史": ("旧值", "新值"),
}


def _migrate_table_money_cols(conn: sqlite3.Connection, table: str, cols: tuple[str, ...]) -> int:
    """逐行把金额列从元 REAL 写成整数分。返回更新行数。一律用 rowid 定位，避免复合主键麻烦。"""
    try:
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return 0
    use = [c for c in cols if c in have]
    if not use:
        return 0
    rows = conn.execute(f"SELECT rowid, {','.join(use)} FROM {table}").fetchall()
    n = 0
    for row in rows:
        rid = row[0]
        sets = []
        args = []
        for c, v in zip(use, row[1:], strict=False):
            sets.append(f"{c}=?")
            args.append(_yuan_cell_to_fen(v))
        conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE rowid=?", args + [rid])
        n += 1
    return n


def _lookup_std_fen(conn: sqlite3.Connection, 目标表, 定位键, 字段) -> int | None:
    """取 std 现值作锚（有则用于判定纯整数是元还是分）。"""
    if not (目标表 and 定位键 and 字段):
        return None
    try:
        r = conn.execute(
            f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0 LIMIT 1",
            (定位键,),
        ).fetchone()
        if r is not None and r[0] is not None:
            return int(r[0])
    except sqlite3.OperationalError:
        pass
    return None


def _adj_side_to_fen(text, cur_fen, money) -> tuple:
    """单侧 原值/新值 元文本→分文本；(new_text, changed)。"""
    if text is None:
        return None, False
    s = str(text).strip()
    if s == "":
        return "", False
    # 有小数 → 元
    if "." in s or "e" in s.lower():
        return money.yuan_text_to_fen_text(s), True
    try:
        iv = int(float(s))
    except (ValueError, TypeError):
        return s, False
    # 纯整数：若 iv*100 == cur_fen → 元；若 iv == cur_fen → 已是分
    if cur_fen is not None:
        if iv == cur_fen:
            return s, False  # already fen
        if iv * 100 == cur_fen:
            return str(iv * 100), True
    # 无锚：按元转分（存量部署机 adj 均为元）
    return money.yuan_text_to_fen_text(s), True


def _migrate_adj_amount_texts(conn: sqlite3.Connection) -> int:
    """adj 金额字段 原值/新值：元文本 → 分文本。幂等：已是分（与 std 现值一致）则跳过该侧。

    判定：字段∈金额名；有小数点 → 必为元；纯整数则 yuan_to_fen 与 as-fen 双解，
    若按元×100 后与同定位键 std 现值一致则按元迁移，否则视为已是分。
    """
    import money

    try:
        rows = conn.execute(
            "SELECT id,目标表,定位键,字段,原值,新值 FROM adj_调整记录"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    n = 0
    for aid, 目标表, 定位键, 字段, 原值, 新值 in rows:
        if 字段 not in money.AMOUNT_FIELD_NAMES:
            continue
        cur_fen = _lookup_std_fen(conn, 目标表, 定位键, 字段)
        new_o, ch_o = _adj_side_to_fen(原值, cur_fen, money)
        new_n, ch_n = _adj_side_to_fen(新值, cur_fen, money)
        if ch_o or ch_n:
            conn.execute(
                "UPDATE adj_调整记录 SET 原值=?, 新值=? WHERE id=?",
                (new_o if new_o is not None else 原值, new_n if new_n is not None else 新值, aid),
            )
            n += 1
    return n


def migrate_money_to_fen_if_needed(conn: sqlite3.Connection) -> dict:
    """schema 升级到 v3：金额列分 + adj 金额文本分。幂等；迁移前备份。

    v1→v2：std/manual 金额列 元 REAL → 分 INTEGER
    v2→v3：adj 金额 原值/新值 元 TEXT → 分 TEXT（修复存量调整失配）
    定位键仍在 normalize 用元计算，哈希不因分存储漂移。
    """
    ver = _schema_version(conn)
    if ver >= SCHEMA_VERSION:
        return {"status": "skip", "version": ver, "backup": None}

    # 无版本标记且无金额数据 = 新建空库
    if ver == 0 and not _has_money_data(conn):
        _set_schema_version(conn, SCHEMA_VERSION)
        return {"status": "init", "version": SCHEMA_VERSION, "backup": None}

    bak = _backup_db_before_migrate(conn)
    updated = {}
    if ver < 2:
        for table, cols in _MIGRATE_MONEY_COLS.items():
            updated[table] = _migrate_table_money_cols(conn, table, cols)
    # v2 或从 v1 上来：都要做 adj 文本迁移
    updated["adj_调整记录"] = _migrate_adj_amount_texts(conn)
    _set_schema_version(conn, SCHEMA_VERSION)
    return {"status": "migrated", "version": SCHEMA_VERSION, "backup": bak, "updated": updated}


def reset_std_tables(conn: sqlite3.Connection, *, commit: bool = False) -> None:
    """清空标准表（全量重建前）；人工表绝不动。

    默认**不 commit**（任务书33·A1）：清表+插入必须与 _rebuild_std 同事务，
    中途崩溃不得留下空 std。调用方在整批成功后一次 COMMIT。
    commit=True 仅兼容极少数「只要空表」的调用。
    """
    cur = conn.cursor()
    for name in STD_TABLE_NAMES:
        cur.execute(f"DELETE FROM {name}")
    # 释放 AUTOINCREMENT 计数，避免 id 无限增长（sqlite_sequence 可能不存在）
    try:
        cur.execute(
            "DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?" * len(STD_TABLE_NAMES)), STD_TABLE_NAMES
        )
    except sqlite3.OperationalError:
        pass
    if commit:
        conn.commit()
