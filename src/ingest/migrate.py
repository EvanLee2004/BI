#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：手填与调整.xlsx（宽表）→ manual_手填 表。

- 幂等：仅当 manual_手填 为空时导入（人工表重建永不清空，二次跑不覆盖已存的手填）。
- 忠实：读法完全复用 loaders.load_manual（同一套月份列名归一 / 空值跳过逻辑），保证迁移后
  db.load_manual 与旧 loaders.load_manual 逐项一致（回归红线）。
- 归档：迁移只读不删源文件；正式退役由人工在确认无误后归档（本轮不动源文件）。
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import loaders


def manual_is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM manual_手填").fetchone()[0] == 0


def migrate_manual(
    cfg: dict, conn: sqlite3.Connection, root: Path | None = None, 经手人: str = "迁移", 时间: str = ""
) -> dict:
    """把手填 xlsx 导入 manual_手填。返回 {status, imported, detail}。"""
    if not manual_is_empty(conn):
        return {"status": "skipped", "imported": 0, "detail": "manual_手填 已有数据，跳过迁移（不覆盖人工表）"}

    raw = loaders.load_manual(cfg, root)  # {'YYYY-MM': {项目: 金额float}}
    if not raw:
        return {"status": "empty_source", "imported": 0, "detail": "手填与调整.xlsx 为空或不存在，无可迁移"}

    import money

    stamp = 时间 or _now()
    n = 0
    cur = conn.cursor()
    for 归属月, items in raw.items():
        for 项目, 金额 in items.items():
            fen = money.yuan_to_fen(金额)
            if fen is None:
                fen = 0
            cur.execute(
                "INSERT OR REPLACE INTO manual_手填(归属月,项目,金额,填写时间,经手人) VALUES(?,?,?,?,?)",
                (归属月, 项目, fen, stamp, 经手人),
            )
            n += 1
    conn.commit()
    return {"status": "migrated", "imported": n, "detail": f"手填 xlsx → manual_手填 共 {n} 条"}


def _now() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
