#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""私密文件写盘（任务书64·P）：写后 chmod 0o600，缓解明文凭据落地风险。

适用：看板账号.json / 智云配置.json / 管理员密钥.json 等含口令或密钥的本地文件。
Linux 生效；macOS 兼容；Windows 跳过权限位（测试中亦跳过）。
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def chmod_private(path: Path | str) -> None:
    """将文件权限设为 0o600（仅属主读写）。Windows 或失败则静默跳过。"""
    if sys.platform == "win32":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def write_private_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """写入文本后 chmod 0o600。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding=encoding)
    chmod_private(p)


def write_private_bytes(path: Path | str, data: bytes) -> None:
    """写入二进制后 chmod 0o600。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    chmod_private(p)


def is_private_mode(path: Path | str) -> bool | None:
    """检查是否仅属主可读写（0o600）。Windows 返回 None（不适用）。"""
    if sys.platform == "win32":
        return None
    try:
        mode = stat.S_IMODE(Path(path).stat().st_mode)
    except OSError:
        return False
    return mode == (stat.S_IRUSR | stat.S_IWUSR)
