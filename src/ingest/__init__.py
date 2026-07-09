#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新管道（刀1 子集）：fetch 台账 → 读原始 → 规范化 → 全量重建标准表 → 一次性迁移手填。

刀2 会在此基础上补：diff 分级 / 套用调整 / 可疑单规则 / 运行日志。刀1 只做"标准表落库 + 手填迁移"，
让 profit 改从库读，且数字与 v6-final 一分不差。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import columns
import db
import schema
from ingest import readers, normalize, fetch, migrate, suspects, adjust, archive

_STD_ORDER = ["std_收入明细", "std_下单", "std_回款", "std_内部译员", "std_费用明细"]

_STD_INSERT = {
    "std_收入明细": (["定位键", "订单号", "客户", "业务线", "整单交付日期", "交付额", "项目成本", "归属月", "原值_交付日期", "原值_归属月"]),
    "std_下单": (["定位键", "订单号", "下单日期", "下单预估额", "归属月", "原值_归属月"]),
    "std_回款": (["定位键", "回款ID", "到账日期", "到账金额", "归属月", "原值_归属月"]),
    "std_内部译员": (["定位键", "任务ID", "任务提交日期", "结算金额", "译员类型", "归属月", "原值_归属月"]),
    "std_费用明细": (["定位键", "收单月份", "收单日期", "含税金额", "业务BU", "对应报表大类", "预算明细费用类型", "预算归属部门", "归属月", "原值_归属月"]),
}


def _insert(conn, table: str, records: list[dict]) -> None:
    cols = _STD_INSERT[table]
    sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
    conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in records])


def build_std_db(cfg: dict, ledger_year: int, root: Path | None = None,
                 conn=None, today=None, trigger: str = "manual",
                 archive_backups: bool = False) -> dict:
    """跑一次更新管道（刀1+刀2 子集）：fetch → 规范化 → diff 快照 → 全量重建 → 手填迁移 →
    diff分级/可疑单 → 重放调整/过期校验 → 写运行日志。返回状态报告 dict。"""
    own = conn is None
    if own:
        conn = db.connect(cfg, root)
    c = cfg["columns"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report: dict = {}

    # 1) fetch 收单台账（可达才拉、不可达走本地副本，不中断）
    report["fetch"] = fetch.fetch_ledger(cfg, root)

    # 2) 读原始 + 规范化
    proj = normalize.norm_project_detail(readers.read_project_detail(cfg, root), c)
    orders = normalize.norm_orders(readers.read_orders(cfg, root), c)
    receipts = normalize.norm_receipts(readers.read_receipts(cfg, root), c)
    inhouse = normalize.norm_inhouse(readers.read_inhouse(cfg, root), c, cfg)
    lheader, lrows = readers.read_ledger(cfg, ledger_year, root)
    lcols = columns.resolve_ledger_columns(lheader)
    ledger = normalize.norm_ledger(lheader, lrows, ledger_year, lcols)

    records = {"std_收入明细": proj, "std_下单": orders, "std_回款": receipts,
               "std_内部译员": inhouse, "std_费用明细": ledger}

    # 2.5) diff 快照：重建前抓上次原始归属月（供 diff 分级比对"周期是否变"）
    old_snap = suspects.snapshot_before_reset(conn)

    # 3) 全量重建标准表（人工表不动）
    _rebuild_std(conn, records)
    report["counts"] = {t: len(records[t]) for t in _STD_ORDER}

    # 4) 一次性迁移手填（仅当 manual_手填 为空）
    report["migrate_manual"] = migrate.migrate_manual(cfg, conn, root)

    # 5) diff 分级 + 可疑单规则（金额变覆盖已由重建完成；周期变/月初1号入待确认队列）
    report["suspects"] = suspects.detect(conn, old_snap, now, today=today)

    # 6) 重放调整 + 过期校验（改数不改结果、只记指令）
    report["adjust"] = adjust.apply_adjustments(conn, now)

    # 7) 写运行日志（结果绿/黄/红）——注意不把 records 塞进日志 JSON
    report["result"] = _log_run(conn, now, trigger, report)

    # 8) db 每日滚动备份（30份）+ 月末快照（仅真实跑，测试/回归不落盘污染数据目录）
    if archive_backups:
        d = today if isinstance(today, datetime.date) else datetime.date.today()
        report["backup"] = archive.backup_db(cfg, d, root)
        report["snapshot"] = archive.snapshot_if_month_end(cfg, d, root)

    report["records"] = records  # 供 server 缓存做"秒级重算"（不落日志）
    if own:
        conn.close()
    return report


def _rebuild_std(conn, records: dict) -> None:
    """全量重建标准表（人工表不动）。records: {表名: [规范化记录]}。"""
    schema.reset_std_tables(conn)
    for t in _STD_ORDER:
        _insert(conn, t, records[t])
    conn.commit()


def reapply(cfg: dict, conn, records: dict, today=None) -> dict:
    """**轻量重算**（管理员保存后秒级重算用）：用缓存的原始记录重置标准表 → 重放全部生效调整。
    不 fetch、不读 xlsx、不重跑 diff/可疑单（无新数据）。返回 adjust 报告。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _rebuild_std(conn, records)
    rep = adjust.apply_adjustments(conn, now)
    conn.commit()
    return rep


def _log_run(conn, now: str, trigger: str, report: dict) -> str:
    """据本轮情况判绿/黄/红，写 meta_运行日志。黄=fetch走本地副本 / 有过期疑似 / 有待确认。"""
    fetch_ok = report["fetch"]["status"] == "fetched"
    adj = report.get("adjust", {})
    sus = report.get("suspects", {})
    yellow = (not fetch_ok) or adj.get("expired", 0) > 0 or \
        (sus.get("period_shift", 0) + sus.get("month_edge", 0)) > 0
    red = report["fetch"]["status"] == "no_source"
    结果 = "红" if red else ("黄" if yellow else "绿")
    conn.execute(
        "INSERT INTO meta_运行日志(时间,触发方式,结果,体检JSON) VALUES(?,?,?,?)",
        (now, trigger, 结果, json.dumps(report, ensure_ascii=False)))
    conn.commit()
    return 结果
