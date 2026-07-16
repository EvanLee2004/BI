#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收单台账 fetch：从内网 SMB/UNC 共享（或 Linux CIFS 挂载点）拉到本地数据目录。

铁律（03 详细设计 七 + 用户交代）：
- 路径写 config.ledger_share_path：
  - Windows：UNC 如 \\\\192.168.10.151\\财务部\\…\\收单台账.xlsx
  - Linux：CIFS 挂载后的 POSIX 路径如 /mnt/caiwu/lara.zhao/收单台账.xlsx（见 docs/Ubuntu部署手册）
- **路径可达才拉、不可达走上次本地副本 + 体检黄，绝不中断管道**。
- 本机（macOS）读不到该路径属正常：exists() 为假即走本地副本；开发期直接用数据目录里现有台账。
- 一律 pathlib，不硬编码反斜杠拼接；UNC 与 POSIX 均走 Path(share_raw).exists()。
"""

from __future__ import annotations

import shutil
import sys
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


def fetch_ledger(cfg: dict, root: Path | None = None) -> dict:
    """尝试从共享路径把收单台账拉到 数据/收单台账.xlsx。
    返回 {status: 'fetched'|'local_fallback'|'no_source', detail: str}。永不抛异常中断管道。"""
    local = loaders.data_dir(cfg, root) / cfg["files"]["ledger"]
    share_raw = (cfg.get("ledger_share_path") or "").strip()

    if not share_raw:
        detail = "未配置 ledger_share_path，直接用数据目录现有台账"
        return {"status": "local_fallback" if local.exists() else "no_source", "detail": detail}

    share = _normalize_share_path(share_raw)
    try:
        reachable = share.exists()
    except OSError:
        reachable = False

    if reachable:
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(share, local)
            return {"status": "fetched", "detail": f"已从共享拉取：{share}"}
        except OSError as e:
            if local.exists():
                return {"status": "local_fallback", "detail": f"共享可达但复制失败（{e}），用上次本地副本（体检黄）"}
            return {"status": "no_source", "detail": f"共享可达但复制失败且无本地副本：{e}"}

    # 共享不可达（本机 macOS / 未挂载 CIFS 属正常）
    hint = ""
    if sys.platform.startswith("linux") and (share_raw.startswith("\\\\") or share_raw.startswith("//")):
        hint = "；Linux 请挂 CIFS 到 /mnt/caiwu 后在设置页填 POSIX 路径"
    if local.exists():
        return {
            "status": "local_fallback",
            "detail": f"共享不可达（{share}），用数据目录现有台账（体检黄；部署机上应可达）{hint}",
        }
    return {"status": "no_source", "detail": f"共享不可达且无本地副本：{share}{hint}"}
