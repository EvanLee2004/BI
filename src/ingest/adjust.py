#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调整记录重放 + 过期校验（03 详细设计 二·4 / 02 核心决策 #1）。

在标准表已用最新抓取重建（字段=原始值）之后调用：
- 遍历全部 `状态='生效'` 的调整，按 (目标表, 定位键, 字段) 贴回：
  * 类型='改值'：先做**过期校验**——库中现值（刚重建=原始值）与调整记录的 `原值` 不符 → 说明源头
    已自行修正，标该调整 `过期疑似`、**不套用**、体检黄；相符 → 套用 `新值`（改日期字段连带重算归属月）。
  * 类型='剔除'：把匹配行打 `已删除=1`（软删，不物理删）。
- 这样"重抓多少次、人工修正都不丢"，且天然形成审计台账。

金额天天变故定位键用稳定自然键（不含金额），重放才贴得回去——见 04_设计变更_定位键策略。
"""
from __future__ import annotations

import sqlite3

import loaders
import schema

_AMOUNT_FIELDS = {"交付额", "项目成本", "下单预估额", "到账金额", "结算金额", "含税金额"}

# 费用明细的归属月由 收单日期(优先)/收单月份(退回·配账年) 派生（口径=periods.ledger_row_date）；
# 改这两个字段要连带重算归属月（R1 开放全字段后补上，与智云四源的 PERIOD_DATE_FIELD 机制对应）
_LEDGER_DATE_FIELDS = {"收单日期", "收单月份"}


def _ledger_ym(收单日期, 收单月份, ledger_year: int) -> str | None:
    """费用明细归属月：优先收单日期，退回收单月份+账年——与 periods.ledger_row_date 同口径。"""
    parts = loaders.parse_date_parts(收单日期)
    if parts:
        return f"{parts[0]:04d}-{parts[1]:02d}"
    if 收单月份 not in (None, ""):
        try:
            return f"{ledger_year:04d}-{int(str(收单月份).strip()):02d}"
        except ValueError:
            return None
    return None


def _values_match(current, 原值: str) -> bool:
    """库中现值 与 调整记录的原值 是否一致（金额按数值容差、其余按去空白文本）。"""
    if 原值 is None:
        原值 = ""
    cs = "" if current is None else str(current).strip()
    os_ = str(原值).strip()
    # 数值型（现值可能是 REAL）：按容差比
    try:
        return abs(float(cs) - float(os_)) < 1e-6
    except (ValueError, TypeError):
        return cs == os_


def _cast(字段: str, 新值: str):
    if 字段 in _AMOUNT_FIELDS:
        return loaders.parse_amount(新值)
    return 新值


def apply_adjustments(conn: sqlite3.Connection, now: str) -> dict:
    """重放全部生效调整。返回 {applied, expired, removed, skipped, missing}。
    missing=定位键失配（源头行删了/键变了，台账键含金额、源头改金额即失配）——调整没套用但记录还在，
    必须冒泡到体检黄提醒人工复核，否则「剔除」会悄悄复活。"""
    applied = expired = removed = skipped = missing = 0
    rows = conn.execute(
        "SELECT id,目标表,定位键,字段,原值,新值,类型 FROM adj_调整记录 WHERE 状态='生效' ORDER BY id"
    ).fetchall()
    for aid, 目标表, 定位键, 字段, 原值, 新值, 类型 in rows:
        if 目标表 not in schema.STD_TABLE_NAMES:
            skipped += 1
            continue
        match_rows = conn.execute(
            f"SELECT id FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchall()
        if not match_rows:
            missing += 1  # 定位键在本次抓取里不存在（源头删了/键变了）——不动，留调整待人工看
            continue
        if len(match_rows) > 1:
            # 新批次出现同键重复行（写调整时是唯一的）→ 语义变模糊，按过期疑似标黄、不套用，留人工复核
            conn.execute("UPDATE adj_调整记录 SET 状态='过期疑似' WHERE id=?", (aid,))
            expired += 1
            continue

        if 类型 == "剔除":
            cur = conn.execute(f"UPDATE {目标表} SET 已删除=1 WHERE 定位键=? AND 已删除=0", (定位键,))
            removed += cur.rowcount
            continue

        # 类型='改值'：过期校验
        if 字段 not in schema.ADJUSTABLE_FIELDS.get(目标表, {}):
            skipped += 1
            continue
        # 现值取第一条匹配行（重放当刻=原始值）
        current = conn.execute(
            f"SELECT {字段} FROM {目标表} WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()[0]
        if not _values_match(current, 原值):
            conn.execute("UPDATE adj_调整记录 SET 状态='过期疑似' WHERE id=?", (aid,))
            expired += 1
            continue
        # 套用新值到所有匹配行
        conn.execute(f"UPDATE {目标表} SET {字段}=? WHERE 定位键=? AND 已删除=0", (_cast(字段, 新值), 定位键))
        # 若改的是驱动归属月的日期字段，连带重算归属月
        if schema.PERIOD_DATE_FIELD.get(目标表) == 字段:
            parts = loaders.parse_date_parts(新值)
            ym = f"{parts[0]:04d}-{parts[1]:02d}" if parts else None
            conn.execute(f"UPDATE {目标表} SET 归属月=? WHERE 定位键=? AND 已删除=0", (ym, 定位键))
        elif 目标表 == "std_费用明细" and 字段 in _LEDGER_DATE_FIELDS:
            d, m = conn.execute(
                "SELECT 收单日期,收单月份 FROM std_费用明细 WHERE 定位键=? AND 已删除=0", (定位键,)).fetchone()
            ym = _ledger_ym(d, m, int(now[:4]))  # 账年=本轮更新年（与 build_std_db 的 ledger_year 一致）
            conn.execute("UPDATE std_费用明细 SET 归属月=? WHERE 定位键=? AND 已删除=0", (ym, 定位键))
        applied += 1
    conn.commit()
    return {"applied": applied, "expired": expired, "removed": removed,
            "skipped": skipped, "missing": missing}
