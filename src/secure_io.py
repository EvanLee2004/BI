#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""私密文件写盘（任务书64·P / 2.6.3·A1）：原子写 + chmod 0o600。

适用：看板账号.json / 智云配置.json / 管理员密钥.json 等含口令或密钥的本地文件。
Linux 生效；macOS 兼容；Windows 跳过权限位（测试中亦跳过）。

原子写出处：同目录临时文件 → chmod → os.replace（POSIX 原子 rename；
Python 文档与常用「write-then-rename」模式，避免 write_text 先截断再写）。
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
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
    """原子写入文本后 chmod 0o600。

    同目录 tmp → 写完整内容 → chmod 0o600 → os.replace 落到目标。
    避免进程被杀/断电时目标文件被截断成半截。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        chmod_private(tmp_path)
        os.replace(tmp_path, p)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    # 目标再确保一次权限（部分平台 replace 后 mode 继承原文件）
    chmod_private(p)


def write_private_bytes(path: Path | str, data: bytes) -> None:
    """原子写入二进制后 chmod 0o600。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        chmod_private(tmp_path)
        os.replace(tmp_path, p)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
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
