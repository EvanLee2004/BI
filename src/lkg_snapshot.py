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


def _payload_for_checksum(data: dict[str, Any]) -> dict[str, Any]:
    """checksum 覆盖字段：不含自指 checksum。"""
    return {k: v for k, v in data.items() if k != "checksum"}


def verify_checksum(data: dict[str, Any]) -> bool:
    stored = str(data.get("checksum") or "").strip()
    if not stored:
        return False
    raw = json.dumps(
        _payload_for_checksum(data), ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest == stored


def _quarantine_corrupt(path: Path) -> None:
    bak = path.with_suffix(path.suffix + f".corrupt.{int(time.time())}")
    try:
        path.rename(bak)
    except OSError:
        pass


def load_lkg(
    data_dir: Path | str,
    *,
    require_schema: int | str | None = None,
) -> dict[str, Any] | None:
    """加载 LKG；损坏/checksum 失败/不兼容返回 None（调用方走 maintenance，不 bootstrap）。"""
    path = lkg_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _quarantine_corrupt(path)
        return None
    if not isinstance(data, dict) or "summary" not in data:
        _quarantine_corrupt(path)
        return None
    if not verify_checksum(data):
        _quarantine_corrupt(path)
        return None
    if require_schema is not None and data.get("schema_version") != require_schema:
        return None
    return data


def is_compatible(lkg: dict[str, Any] | None, *, schema_version: int | str | None = None) -> bool:
    """结构兼容：必须有 summary；schema_version=None 不再视为永久兼容。"""
    if not lkg or not isinstance(lkg.get("summary"), dict):
        return False
    sv = lkg.get("schema_version")
    if sv is None:
        # 缺 schema 的旧/残缺快照：仅当调用方未要求 schema 时仍拒绝（须显式版本）
        return False
    if schema_version is not None and sv != schema_version:
        return False
    return True
