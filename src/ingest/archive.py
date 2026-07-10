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


def backup_db(cfg: dict, today: datetime.date | None = None, root: Path | None = None, keep: int | None = None) -> dict:
    """拷 看板.db → 数据/备份/看板_YYYYMMDD.db，滚动保留最近 keep 份（每天一份≈保留 keep 天）。
    keep 不传 → 读 config.backup_keep_days（缺省 30），管理员端「设置」页可改。"""
    if keep is None:
        keep = max(1, int(cfg.get("backup_keep_days", 30) or 30))
    src = db.db_path(cfg, root)
    if not src.exists():
        return {"status": "skip", "detail": "库文件不存在"}
    day = today or datetime.date.today()
    bdir = loaders.data_dir(cfg, root) / "备份"
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / f"看板_{day:%Y%m%d}.db"
    shutil.copy2(src, dst)
    backups = sorted(bdir.glob("看板_*.db"))
    pruned = 0
    while len(backups) > keep:
        backups[0].unlink()
        backups.pop(0)
        pruned += 1
    return {"status": "ok", "path": str(dst), "kept": len(backups), "pruned": pruned}


def snapshot_page(cfg: dict, html: str, today: datetime.date | None = None,
                  root: Path | None = None, keep: int | None = None) -> dict:
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
