# -*- coding: utf-8 -*-
"""持久安装状态（3.6.0 G1）。

首次安装判定不得依赖进程内 ``_state.has_data``。
状态落 data_dir/install_state.json（原子写）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

InstallPhase = Literal["fresh", "unconfigured", "configured", "ready", "degraded"]

STATE_NAME = "install_state.json"
VALID_PHASES = frozenset({"fresh", "unconfigured", "configured", "ready", "degraded"})


def state_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / STATE_NAME


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".install_state.", dir=str(path.parent))
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


def load_install_state(data_dir: Path | str) -> dict[str, Any]:
    p = state_path(data_dir)
    if not p.is_file():
        return {"phase": "fresh", "version": 1}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 损坏：隔离不 seed 覆盖（返回 degraded 视图，保留文件）
        return {"phase": "degraded", "version": 1, "corrupt": True, "path": str(p)}
    if not isinstance(raw, dict):
        return {"phase": "degraded", "version": 1, "corrupt": True}
    phase = str(raw.get("phase") or "fresh")
    if phase not in VALID_PHASES:
        phase = "degraded"
    out = dict(raw)
    out["phase"] = phase
    return out


def save_install_state(data_dir: Path | str, state: dict[str, Any]) -> Path:
    phase = str(state.get("phase") or "fresh")
    if phase not in VALID_PHASES:
        raise ValueError(f"invalid install phase: {phase}")
    payload = dict(state)
    payload["phase"] = phase
    payload.setdefault("version", 1)
    p = state_path(data_dir)
    _atomic_write(p, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return p


def detect_phase(
    *,
    has_accounts: bool,
    has_db: bool,
    has_source_files: bool,
    has_lkg: bool,
    last_build_ok: bool | None,
    prior_phase: str | None = None,
) -> InstallPhase:
    """纯函数：由磁盘事实推断 phase（不读内存 has_data）。"""
    if not has_accounts and not has_db and not has_source_files:
        return "fresh"
    if has_accounts and not has_source_files and not has_db:
        return "unconfigured"
    if last_build_ok is False and (has_lkg or has_db or has_source_files):
        return "degraded"
    if has_db or last_build_ok is True:
        return "ready"
    if has_accounts and has_source_files:
        return "configured"
    if prior_phase in VALID_PHASES:
        return prior_phase  # type: ignore[return-value]
    return "configured"


def bootstrap_allowed(
    *,
    phase: str,
    has_accounts: bool,
    has_db: bool,
    has_source_files: bool,
    has_lkg: bool,
    memory_has_data: bool = False,
) -> bool:
    """是否允许展示「首次安装」引导页。

    规则：
    - fresh：无账号/无库/无源 → 允许；
    - unconfigured：仅有账号、尚无业务库/源文件/LKG → 允许（空机 seed 账号后的首次取数引导）；
    - configured/ready/degraded（有库/源/LKG）→ **禁止**（即使 memory has_data=False）；
    - memory_has_data=True 时禁止 bootstrap（本进程已构建成功，测试/热路径）；
    - memory_has_data=False 时仍须看磁盘，不得仅凭空内存进 bootstrap（防 CRC 误进首次安装）。
    """
    _ = has_accounts
    if memory_has_data:
        return False
    if has_db or has_source_files or has_lkg:
        return False
    if phase in ("fresh", "unconfigured"):
        return True
    return False


def _db_has_business_rows(db_path: Path) -> bool:
    """库文件存在且关键业务表有行（空 schema 不算「已安装业务」）。"""
    if not db_path.is_file() or db_path.stat().st_size < 4096:
        return False
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            for t in ("std_下单", "std_收入明细", "std_回款", "std_费用明细"):
                try:
                    n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()
                    if n and int(n[0]) > 0:
                        return True
                except sqlite3.Error:
                    continue
        finally:
            conn.close()
    except Exception:
        return False
    return False


def probe_disk_facts(data_dir: Path | str, cfg: dict | None = None) -> dict[str, bool]:
    """扫描 data_dir 得到安装事实（无真实业务内容泄漏）。"""
    d = Path(data_dir)
    files = (cfg or {}).get("files") or {}
    order = files.get("orders") or "下单.xlsx"
    detail = (files.get("project_detail_stem") or "项目明细") + ".xlsx"
    has_src = (d / order).is_file() or (d / detail).is_file()
    dbp = d / ((cfg or {}).get("db_path") or "看板.db")
    has_db = _db_has_business_rows(dbp)
    has_acc = (d / "看板账号.json").is_file()
    snap_dir = d / "快照存档"
    has_lkg = (d / "lkg" / "snapshot.json").is_file() or (
        snap_dir.is_dir() and any(snap_dir.rglob("*.json"))
    )
    return {
        "has_accounts": has_acc,
        "has_db": has_db,
        "has_source_files": has_src,
        "has_lkg": bool(has_lkg),
    }


def resolve_admin_entry(
    data_dir: Path | str,
    *,
    cfg: dict | None = None,
    memory_has_data: bool = False,
    last_build_ok: bool | None = None,
) -> str:
    """管理端入口决策：bootstrap | spa | maintenance。

    - bootstrap：仅真正首次
    - spa：ready/configured（有安装事实）
    - maintenance：degraded 且无可用展示
    """
    if memory_has_data:
        return "spa"
    facts = probe_disk_facts(data_dir, cfg)
    st = load_install_state(data_dir)
    phase = detect_phase(
        has_accounts=facts["has_accounts"],
        has_db=facts["has_db"],
        has_source_files=facts["has_source_files"],
        has_lkg=facts["has_lkg"],
        last_build_ok=last_build_ok,
        prior_phase=str(st.get("phase") or ""),
    )
    if bootstrap_allowed(
        phase=phase,
        has_accounts=facts["has_accounts"],
        has_db=facts["has_db"],
        has_source_files=facts["has_source_files"],
        has_lkg=facts["has_lkg"],
        memory_has_data=memory_has_data,
    ):
        return "bootstrap"
    if phase == "degraded" and not facts["has_lkg"] and not memory_has_data and not facts["has_db"]:
        return "maintenance"
    return "spa"


def mark_ready(data_dir: Path | str, *, version: str = "", commit: str = "") -> Path:
    return save_install_state(
        data_dir,
        {
            "phase": "ready",
            "version": 1,
            "product_version": version,
            "git_commit": commit,
        },
    )


def mark_degraded(data_dir: Path | str, *, reason: str = "") -> Path:
    st = load_install_state(data_dir)
    st["phase"] = "degraded"
    if reason:
        st["reason"] = reason[:200]
    return save_install_state(data_dir, st)
