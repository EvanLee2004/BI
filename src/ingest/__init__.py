#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新管道：fetch 台账 → 读原始 → 规范化 → 全量重建标准表 → 一次性迁移手填 →
重放调整/过期校验 → 写运行日志。profit 只从库读，数字与 v6-final 一分不差（回归红线）。
（可疑单/diff 分级机制已于 R0 整套删除，见 4_管理过程/10_迭代计划_数据库分层改造R系列.md 三。）
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

import columns
import db
from db_write import (
    db_file_size_bytes,
    disk_free_ratio,
    insert_run_log,
    prune_run_logs,
    rebuild_std_tables,
    vacuum_db,
)
from ingest import readers, normalize, fetch, fetch_zhiyun, migrate, adjust, archive

_STD_ORDER = ["std_收入明细", "std_下单", "std_回款", "std_内部译员", "std_费用明细"]


def _normalize_all_sources(cfg, ledger_year, root) -> dict:
    c = cfg["columns"]
    proj = normalize.norm_project_detail(readers.read_project_detail(cfg, root), c)
    orders = normalize.norm_orders(readers.read_orders(cfg, root), c)
    receipts = normalize.norm_receipts(readers.read_receipts(cfg, root), c)
    inhouse = normalize.norm_inhouse(readers.read_inhouse(cfg, root), c, cfg)
    lheader, lrows = readers.read_ledger(cfg, ledger_year, root)
    lcols = columns.resolve_ledger_columns(lheader)
    ledger = normalize.norm_ledger(lheader, lrows, ledger_year, lcols)
    return {
        "std_收入明细": proj,
        "std_下单": orders,
        "std_回款": receipts,
        "std_内部译员": inhouse,
        "std_费用明细": ledger,
    }


def _report_disk_and_db(cfg, root, report: dict) -> None:
    try:
        data_path = __import__("loaders").data_dir(cfg, root)
        ratio = disk_free_ratio(data_path)
        min_r = float(cfg.get("disk_free_min_ratio", 0.10))
        report["disk"] = {"free_ratio": ratio, "min_ratio": min_r}
        if ratio is not None and ratio < min_r:
            report["disk"]["red"] = True
        report["db_size"] = db_file_size_bytes(cfg, root)
    except Exception as e:
        report["disk"] = {"error": f"{type(e).__name__}: {e}"}


def _run_archive_backups(cfg, root, conn, today, report: dict) -> None:
    d = today if isinstance(today, datetime.date) else datetime.date.today()
    report["backup"] = archive.backup_db(cfg, d, root)
    report["snapshot"] = archive.snapshot_if_month_end(cfg, d, root)
    is_me = False
    try:
        is_me = bool((report.get("snapshot") or {}).get("done")) or (
            d.month != (d + datetime.timedelta(days=1)).month
        )
    except Exception:
        pass
    if is_me:
        try:
            vacuum_db(conn)
            report["vacuum"] = "ok"
        except Exception as e:
            report["vacuum"] = f"fail:{type(e).__name__}"


