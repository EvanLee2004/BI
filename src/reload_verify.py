# -*- coding: utf-8 -*-
"""reload 成功判据纯函数（3.6.0 G1）。

供 deploy/linux/reload_kanban.sh 与 tests 共用；禁止只凭 health=200 判绿。
"""

from __future__ import annotations

from typing import Any


def verify_process_switch(
    *,
    old_pid: str | int | None,
    new_pid: str | int | None,
    health_code: int | str,
    runtime_version: str | None,
    disk_version: str | None,
    runtime_commit: str | None = None,
    disk_commit: str | None = None,
    old_pid_still_alive: bool | None = None,
) -> tuple[bool, str]:
    """返回 (ok, reason)。

    失败路径：
    - health 非 200
    - 无新 PID
    - 新旧 PID 相同（未切换）
    - 旧 PID 仍存活（若显式传入）
    - 无 runtime version
    - runtime version ≠ disk version（两边都非空时）
    - commit 不一致（两边都非空时；允许 short/full 前缀互包）
    """
    try:
        code = int(health_code)
    except (TypeError, ValueError):
        return False, "health_code_invalid"

    if code != 200:
        return False, f"health_not_200:{code}"

    new_s = str(new_pid or "").strip()
    old_s = str(old_pid or "").strip()
    if not new_s or new_s in ("none", "0", "None"):
        return False, "no_new_pid"

    if old_s and old_s not in ("none", "0", "None") and new_s == old_s:
        return False, "pid_unchanged"

    if old_pid_still_alive is True and old_s and old_s not in ("none", "0", "None"):
        return False, "old_pid_still_alive"

    rv = (runtime_version or "").strip()
    dv = (disk_version or "").strip()
    if not rv:
        return False, "no_runtime_version"
    if dv and rv != dv:
        return False, f"version_mismatch:{rv}!={dv}"

    rc = (runtime_commit or "").strip()
    dc = (disk_commit or "").strip()
    if dc and rc:
        if not (
            dc.startswith(rc)
            or rc.startswith(dc)
            or rc.startswith(dc[:7])
            or dc.startswith(rc[:7])
        ):
            return False, f"commit_mismatch:{rc[:12]}!={dc[:12]}"

    return True, "ok"


def parse_health_metrics(body: str | bytes | dict[str, Any] | None) -> dict[str, Any]:
    """从 health JSON 抽取 version/git_commit/pid。"""
    import json

    if body is None:
        return {}
    if isinstance(body, dict):
        data = body
    else:
        try:
            data = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return {}
    if not isinstance(data, dict):
        return {}
    raw_m = data.get("metrics")
    m: dict[str, Any] = raw_m if isinstance(raw_m, dict) else {}
    return {
        "version": m.get("version") or data.get("version") or "",
        "git_commit": m.get("git_commit") or data.get("git_commit") or "",
        "pid": m.get("pid") or data.get("pid") or "",
    }


def is_expected_ops_exit(code: int | str | None) -> bool:
    """运维预期退出：0 正常、143=SIGTERM、130=SIGINT；不计入 crash-storm。"""
    try:
        c = int(code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return c in (0, 130, 143)
