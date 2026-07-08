#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板.db 唯一表定义（建表 SQL + 字段常量都从这里出，杜绝三处各自解析的旧病）。

约定（03 详细设计 一）：
- 金额一律 REAL（元）；日期一律 TEXT，能解析的存 ISO `YYYY-MM-DD`，解析不出的存原文（归属月留空）；
  归属月 TEXT `YYYY-MM`。
- **标准表（std_*）每次更新全量重建、永不手改**；用自增 id 做主键（保证每源行一条、绝不塌行，
  守刀1回归红线）；`定位键`=内容哈希，仅作刀2调整匹配用的索引，不当主键（造数把同 ID 复制成 7 个
  月度变体、金额/日期各异，故 ID 不唯一——2026-07-08 首日核实结论，退行哈希）。
- **人工表（adj_/manual_/suspect_/meta_）重建时永不清空**。
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

# ---- 标准数据表（程序生成·每次全量重建·永不手改） ----
# 说明：金额列用干净内部名（去掉源表头里的 "/"，否则做不了 SQL 列名）；db.py 读回时映射回
# config.columns 里的源列名，交给 profit 原样计算（回归红线：改读库后数字与 v6-final 一分不差）。
# 公共尾列（所有标准表都带）：
#   原值_归属月 = 本次重抓的原始归属月（规范化即写、重放永不改）——供 diff 分级比对"周期是否变"。
#   已删除 = 剔除调整的软删标记（1=剔除，不物理删）；db 读回层按 已删除=0 过滤。
STD_TABLES: dict[str, str] = {
    "std_收入明细": """
        CREATE TABLE IF NOT EXISTS std_收入明细 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,                 -- SOD（明细行级）；见 04_设计变更_定位键策略
            订单号 TEXT, 客户 TEXT, 业务线 TEXT,
            整单交付日期 TEXT, 交付额 REAL, 项目成本 REAL,
            归属月 TEXT,
            原值_交付日期 TEXT,          -- 规范化前的原始交付日期（重放不改）
            原值_归属月 TEXT,
            已删除 INTEGER DEFAULT 0
        )""",
    "std_下单": """
        CREATE TABLE IF NOT EXISTS std_下单 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            订单号 TEXT, 下单日期 TEXT, 下单预估额 REAL,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_回款": """
        CREATE TABLE IF NOT EXISTS std_回款 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            回款ID TEXT, 到账日期 TEXT, 到账金额 REAL,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_内部译员": """
        CREATE TABLE IF NOT EXISTS std_内部译员 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            任务ID TEXT, 任务提交日期 TEXT, 结算金额 REAL, 译员类型 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
    "std_费用明细": """
        CREATE TABLE IF NOT EXISTS std_费用明细 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            定位键 TEXT,
            收单月份 TEXT, 收单日期 TEXT, 含税金额 REAL,
            业务BU TEXT, 对应报表大类 TEXT, 预算明细费用类型 TEXT,
            归属月 TEXT, 原值_归属月 TEXT, 已删除 INTEGER DEFAULT 0
        )""",
}

# 每张标准表：可被"改值"调整的字段 → 该字段规范化前原始值所在列（过期校验/重放用）。
# 重放先把 std 重建成原始值，故重放当刻"当前值"即原始值；日期改值会连带重算 归属月。
ADJUSTABLE_FIELDS: dict[str, dict[str, str]] = {
    "std_收入明细": {"整单交付日期": "原值_交付日期", "交付额": "交付额", "项目成本": "项目成本"},
    "std_下单": {"下单日期": "下单日期", "下单预估额": "下单预估额"},
    "std_回款": {"到账日期": "到账日期", "到账金额": "到账金额"},
    "std_内部译员": {"任务提交日期": "任务提交日期", "结算金额": "结算金额"},
    "std_费用明细": {"含税金额": "含税金额", "对应报表大类": "对应报表大类", "业务BU": "业务BU"},
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
            归属月 TEXT, 项目 TEXT, 金额 REAL, 填写时间 TEXT, 经手人 TEXT,
            PRIMARY KEY (归属月, 项目)
        )""",
    "manual_历史": """
        CREATE TABLE IF NOT EXISTS manual_历史 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 经手人 TEXT,
            归属月 TEXT, 项目 TEXT, 旧值 REAL, 新值 REAL
        )""",
    "suspect_待确认": """
        CREATE TABLE IF NOT EXISTS suspect_待确认 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            发现时间 TEXT, 目标表 TEXT, 定位键 TEXT,
            规则 TEXT,
            摘要 TEXT, 建议字段 TEXT, 当前值 TEXT,
            状态 TEXT DEFAULT '待确认' CHECK(状态 IN ('待确认','已确认正常','已调整'))
        )""",
    "meta_运行日志": """
        CREATE TABLE IF NOT EXISTS meta_运行日志 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            时间 TEXT, 触发方式 TEXT,
            结果 TEXT CHECK(结果 IN ('绿','黄','红')),
            体检JSON TEXT
        )""",
}

STD_TABLE_NAMES = tuple(STD_TABLES.keys())
HUMAN_TABLE_NAMES = tuple(HUMAN_TABLES.keys())


# 版本升级时给存量库补列（不丢人工表）：表 → [(列名, 列定义)]
_ADD_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "std_收入明细": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0")],
    "std_下单": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0")],
    "std_回款": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0")],
    "std_内部译员": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0")],
    "std_费用明细": [("原值_归属月", "TEXT"), ("已删除", "INTEGER DEFAULT 0")],
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """给存量库补齐后加的列（幂等）——升级 app 不清人工表。"""
    cur = conn.cursor()
    for table, cols in _ADD_COLUMNS.items():
        have = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in have:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def create_all(conn: sqlite3.Connection) -> None:
    """建齐所有表（幂等）+ 给存量库补后加的列。"""
    cur = conn.cursor()
    for ddl in {**STD_TABLES, **HUMAN_TABLES}.values():
        cur.execute(ddl)
    _ensure_columns(conn)
    conn.commit()


def reset_std_tables(conn: sqlite3.Connection) -> None:
    """清空标准表（每次更新全量重建前调用）；人工表绝不动。"""
    cur = conn.cursor()
    for name in STD_TABLE_NAMES:
        cur.execute(f"DELETE FROM {name}")
    # 释放 AUTOINCREMENT 计数，避免 id 无限增长（sqlite_sequence 可能不存在）
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN (%s)"
                    % ",".join("?" * len(STD_TABLE_NAMES)), STD_TABLE_NAMES)
    except sqlite3.OperationalError:
        pass
    conn.commit()
