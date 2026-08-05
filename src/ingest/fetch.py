#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收单台账 fetch：从内网 SMB/UNC 共享（或 Linux CIFS 挂载点）拉到本地数据目录。

铁律（03 详细设计 七 + 用户交代）：
- 路径写 config.ledger_share_path（**真实内网路径不进 git**，部署机写 本地配置.json）：
  - Windows：UNC 如 \\\\文件服务器\\共享名\\…\\收单台账.xlsx
  - Linux：CIFS/gvfs 挂载后的 POSIX 路径（见 docs/Ubuntu部署手册；具体路径见机上运维笔记）
- **路径可达才拉、不可达走上次本地副本 + 体检黄，绝不中断管道**。
- 本机（macOS）读不到该路径属正常：exists() 为假即走本地副本；开发期直接用数据目录里现有台账。
- 一律 pathlib，不硬编码反斜杠拼接；UNC 与 POSIX 均走 Path(share_raw).exists()。
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import loaders


def _normalize_share_path(share_raw: str) -> Path:
    """把配置里的共享路径收成 Path。Windows UNC 保持原样；Linux 上若误填 \\\\host\\share 则提示走挂载。"""
    s = (share_raw or "").strip()
    # Linux 上 UNC 字面量 Path 不可达——调用方仍会走 local_fallback；此处不改写配置
    if sys.platform.startswith("linux") and (s.startswith("\\\\") or s.startswith("//") and "\\" in s):
        # 允许 //host/share POSIX-SMB 写法（部分环境 cifs 用 //）；反斜杠 UNC 在 Linux 几乎必失败
        pass
    return Path(s)


def _local_copy_meta(local: Path) -> dict:
    """本地台账副本元信息（给人话告警用）。"""
    meta: dict = {"source": "收单台账", "local_path": str(local.name)}
    try:
        if local.exists():
            import datetime as _dt

            mt = local.stat().st_mtime
            dt = _dt.datetime.fromtimestamp(mt)
            meta["local_mtime"] = mt
            meta["local_as_of"] = dt.strftime("%Y-%m-%d %H:%M")
            meta["local_as_of_cn"] = f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
            meta["data_as_of_cn"] = f"{dt.month}月{dt.day}日"  # 无表内末行日期时用副本日
        else:
            meta["local_as_of"] = ""
            meta["local_as_of_cn"] = "无本地副本"
            meta["data_as_of_cn"] = "无"
    except OSError:
        meta["local_as_of"] = ""
        meta["local_as_of_cn"] = "未知"
        meta["data_as_of_cn"] = "未知"
    return meta


def _fallback_detail(reason: str, meta: dict) -> str:
    """人话：共享不可达 + 用的是哪天的副本。"""
    as_of = meta.get("local_as_of_cn") or "未知时间"
    data_end = meta.get("data_as_of_cn") or as_of
    return (
        f"收单台账共享盘不可达（{reason}），"
        f"用的是 {as_of} 的本地副本（数据止于 {data_end}）"
    )



def _apply_ledger_freshness(cfg: dict, out: dict) -> dict:
    """FIN-006：台账 local_fallback 超过 max 小时标 stale_red（默认 48h 与智云对齐）。"""
    if out.get("status") != "local_fallback":
        return out
    try:
        max_h = float(cfg.get("ledger_fallback_max_age_hours", 48) or 48)
    except (TypeError, ValueError):
        max_h = 48.0
    age_h = out.get("local_age_hours")
    if age_h is None:
        # 从 mtime 推
        try:
            import time
            mtime = out.get("local_mtime")
            if mtime:
                age_h = max(0.0, (time.time() - float(mtime)) / 3600.0)
        except (TypeError, ValueError):
            age_h = None
    if age_h is not None and age_h > max_h:
        out = dict(out)
        out["stale"] = True
        out["stale_hours"] = round(float(age_h), 1)
        out["detail"] = (out.get("detail") or "") + f"（本地副本已超 {max_h:.0f}h，须尽快恢复共享）"
        out["yellow"] = True
    return out


def fetch_ledger(cfg: dict, root: Path | None = None) -> dict:  # noqa: C901
    """尝试从共享路径把收单台账拉到 数据/收单台账.xlsx。
    返回 {status: 'fetched'|'local_fallback'|'no_source', detail: str, ...}。
    永不抛异常中断管道。

    2.2.8：未配置 ledger_share_path 且本地有台账 → status=fetched（开发机不因无共享天天红）；
    已配置但不可达/复制失败 → local_fallback（方案 B 体检红=本次未抓到）。

    2.6.8 T1/T4：local_fallback 带 source / local_as_of / data_as_of；不可达时短重试。
    """
    local = loaders.data_dir(cfg, root) / cfg["files"]["ledger"]
    share_raw = (cfg.get("ledger_share_path") or "").strip()

    if not share_raw:
        if local.exists():
            return {"status": "fetched", "detail": "未配置共享路径，使用本地台账", **_local_copy_meta(local)}
        return {"status": "no_source", "detail": "未配置 ledger_share_path 且无本地台账", "source": "收单台账"}

    share = _normalize_share_path(share_raw)
    # 2.6.8 T4：短重试（默认 3×2s，配置可改；不碰系统挂载）
    try:
        retries = int(cfg.get("ledger_share_retries", 3) or 3)
    except (TypeError, ValueError):
        retries = 3
    try:
        delay = float(cfg.get("ledger_share_retry_delay_sec", 2) or 2)
    except (TypeError, ValueError):
        delay = 2.0
    retries = max(1, min(10, retries))
    delay = max(0.0, min(30.0, delay))

    reachable = False
    attempts = 0
    last_err = ""
    for i in range(retries):
        attempts = i + 1
        try:
            reachable = share.exists()
        except OSError as e:
            reachable = False
            last_err = str(e)
        if reachable:
            break
        if i + 1 < retries and delay > 0:
            time.sleep(delay)

    meta = _local_copy_meta(local)
    meta["share_attempts"] = attempts

    if reachable:
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(share, local)
            out = {"status": "fetched", "detail": f"已从共享拉取：{share}", **_local_copy_meta(local)}
            out["share_attempts"] = attempts
            return out
        except OSError as e:
            if local.exists():
                return _apply_ledger_freshness(cfg, {
                    "status": "local_fallback",
                    "detail": _fallback_detail(f"共享可达但复制失败：{e}", meta),
                    "reason": "copy_failed",
                    **meta,
                })
            return {
                "status": "no_source",
                "detail": f"共享可达但复制失败且无本地副本：{e}",
                "source": "收单台账",
                "share_attempts": attempts,
            }

    # 共享不可达
    hint = ""
    if sys.platform.startswith("linux") and (share_raw.startswith("\\\\") or share_raw.startswith("//")):
        hint = "；Linux 请挂 CIFS 到固定挂载点后在设置页填 POSIX 路径"
    why = f"路径不存在或会话挂载已断：{share}"
    if last_err:
        why += f"（{last_err}）"
    if local.exists():
        return _apply_ledger_freshness(cfg, {
            "status": "local_fallback",
            "detail": _fallback_detail(why, meta) + hint,
            "reason": "unreachable",
            **meta,
        })
    return {
        "status": "no_source",
        "detail": f"共享不可达且无本地副本：{share}{hint}",
        "source": "收单台账",
        "share_attempts": attempts,
    }
