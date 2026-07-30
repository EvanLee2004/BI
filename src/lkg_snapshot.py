# -*- coding: utf-8 -*-
"""Last-Known-Good VM/summary 快照（3.6.0 G1）。

成功构建后原子保存；冷启动构建失败时只读加载兼容快照，禁止退到 bootstrap。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def lkg_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / "lkg"


def lkg_path(data_dir: Path | str) -> Path:
    return lkg_dir(data_dir) / "snapshot.json"


def save_lkg(
    data_dir: Path | str,
    summary: dict[str, Any],
    *,
    version: str = "",
    commit: str = "",
    schema_version: int | str | None = None,
) -> Path:
    """原子写 LKG（不含敏感配置）。"""
    d = lkg_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": version,
        "git_commit": commit,
        "schema_version": schema_version,
        "summary": summary,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    payload["checksum"] = digest
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path = lkg_path(data_dir)
    fd, tmp = tempfile.mkstemp(prefix=".lkg.", dir=str(d))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load_lkg(
    data_dir: Path | str,
    *,
    require_schema: int | str | None = None,
) -> dict[str, Any] | None:
    """加载 LKG；损坏或不兼容返回 None（调用方走 maintenance，不 bootstrap）。"""
    path = lkg_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "summary" not in data:
        return None
    if require_schema is not None and data.get("schema_version") not in (None, require_schema):
        # 显式 schema 不匹配 → 不兼容
        if data.get("schema_version") != require_schema:
            return None
    return data


def is_compatible(lkg: dict[str, Any] | None, *, schema_version: int | str | None = None) -> bool:
    if not lkg or not isinstance(lkg.get("summary"), dict):
        return False
    if schema_version is not None and lkg.get("schema_version") not in (None, schema_version):
        return False
    return True