def build_std_db(
    cfg: dict,
    ledger_year: int,
    root: Path | None = None,
    conn=None,
    today=None,
    trigger: str = "manual",
    archive_backups: bool = False,
) -> dict:
    """跑一次更新管道：fetch → 规范化 → 全量重建 → 手填迁移 → 重放调整/过期校验 →
    写运行日志。返回状态报告 dict。"""
    own = conn is None
    if own:
        conn = db.connect(cfg, root)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report: dict = {}

    # 1) fetch 收单台账（可达才拉、不可达走本地副本，不中断）
    report["fetch"] = fetch.fetch_ledger(cfg, root)
    # 1b) 智云四源在线抓（默认常开=更新必抓，抓不到降级；config.zhiyun_auto_fetch=false 仅应急后门）。
    # KANBAN_OFFLINE=1 强制跳过（测试/回归用：不碰网络、不动进料口，跑得快且可复现）。
    if cfg.get("zhiyun_auto_fetch") and not os.environ.get("KANBAN_OFFLINE"):
        # 跨年：写盘前归档旧年四源（只一次；不污染 fetch_zhiyun 源键）
        try:
            report["year_archive"] = archive.maybe_year_archive_zhiyun(cfg, root, today=today)
        except Exception as e:
            report["year_archive"] = {"status": "error", "detail": f"{type(e).__name__}: {e}", "ok": False}
        report["fetch_zhiyun"] = fetch_zhiyun.fetch_all(cfg, root, today=today)
        # 任务书66·D：登录冷却元信息（不占源键）
        if isinstance(report["fetch_zhiyun"], dict) and report["fetch_zhiyun"].get("_meta_cooldown"):
            report["zhiyun_login_cooldown"] = report["fetch_zhiyun"].pop("_meta_cooldown")
            try:
                from notify import alert_event

                alert_event("zhiyun_login_cooldown", "智云凭据疑似失效需人工检查")
            except Exception:
                pass

    # 2) 读原始 + 规范化
    records = _normalize_all_sources(cfg, ledger_year, root)
    # 3) 全量重建标准表（人工表不动）
    _rebuild_std(conn, records)
    report["counts"] = {t: len(records[t]) for t in _STD_ORDER}
    # 4) 一次性迁移手填（仅当 manual_手填 为空）
    report["migrate_manual"] = migrate.migrate_manual(cfg, conn, root)
    # 5) 重放调整 + 过期校验（改数不改结果、只记指令）
    report["adjust"] = adjust.apply_adjustments(conn, now)
    report["duplicate_locators"] = db.audit_duplicate_locators(conn)
    report["db_check"] = db.pragma_quick_check(conn)
    _report_disk_and_db(cfg, root, report)
    # 6) 写运行日志（结果绿/黄/红；磁盘红并入 _log_run）
    report["result"] = _log_run(conn, now, trigger, report)
    try:
        keep = int(cfg.get("run_log_keep_days", 365))
        report["run_log_pruned"] = prune_run_logs(conn, keep)
    except Exception as e:
        report["run_log_pruned"] = f"skip:{type(e).__name__}"
    # 7) db 每日滚动备份 + 月末快照 + 月末 VACUUM
    if archive_backups:
        _run_archive_backups(cfg, root, conn, today, report)
    # 8) 可选飞书告警（失败绝不影响主流程）
    try:
        from notify import maybe_alert_pipeline

        maybe_alert_pipeline(cfg, report, root)
    except Exception:
        pass

    report["records"] = records  # 供 server 缓存做"秒级重算"（不落日志）
    if own:
        conn.close()
    return report


def _rebuild_std(conn, records: dict) -> None:
    """全量重建标准表（人工表不动）。SQL 在 db_write.rebuild_std_tables。"""
    rebuild_std_tables(conn, records)


def reapply(cfg: dict, conn, records: dict, today=None) -> dict:
    """**轻量重算**（管理员保存后秒级重算用）：用缓存的原始记录重置标准表 → 重放全部生效调整。
    不 fetch、不读 xlsx（无新数据）。返回 adjust 报告。
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _rebuild_std(conn, records)
    rep = adjust.apply_adjustments(conn, now)
    return rep


def _log_run(conn, now: str, trigger: str, report: dict) -> str:
    """据本轮情况判绿/黄/红，写 meta_运行日志（SQL 经 db_write.insert_run_log）。"""
    fetch_ok = report["fetch"]["status"] == "fetched"
    adj = report.get("adjust", {})
    zy = report.get("fetch_zhiyun") or {}
    zy_degraded = any(v.get("status") != "fetched" for v in zy.values())
    zy_warn = any(bool(v.get("warnings")) for v in zy.values() if isinstance(v, dict))
    dups = report.get("duplicate_locators") or {}
    # 任务书66·D / 明昊拍板：定位键重复不再使体检黄，仅信息展示
    db_bad = not (report.get("db_check") or {}).get("ok", True)
    yellow = (
        (not fetch_ok)
        or adj.get("expired", 0) > 0
        or adj.get("missing", 0) > 0
        or zy_degraded
        or zy_warn
    )
    # 登录冷却 → 红（见 fetch_zhiyun 写入 report 标记）
    if any(
        isinstance(v, dict) and v.get("login_cooldown")
        for v in (report.get("fetch_zhiyun") or {}).values()
    ):
        yellow = True  # at least yellow; red set below if flag
    if (report.get("zhiyun_login_cooldown") or {}).get("active"):
        pass  # red handled below
    disk_red = bool((report.get("disk") or {}).get("red"))
    login_cd = bool((report.get("zhiyun_login_cooldown") or {}).get("active"))
    red = report["fetch"]["status"] == "no_source" or db_bad or disk_red or login_cd
    结果 = "红" if red else ("黄" if yellow else "绿")
    # 信息行：定位键重复计数（不影响绿黄红）
    n_dup_keys = sum(len(v) for v in dups.values()) if isinstance(dups, dict) else 0
    if n_dup_keys:
        report.setdefault("info", []).append(
            f"{n_dup_keys} 组定位键重复（按现状计入·明昊拍板不判黄；写调整仍拒/重放过期疑似）"
        )
    log_body = {k: v for k, v in report.items() if k != "records"}
    insert_run_log(conn, now, trigger, 结果, log_body)
    return 结果
