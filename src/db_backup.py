# -*- coding: utf-8 -*-
"""SQLite 备份 / 隔离恢复（3.6.0 G1）。

- 使用 SQLite backup API（非写入中裸 cp）
- manifest：version、commit、时间、源 checksum、关键表行数哈希
- 恢复验证失败 → 非 0 / 抛错
- 绝不打印表内容
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

# 受保护业务表（哈希行数，不导出内容）
PROTECTED_TABLES = (
    "std_收入明细",
    "std_下单",
    "std_回款",
    "std_内部译员",
    "std_费用明细",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in PROTECTED_TABLES:
        try:
            row = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()
            out[t] = int(row[0]) if row else 0
        except sqlite3.Error:
            out[t] = -1
    return out


def _counts_fingerprint(counts: dict[str, int]) -> str:
    payload = json.dumps(counts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def backup_sqlite(
    src_db: Path | str,
    dest_dir: Path | str,
    *,
    version: str = "",
    commit: str = "",
    prefix: str = "看板",
) -> dict[str, Any]:
    """VACUUM/backup API 生成带 manifest 的备份。返回 meta（无表内容）。"""
    src = Path(src_db)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if not src.is_file():
        raise FileNotFoundError(f"db_missing:{src.name}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    short = (commit or "unknown")[:12]
    ver = (version or "0").replace("/", "-")
    base = f"{prefix}_{ver}_{short}_{ts}"
    db_out = dest / f"{base}.db"
    man_out = dest / f"{base}.manifest.json"

    # SQLite backup API
    src_conn = sqlite3.connect(f"file:{src.resolve()}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(str(db_out))
        try:
            src_conn.backup(dst_conn)
            counts = _table_counts(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    meta = {
        "version": version,
        "git_commit": commit,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_name": src.name,
        "source_sha256": _sha256_file(src),
        "backup_name": db_out.name,
        "backup_sha256": _sha256_file(db_out),
        "table_counts": counts,
        "counts_fp": _counts_fingerprint(counts),
    }
    # 原子写 manifest
    fd, tmp = tempfile.mkstemp(prefix=".man.", dir=str(dest))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, man_out)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    meta["manifest_path"] = str(man_out)
    meta["backup_path"] = str(db_out)
    return meta


def quick_check(db_path: Path | str) -> tuple[bool, str]:
    """最小完整性：能打开 + 关键表可查询。"""
    p = Path(db_path)
    if not p.is_file():
        return False, "missing"
    try:
        conn = sqlite3.connect(f"file:{p.resolve()}?mode=ro", uri=True)
        try:
            conn.execute("SELECT 1").fetchone()
            counts = _table_counts(conn)
        finally:
            conn.close()
    except sqlite3.Error as e:
        return False, f"sqlite:{type(e).__name__}"
    if all(v < 0 for v in counts.values()):
        return False, "no_protected_tables"
    return True, "ok"


def restore_isolated_verify(
    backup_db: Path | str,
    *,
    expected_counts_fp: str | None = None,
    work_dir: Path | str | None = None,
) -> dict[str, Any]:
    """隔离目录恢复验证：复制到临时库、quick_check、关键表指纹。

    不写回生产路径。失败抛 RuntimeError。
    """
    src = Path(backup_db)
    if not src.is_file():
        raise RuntimeError("backup_missing")
    ok, reason = quick_check(src)
    if not ok:
        raise RuntimeError(f"quick_check_fail:{reason}")

    wd = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="kanban_restore_"))
    wd.mkdir(parents=True, exist_ok=True)
    isolated = wd / "restored.db"
    # 用 backup API 再拷一份证明可读
    s = sqlite3.connect(f"file:{src.resolve()}?mode=ro", uri=True)
    try:
        d = sqlite3.connect(str(isolated))
        try:
            s.backup(d)
            counts = _table_counts(d)
        finally:
            d.close()
    finally:
        s.close()

    fp = _counts_fingerprint(counts)
    if expected_counts_fp and fp != expected_counts_fp:
        raise RuntimeError(f"counts_fp_mismatch:{fp}!={expected_counts_fp}")
    return {
        "ok": True,
        "isolated": str(isolated),
        "table_counts": counts,
        "counts_fp": fp,
    }
