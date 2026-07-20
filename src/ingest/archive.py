#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归档：db 每日滚动备份（留30份）+ 月末快照（03 详细设计 一·3 / 七）。

- **db 每日备份**：每次更新跑完拷 数据/备份/看板_YYYYMMDD.db，留最近 30 份——人工表(调整/手填)
  不可再生，标准表可重抓。
- **月末快照**：当天=当月最后一天 → 拷 6 个原始源 + 看板.db + summary.json 到 数据/快照存档/YYYY-MM/。
  "财务永远讲某一个时点"。
两者都写在 数据/ 内，已由 .gitignore 挡住（绝不进 git）。
"""

from __future__ import annotations

import calendar
import datetime
import shutil
from pathlib import Path

import loaders
import db


def _vacuum_into(src: Path, dst: Path) -> None:
    """SQLite ≥3.27：VACUUM INTO 产出单文件一致快照（含 WAL 视图）。"""
    import sqlite3

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    conn = sqlite3.connect(str(src), timeout=30.0)
    try:
        # 安全字面量路径：仅接受本机 Path 解析后的绝对路径
        target = str(dst.resolve())
        if "'" in target:
            raise OSError("backup path contains quote")
        conn.execute(f"VACUUM INTO '{target}'")
    finally:
        conn.close()


def backup_db(cfg: dict, today: datetime.date | None = None, root: Path | None = None, keep: int | None = None) -> dict:
    """拷 看板.db → 数据/备份/看板_YYYYMMDD.db，滚动保留最近 keep 份（每天一份≈保留 keep 天）。

    任务书64·D1：优先 VACUUM INTO 一致快照；失败回退 copy2 并体检黄（status=degraded）。
    keep 不传 → 读 config.backup_keep_days（缺省 30），管理员端「设置」页可改。
    注意：仅清理 备份/看板_*.db；**不触及** 快照存档/ 与 年度归档/（永久保留）。
    """
    if keep is None:
        keep = max(1, int(cfg.get("backup_keep_days", 30) or 30))
    src = db.db_path(cfg, root)
    if not src.exists():
        return {"status": "skip", "detail": "库文件不存在", "ok": False}
    day = today or datetime.date.today()
    bdir = loaders.data_dir(cfg, root) / "备份"
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / f"看板_{day:%Y%m%d}.db"
    method = "vacuum_into"
    try:
        _vacuum_into(src, dst)
    except Exception as e:
        method = "copy2_fallback"
        try:
            shutil.copy2(src, dst)
        except OSError as e2:
            return {"status": "error", "detail": f"VACUUM INTO 失败({type(e).__name__}: {e}); copy2 失败({e2})", "ok": False}
    backups = sorted(bdir.glob("看板_*.db"))
    pruned = 0
    while len(backups) > keep:
        backups[0].unlink()
        backups.pop(0)
        pruned += 1
    out = {
        "status": "ok" if method == "vacuum_into" else "degraded",
        "path": str(dst),
        "kept": len(backups),
        "pruned": pruned,
        "ok": True,
        "method": method,
    }
    if method != "vacuum_into":
        out["detail"] = "VACUUM INTO 失败，已回退 copy2（体检黄）"
        out["yellow"] = True
    return out


def restore_db_from_backup(
    cfg: dict, backup_path: Path | str, root: Path | None = None
) -> dict:
    """从每日滚动备份恢复看板.db（覆盖当前库）。测试/演练用；部署手册「恢复演练」章节同步骤。

    步骤：停写 → copy2 备份→目标 → 下次 connect 自动 migrate/建表。
    返回 {status, path, detail}。
    """
    src = Path(backup_path)
    if not src.exists() or not src.is_file():
        return {"status": "error", "detail": f"备份不存在：{src}"}
    dst = db.db_path(cfg, root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # 恢复前再留一份当前库（若存在）
    if dst.exists():
        pre = dst.with_name(dst.name + f".pre-restore-{datetime.datetime.now():%Y%m%d%H%M%S}")
        try:
            shutil.copy2(dst, pre)
        except OSError:
            pre = None
    else:
        pre = None
    try:
        shutil.copy2(src, dst)
    except OSError as e:
        return {"status": "error", "detail": str(e), "pre": str(pre) if pre else None}
    return {"status": "ok", "path": str(dst), "from": str(src), "pre": str(pre) if pre else None}


def maybe_year_archive_zhiyun(  # noqa: C901  # 跨年归档分支：存在/跳过/拷贝/失败
    cfg: dict,
    root: Path | None = None,
    today: datetime.date | None = None,
) -> dict:
    """跨年自动归档（任务书64·E）：zhiyun_since=auto 切到新年后首抓前，
    若 数据/年度归档/<旧年>/ 尚不存在，则把四源现有 xlsx + 当日 db 完整拷入后返回。

    归档只做一次（目录已存在即跳过）；**永久保留**，backup_keep 清理不得触及。
    """
    from ingest import fetch_zhiyun

    day = today or datetime.date.today()
    since_raw = cfg.get("zhiyun_since") if cfg.get("zhiyun_since") is not None else "auto"
    resolved = fetch_zhiyun.resolve_zhiyun_since(since_raw, today=day)
    if not resolved:
        return {"status": "skip", "detail": "zhiyun_since 全量/空，不触发跨年归档"}
    try:
        y = int(resolved[:4])
    except (TypeError, ValueError):
        return {"status": "skip", "detail": f"无法解析 since 年份：{resolved}"}
    # 仅当 since 落在「当年元旦」（auto 或写死同年）且我们即将按新年过滤覆盖时
    if y != day.year:
        return {"status": "skip", "detail": f"since 年 {y} ≠ today 年 {day.year}"}
    prev = y - 1
    if prev < 2000:
        return {"status": "skip", "detail": "prev year 无效"}
    base = loaders.data_dir(cfg, root)
    arch = base / "年度归档" / str(prev)
    if arch.is_dir() and any(arch.iterdir()):
        return {"status": "exists", "path": str(arch), "year": prev, "ok": True}
    # 有任一源文件才归档
    stems = []
    files_cfg = cfg.get("files") or {}
    for key in ("orders", "receipts", "project_detail_stem", "inhouse"):
        name = files_cfg.get(key)
        if not name:
            continue
        if key == "project_detail_stem":
            p = base / f"{name}.xlsx"
        else:
            p = base / name
        if p.is_file():
            stems.append(p)
    if not stems:
        return {"status": "skip", "detail": "无本地四源 xlsx，跳过归档", "year": prev}
    arch.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in stems:
        try:
            shutil.copy2(p, arch / p.name)
            copied.append(p.name)
        except OSError as e:
            return {"status": "error", "detail": str(e), "ok": False, "year": prev}
    dbp = db.db_path(cfg, root)
    if dbp.is_file():
        try:
            # 优先一致快照
            try:
                _vacuum_into(dbp, arch / f"看板_{prev}.db")
            except Exception:
                shutil.copy2(dbp, arch / f"看板_{prev}.db")
            copied.append(f"看板_{prev}.db")
        except OSError:
            pass
    return {
        "status": "archived",
        "path": str(arch),
        "year": prev,
        "files": copied,
        "ok": True,
        "detail": f"已归档 {prev}",
    }


def snapshot_page(
    cfg: dict, html: str, today: datetime.date | None = None, root: Path | None = None, keep: int | None = None
) -> dict:
    """存当天渲染好的看板页面 → 数据/备份/页面_YYYYMMDD.html（同天覆盖=留当天最后一次），
    滚动保留 keep 天（同 backup_keep_days）。供管理员端「历史快照」按天回看。
    月末那天的页面另随月末快照永久保留（12-31 即年末档）。"""
    if keep is None:
        keep = max(1, int(cfg.get("backup_keep_days", 365) or 365))
    day = today or datetime.date.today()
    bdir = loaders.data_dir(cfg, root) / "备份"
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / f"页面_{day:%Y%m%d}.html"
    dest.write_text(html, encoding="utf-8")
    if is_month_end(day):  # 月末页面另存进月末快照夹，永久保留（12-31 即年末档）
        snap = loaders.data_dir(cfg, root) / "快照存档" / f"{day:%Y-%m}"
        snap.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, snap / dest.name)
    pages = sorted(bdir.glob("页面_*.html"))
    pruned = 0
    while len(pages) > keep:
        pages[0].unlink()
        pages.pop(0)
        pruned += 1
    return {"status": "ok", "path": str(dest), "kept": len(pages), "pruned": pruned}


def is_month_end(day: datetime.date) -> bool:
    return day.day == calendar.monthrange(day.year, day.month)[1]


def snapshot_if_month_end(cfg: dict, today: datetime.date | None = None, root: Path | None = None) -> dict:
    """当天=当月最后一天 → 拷 原始6源 + 看板.db + summary.json 到 快照存档/YYYY-MM/。"""
    day = today or datetime.date.today()
    if not is_month_end(day):
        return {"status": "skip", "detail": "非当月最后一天"}
    base = loaders.data_dir(cfg, root)
    snap = base / "快照存档" / f"{day:%Y-%m}"
    snap.mkdir(parents=True, exist_ok=True)
    copied = []
    # 6 个原始源（项目明细是 stem 无后缀，补 .xlsx/.csv；其余已带后缀）
    for name in cfg["files"].values():
        for p in (base / name, base / f"{name}.xlsx", base / f"{name}.csv"):
            if p.exists() and p.is_file():
                shutil.copy2(p, snap / p.name)
                copied.append(p.name)
                break
    # 看板.db
    dbp = db.db_path(cfg, root)
    if dbp.exists():
        shutil.copy2(dbp, snap / dbp.name)
        copied.append(dbp.name)
    # summary.json（run_batch 写到 output_json）
    sj = loaders.ROOT / cfg.get("output_json", "data/驾驶舱数据.json")
    if sj.exists():
        shutil.copy2(sj, snap / "summary.json")
        copied.append("summary.json")
    return {"status": "snapshot", "path": str(snap), "copied": sorted(set(copied))}
