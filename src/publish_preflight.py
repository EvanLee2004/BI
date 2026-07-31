# -*- coding: utf-8 -*-
"""发布链门闸纯函数（3.7.0 · P1-02/P1-03）。

- 备份元数据必须含路径与校验信息才允许继续
- 宣告成功须 version + commit + pid + health 全齐
禁止只凭磁盘 VERSION 或单独 health=200 判绿。
"""

from __future__ import annotations

from typing import Any

from reload_verify import _commits_compatible, verify_process_switch


def require_backup_meta(meta: dict[str, Any] | None) -> tuple[bool, str]:
    """校验 backup_sqlite 返回值：须有 backup_path + 至少一个校验字段。"""
    if not isinstance(meta, dict) or not meta:
        return False, "backup_meta_missing"
    path = str(meta.get("backup_path") or "").strip()
    if not path:
        return False, "backup_path_missing"
    sha = str(meta.get("backup_sha256") or meta.get("source_sha256") or "").strip()
    man = str(meta.get("manifest_path") or "").strip()
    if not sha and not man:
        return False, "backup_integrity_missing"
    return True, "ok"


def _health_ok(health_code: int | str) -> tuple[bool, str]:
    try:
        code = int(health_code)
    except (TypeError, ValueError):
        return False, "health_code_invalid"
    if code != 200:
        return False, f"health_not_200:{code}"
    return True, "ok"


def _runtime_align(
    *,
    runtime_version: str | None,
    disk_version: str | None,
    runtime_commit: str | None,
    disk_commit: str | None,
    runtime_pid: str | int | None,
) -> tuple[bool, str]:
    rv = (runtime_version or "").strip()
    dv = (disk_version or "").strip()
    if not rv:
        return False, "no_runtime_version"
    if dv and rv != dv:
        return False, f"version_mismatch:{rv}!={dv}"
    rc = (runtime_commit or "").strip()
    dc = (disk_commit or "").strip()
    if dc and not rc:
        return False, "no_runtime_commit"
    if dc and rc and not _commits_compatible(rc, dc):
        return False, f"commit_mismatch:{rc[:12]}!={dc[:12]}"
    pid = str(runtime_pid or "").strip()
    if not pid or pid in ("none", "0", "None"):
        return False, "no_runtime_pid"
    return True, "ok"


def declare_publish_success(
    *,
    health_code: int | str,
    runtime_version: str | None,
    disk_version: str | None,
    runtime_commit: str | None,
    disk_commit: str | None,
    runtime_pid: str | int | None,
    backup_ok: bool,
    process_switch_ok: bool | None = None,
    old_pid: str | int | None = None,
    new_pid: str | int | None = None,
    old_pid_still_alive: bool | None = None,
) -> tuple[bool, str]:
    """发布成功唯一出口：备份已做 + 进程/runtime 门闸。"""
    if not backup_ok:
        return False, "backup_required"

    if process_switch_ok is None:
        switch_ok, switch_reason = verify_process_switch(
            old_pid=old_pid,
            new_pid=new_pid if new_pid is not None else runtime_pid,
            health_code=health_code,
            runtime_version=runtime_version,
            disk_version=disk_version,
            runtime_commit=runtime_commit,
            disk_commit=disk_commit,
            old_pid_still_alive=old_pid_still_alive,
        )
        if not switch_ok:
            return False, switch_reason
    elif not process_switch_ok:
        return False, "process_switch_not_ok"

    ok_h, reason_h = _health_ok(health_code)
    if not ok_h:
        return False, reason_h

    return _runtime_align(
        runtime_version=runtime_version,
        disk_version=disk_version,
        runtime_commit=runtime_commit,
        disk_commit=disk_commit,
        runtime_pid=runtime_pid,
    )
