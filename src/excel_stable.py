# -*- coding: utf-8 -*-
"""Excel/源文件稳定复制与 ZIP 完整性（3.6.0 G1）。

共享盘/本地源只读：先 copy 到同机临时快照，校验 size 稳定与 ZIP 可读，再交给 openpyxl。
"""

from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path
from typing import Callable


class StableCopyError(Exception):
    """稳定复制失败（不携带凭据）。"""

    def __init__(self, message: str, *, source: str = "", attempts: int = 0):
        super().__init__(message)
        self.source = source
        self.attempts = attempts


def _is_zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            return bad is None
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def stable_copy(
    src: Path | str,
    dest_dir: Path | str,
    *,
    retries: int = 3,
    settle_ms: int = 80,
    sleep_fn: Callable[[float], None] | None = None,
    is_xlsx: bool | None = None,
) -> Path:
    """复制 src → dest_dir/name，要求连续两次 size 一致且（xlsx 时）ZIP 完整。

    失败抛 StableCopyError（message 不含路径中的密码段）。
    """
    sleep = sleep_fn or time.sleep
    src_p = Path(src)
    dest_p = Path(dest_dir)
    dest_p.mkdir(parents=True, exist_ok=True)
    if not src_p.is_file():
        raise StableCopyError("source_missing", source=src_p.name, attempts=0)

    name = src_p.name
    out = dest_p / name
    check_zip = is_xlsx if is_xlsx is not None else name.lower().endswith((".xlsx", ".xlsm"))

    last_err = "unknown"
    for attempt in range(1, max(1, retries) + 1):
        try:
            shutil.copy2(src_p, out)
            s1 = out.stat().st_size
            sleep(max(0, settle_ms) / 1000.0)
            # 源仍在变？再 copy 一次比对
            shutil.copy2(src_p, out)
            s2 = out.stat().st_size
            if s1 != s2 or s2 != src_p.stat().st_size:
                last_err = "size_unstable"
                sleep(0.05 * attempt)
                continue
            if check_zip and not _is_zip_ok(out):
                last_err = "bad_zip"
                sleep(0.05 * attempt)
                continue
            return out
        except OSError as e:
            last_err = f"os_error:{type(e).__name__}"
            sleep(0.05 * attempt)
    raise StableCopyError(last_err, source=src_p.name, attempts=retries)
