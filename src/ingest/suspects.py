#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff 分级 + 可疑单规则（03 详细设计 二·3）。

- **diff 分级**（金额变覆盖·周期变进待确认）：对比上一次重抓的原始归属月——
  * 金额变（原始归属月没变）→ 无声用新值（重建即覆盖，不惊动人）；
  * 归属周期变（原始归属月跨月）→ 写 suspect_待确认(规则=PERIOD_SHIFT)，本轮按新值入库、等人工定夺。
- **可疑单规则 MONTH_EDGE_NIGHT**：本次新出现、且整单交付日期落在"月初 1 号"（收窄到当月）的收入明细行
  → 写待确认（陆总原型：0701 凌晨 3 笔单业务实属 6 月）。⚠ 智云导出交付日期为日期级（无时分），无法
  区分 00:00–12:00，退化为"当月 1 号交付"入队。

**唯一性护栏**：diff/可疑单只对"定位键唯一"的记录生效——定位键须稳定(自然键)且唯一，diff 才有意义。
当前测试数据把同一自然键 7× 复制成月度变体（定位键不唯一），这些行一律跳过（bulk 不真正演练 diff，机制靠
构造的唯一键用例验证，符合刀2验收"造用例"）；真实智云导出里这些 ID 唯一，机制照常。台账用不稳定内容哈希，
不参与 diff。见 04_设计变更_定位键策略。
"""
from __future__ import annotations

from collections import Counter
import sqlite3

import loaders

# 参与 PERIOD_SHIFT diff 的表（有稳定定位键；台账内容哈希不稳，跳过）
_DIFF_TABLES = ["std_收入明细", "std_下单", "std_回款", "std_内部译员"]


def snapshot_before_reset(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """重建前抓上一次的 {表: {定位键: 原值_归属月}}，**只保留唯一定位键**（非唯一无法一一对上，跳过）。"""
    snap: dict[str, dict[str, str]] = {}
    for t in _DIFF_TABLES:
        pairs = conn.execute(f"SELECT 定位键,原值_归属月 FROM {t} WHERE 定位键 IS NOT NULL").fetchall()
        cnt = Counter(k for k, _ in pairs)
        snap[t] = {k: v for k, v in pairs if cnt[k] == 1}
    return snap


def _has_resolved(conn, 目标表: str, 定位键: str, 规则: str) -> bool:
    """该(表,定位键,规则)是否已有人工处理过的记录（已确认正常/已调整）——有则不再重复入队骚扰。"""
    n = conn.execute(
        "SELECT COUNT(*) FROM suspect_待确认 WHERE 目标表=? AND 定位键=? AND 规则=? "
        "AND 状态 IN ('已确认正常','已调整')", (目标表, 定位键, 规则)).fetchone()[0]
    return n > 0


def detect(conn: sqlite3.Connection, old_snap: dict[str, dict[str, str]], now: str, today=None) -> dict:
    """标准表已重建、重放之前调用。返回 {period_shift, month_edge}。"""
    conn.execute("DELETE FROM suspect_待确认 WHERE 状态='待确认'")  # 每次重新检测，保留已处理历史

    ps = 0
    for t in _DIFF_TABLES:
        old = old_snap.get(t, {})
        rows = conn.execute(f"SELECT 定位键,原值_归属月 FROM {t} WHERE 定位键 IS NOT NULL").fetchall()
        cnt = Counter(k for k, _ in rows)
        for 定位键, 新原值月 in rows:
            if cnt[定位键] != 1 or 定位键 not in old:  # 只比唯一且上次也有的
                continue
            if (新原值月 or "") != (old[定位键] or ""):
                if not _has_resolved(conn, t, 定位键, "PERIOD_SHIFT"):
                    _add(conn, now, t, 定位键, "PERIOD_SHIFT",
                         f"归属周期变动：{old[定位键] or '空'} → {新原值月 or '空'}", "归属月", 新原值月)
                    ps += 1

    # MONTH_EDGE_NIGHT：本次新出现、当月 1 号交付的收入明细（只对唯一定位键）
    me = 0
    old_income = old_snap.get("std_收入明细", {})
    inc = conn.execute(
        "SELECT 定位键,整单交付日期 FROM std_收入明细 "
        "WHERE 定位键 IS NOT NULL AND 整单交付日期 IS NOT NULL AND 整单交付日期!=''").fetchall()
    cnt_i = Counter(k for k, _ in inc)
    for 定位键, 交付日期 in inc:
        if cnt_i[定位键] != 1 or 定位键 in old_income:  # 唯一 且 本次新出现
            continue
        parts = loaders.parse_date_parts(交付日期)
        recent = today is None or (parts and parts[0] == today.year and parts[1] == today.month)
        if parts and parts[2] == 1 and recent:
            if not _has_resolved(conn, "std_收入明细", 定位键, "MONTH_EDGE_NIGHT"):
                _add(conn, now, "std_收入明细", 定位键, "MONTH_EDGE_NIGHT",
                     f"月初1号交付（疑似实属上月）：{交付日期}", "整单交付日期", 交付日期)
                me += 1
    conn.commit()
    return {"period_shift": ps, "month_edge": me}


def _add(conn, now, 目标表, 定位键, 规则, 摘要, 建议字段, 当前值):
    conn.execute(
        "INSERT INTO suspect_待确认(发现时间,目标表,定位键,规则,摘要,建议字段,当前值,状态) "
        "VALUES(?,?,?,?,?,?,?, '待确认')", (now, 目标表, 定位键, 规则, 摘要, 建议字段, 当前值))
