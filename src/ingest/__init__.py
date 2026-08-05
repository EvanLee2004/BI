#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新管道：fetch 台账 → 读原始 → 规范化 → 全量重建标准表 → 一次性迁移手填 →
重放调整/过期校验 → 写运行日志。profit 只从库读，数字与 v6-final 一分不差（回归红线）。
（可疑单/diff 分级机制已于 R0 整套删除，见 4_管理过程/10_迭代计划_数据库分层改造R系列.md 三。）
"""

from __future__ import annotations

import logging

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
    remap_adj_locators,
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
    # 2.6.3·B3：月末当天快照 + 查漏补上月
    report["snapshot"] = archive.snapshot_if_month_end(cfg, d, root)
    try:
        report["snapshot_prev_month"] = archive.ensure_prev_month_snapshot(cfg, d, root)
        if (report.get("snapshot_prev_month") or {}).get("yellow"):
            report.setdefault("info", []).append(
                f"已补做上月快照 {(report['snapshot_prev_month'] or {}).get('missing_month')}"
            )
    except Exception as e:
        report["snapshot_prev_month"] = {
            "status": "error",
            "detail": f"{type(e).__name__}: {e}",
            "done": False,
            "yellow": True,
        }
    # 2.6.3·B3/BUG-16：done 明确布尔；月末真空用 is_month_end 或 snapshot.done
    is_me = False
    try:
        is_me = bool((report.get("snapshot") or {}).get("done")) or archive.is_month_end(d)
    except Exception:
        try:
            is_me = d.day == __import__("calendar").monthrange(d.year, d.month)[1]
        except Exception:
            is_me = False
    if is_me:
        try:
            vacuum_db(conn)
            report["vacuum"] = "ok"
        except Exception as e:
            report["vacuum"] = f"fail:{type(e).__name__}"


def build_std_db(  # noqa: C901  # 2.6.3 管道步骤：归档/缺 sheet/备份分支
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
    # 1a) 2.6.3·B4：跨年归档改为管道必跑一步（不再挂在 zhiyun_auto_fetch 内）
    try:
        day0 = today if isinstance(today, datetime.date) else datetime.date.today()
        report["year_archive"] = archive.maybe_year_archive_zhiyun(cfg, root, today=day0)
        if (report.get("year_archive") or {}).get("red") or (
            (report.get("year_archive") or {}).get("status") == "error"
        ):
            try:
                from notify import maybe_alert_text

                ya = report["year_archive"] or {}
                maybe_alert_text(
                    cfg,
                    f"【经营看板告警】跨年归档失败：{ya.get('detail') or ya.get('status')}",
                )
            except Exception as _e:
                logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
    except Exception as e:
        report["year_archive"] = {
            "status": "error",
            "detail": f"{type(e).__name__}: {e}",
            "ok": False,
            "red": True,
        }
    # 1b) 智云四源在线抓（默认常开=更新必抓，抓不到降级；config.zhiyun_auto_fetch=false 仅应急后门）。
    # KANBAN_OFFLINE=1 强制跳过（测试/回归用：不碰网络、不动进料口，跑得快且可复现）。
    if cfg.get("zhiyun_auto_fetch") and not os.environ.get("KANBAN_OFFLINE"):
        report["fetch_zhiyun"] = fetch_zhiyun.fetch_all(cfg, root, today=today)
        # 任务书66·D：登录冷却元信息（不占源键）
        if isinstance(report["fetch_zhiyun"], dict) and report["fetch_zhiyun"].get("_meta_cooldown"):
            report["zhiyun_login_cooldown"] = report["fetch_zhiyun"].pop("_meta_cooldown")
            try:
                from notify import alert_event

                meta = report["zhiyun_login_cooldown"] or {}
                if meta.get("needs_credential_check") or meta.get("error_kind") == "credential":
                    alert_event("zhiyun_login_cooldown", "智云凭据疑似错误需人工检查")
                else:
                    alert_event("zhiyun_login_cooldown", "智云登录短退避（临时失败，稍后自动恢复）")
            except Exception as _e:
                logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
        if isinstance(report.get("fetch_zhiyun"), dict) and report["fetch_zhiyun"].get("_meta_freshness"):
            report["data_freshness"] = report["fetch_zhiyun"].pop("_meta_freshness")

    # 2) 读原始 + 规范化（缺台账 sheet 不抛死整管，见 loaders.load_ledger）
    records = _normalize_all_sources(cfg, ledger_year, root)
    # 2b) 台账缺年页：空集已进 records；抬体检红 + 横幅
    try:
        import loaders as _ld

        miss = _ld.ledger_sheet_missing_status()
        if miss:
            report["ledger_sheet_missing"] = miss
            report.setdefault("fetch_banners_extra", []).append(
                {
                    "source": "ledger",
                    "status": "missing_sheet",
                    "text": f"收单台账缺 {miss.get('year')} 页，找亮晶建",
                }
            )
    except Exception as _e:
        logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
    # 3–5) BE-001：rebuild + remap + migrate_manual + adj 同一 IMMEDIATE 事务
    report["counts"] = {t: len(records[t]) for t in _STD_ORDER}
    try:
        conn.commit()
    except Exception as _e:
        logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
    prev_iso = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        _rebuild_std(conn, records, manage_txn=False)
        try:
            report["locator_remap"] = _remap_expense_adj_locators(
                conn, records.get("std_费用明细") or []
            )
        except Exception as e:
            report["locator_remap"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"}
        report["migrate_manual"] = migrate.migrate_manual(cfg, conn, root, commit=False)
        report["adjust"] = adjust.apply_adjustments(conn, now, commit=False)
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception as _e:
            logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
        raise
    finally:
        conn.isolation_level = prev_iso
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
    # 8) 本机告警日志（失败绝不影响主流程；无外发）
    try:
        from notify import maybe_alert_pipeline

        maybe_alert_pipeline(cfg, report, root)
    except Exception as _e:
        logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)

    report["records"] = records  # 供 server 缓存做"秒级重算"（不落日志）
    if own:
        conn.close()
    return report


def _rebuild_std(conn, records: dict, *, manage_txn: bool = True) -> None:
    """全量重建标准表（人工表不动）。SQL 在 db_write.rebuild_std_tables。

    2.6.8：剥掉 normalize 临时字段（_legacy_定位键 等）再入库。
    manage_txn=False：嵌套 BE-001 外层事务。
    """
    clean: dict = {}
    for t, rows in (records or {}).items():
        if not isinstance(rows, list):
            clean[t] = rows
            continue
        clean[t] = [
            {k: v for k, v in r.items() if not str(k).startswith("_")} if isinstance(r, dict) else r
            for r in rows
        ]
    rebuild_std_tables(conn, clean, manage_txn=manage_txn)


def _remap_expense_adj_locators(conn, expense_rows: list) -> dict:
    """2.6.8 T2：旧定位键（无事项）→ 新定位键。

    仅当某个旧键在本批唯一对应 1 行新键时才改 adj（旧撞键行本就拒调，无有效 adj）。
    SQL 在 db_write.remap_adj_locators（业务层零裸 SQL）。
    """
    legacy_to_new: dict[str, list[str]] = {}
    for r in expense_rows or []:
        if not isinstance(r, dict):
            continue
        leg = r.get("_legacy_定位键")
        neu = r.get("定位键")
        if not leg or not neu:
            continue
        legacy_to_new.setdefault(str(leg), []).append(str(neu))

    mapping: dict[str, str] = {}
    skipped_ambiguous = 0
    unchanged = 0
    for leg, news in legacy_to_new.items():
        uniq = list(dict.fromkeys(news))  # 保序去重
        if len(uniq) != 1:
            skipped_ambiguous += 1
            continue
        neu = uniq[0]
        if neu == leg:
            unchanged += 1
            continue
        mapping[leg] = neu
    remapped = remap_adj_locators(conn, "std_费用明细", mapping)
    return {
        "status": "ok",
        "remapped_rows": remapped,
        "skipped_ambiguous_keys": skipped_ambiguous,
        "unchanged_keys": unchanged,
        "mapping_size": len(mapping),
    }


def reapply(cfg: dict, conn, records: dict, today=None) -> dict:
    """**轻量重算**（管理员保存后秒级重算用）：用缓存的原始记录重置标准表 → 重放全部生效调整。
    不 fetch、不读 xlsx（无新数据）。返回 adjust 报告。

    BE-001：rebuild + apply 同一 BEGIN IMMEDIATE 事务，中途失败整段回滚。
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.commit()
    except Exception as _e:
        logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
    prev_iso = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        _rebuild_std(conn, records, manage_txn=False)
        rep = adjust.apply_adjustments(conn, now, commit=False)
        conn.execute("COMMIT")
        return rep
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception as _e:
            logging.getLogger('kanban.ingest').exception('swallowed: %s', _e)
        raise
    finally:
        conn.isolation_level = prev_iso


def _zy_source_results(report: dict) -> dict:
    """智云四源结果（去掉 _meta_* 等非源键）。管道未跑智云时返回 {}。"""
    zy = report.get("fetch_zhiyun") or {}
    if not isinstance(zy, dict):
        return {}
    return {k: v for k, v in zy.items() if isinstance(v, dict) and not str(k).startswith("_")}


def _status_is_ok_fetch(status: str | None) -> bool:
    """应抓源视为「本次抓到」的状态：fetched / skipped*。"""
    if not status:
        return True
    return status in ("fetched", "skipped", "skipped_no_share")


def _log_run(conn, now: str, trigger: str, report: dict) -> str:
    """方案 B（2.2.8）：绿=应抓源都抓到且无业务提醒；红=有源本次未抓到或硬故障；
    黄=抓齐仍有业务提醒。应抓源=台账（有配置则须 fetched；未配置已标 fetched）+
    智云四源（仅本轮实际跑了 fetch_zhiyun 时计入；zhiyun_auto_fetch 关则无该键不因智云红）。
    """
    fetch = report.get("fetch") or {}
    fetch_st = fetch.get("status")
    adj = report.get("adjust", {}) or {}
    zy_src = _zy_source_results(report)
    dups = report.get("duplicate_locators") or {}

    db_bad = not (report.get("db_check") or {}).get("ok", True)
    disk_red = bool((report.get("disk") or {}).get("red"))
    login_meta = report.get("zhiyun_login_cooldown") or {}
    login_cd = bool(login_meta.get("active"))
    if not login_cd:
        login_cd = any(bool(v.get("login_cooldown")) for v in zy_src.values())
    year_arch_red = bool((report.get("year_archive") or {}).get("red")) or (
        (report.get("year_archive") or {}).get("status") == "error"
    )
    ledger_sheet_miss = bool(report.get("ledger_sheet_missing"))

    # 3.7.4：数据新鲜度三态（可选；有则用于软化「临时失败+仍新鲜副本」）
    freshness = report.get("data_freshness") or {}
    using_fresh = freshness.get("state") == "fetch_failed_using_fresh"
    data_unsafe = freshness.get("state") in ("unsafe", "stale_or_missing")
    # 短退避临时错误 + 仍新鲜副本 → 不硬红（管理端 info 轻提示）
    login_hard = login_cd and not (
        using_fresh
        and (
            login_meta.get("error_kind") == "temporary"
            or login_meta.get("backoff_kind") == "short"
            and not login_meta.get("needs_credential_check")
        )
    )
    # 凭据明确错误且无新鲜副本 → 仍红；有新鲜副本则非阻断（needs 人工检查文案在 reasons）
    if login_cd and login_meta.get("needs_credential_check") and using_fresh:
        login_hard = False

    # 硬红：台账无源 / 库坏 / 盘满 / 登录硬失败 / 跨年归档失败 / 缺当年台账页 / 数据不安全
    hard_red = (
        (fetch_st == "no_source")
        or db_bad
        or disk_red
        or login_hard
        or year_arch_red
        or ledger_sheet_miss
        or data_unsafe
    )

    # 抓数失败红：应抓源 status 非 fetched/skipped*；若仅临时失败且用新鲜副本 → 不红
    fetch_fail = False
    if fetch_st and not _status_is_ok_fetch(fetch_st) and fetch_st != "no_source":
        # local_fallback 等 = 本次未抓到
        fetch_fail = True
    for v in zy_src.values():
        if not _status_is_ok_fetch(v.get("status")):
            fetch_fail = True
            break
    if fetch_fail and using_fresh and not data_unsafe:
        fetch_fail = False
        report.setdefault("info", []).append(
            freshness.get("message")
            or "本次抓取失败，正在使用仍新鲜的最后成功数据（非阻断）"
        )

    # 业务黄：调整过期/失配、智云 warnings（骤降等）；同名控件只在 info 不进 warnings
    # 2.6.3·B3：缺月快照补做 → 黄
    zy_warn = any(bool(v.get("warnings")) for v in zy_src.values())
    snap_yellow = bool((report.get("snapshot_prev_month") or {}).get("yellow"))
    business_yellow = (
        int(adj.get("expired", 0) or 0) > 0
        or int(adj.get("missing", 0) or 0) > 0
        or zy_warn
        or snap_yellow
    )

    red = hard_red or fetch_fail
    yellow = (not red) and business_yellow
    结果 = "红" if red else ("黄" if yellow else "绿")

    # 信息行：定位键重复计数（不影响绿黄红）；智云源 info 上浮到 report.info
    n_dup_keys = sum(len(v) for v in dups.values()) if isinstance(dups, dict) else 0
    if n_dup_keys:
        report.setdefault("info", []).append(
            f"{n_dup_keys} 组定位键重复（按现状计入·明昊拍板不判黄；写调整仍拒/重放过期疑似）"
        )
    for src, v in zy_src.items():
        for msg in v.get("info") or []:
            report.setdefault("info", []).append(f"智云·{src}：{msg}")

    log_body = {k: v for k, v in report.items() if k != "records"}
    insert_run_log(conn, now, trigger, 结果, log_body)
    return 结果
