# -*- coding: utf-8 -*-
"""单机候选预热 / 切流纯函数（3.7.3）。

生产约束：systemd 单 worker · nginx 反代 127.0.0.1:8018 · SQLite 单库。
完整双机蓝绿不在本模块范围；本模块定义：

1. 候选端口预热成功判据（旁路 health 与磁盘 version/commit 对齐）
2. nginx upstream 片段生成（可原子写盘后 nginx -t && reload）
3. 切流决策状态机：warmup_ok → cut_to_candidate → recycle_primary → cut_back

禁止：只凭 health=200 无 runtime 对齐；禁止在纯函数里起进程或写盘。
"""

from __future__ import annotations

from typing import Any

from publish_preflight import _runtime_align
from reload_verify import _commits_compatible


def candidate_health_ok(
    *,
    health_code: int | str,
    runtime_version: str | None = None,
    disk_version: str | None = None,
    runtime_commit: str | None = None,
    disk_commit: str | None = None,
    runtime_pid: str | int | None = None,
    require_runtime_align: bool = False,
) -> tuple[bool, str]:
    """旁路候选预热成功判据。

    默认（require_runtime_align=False）：health 200 即通过。
    候选不写共享 runtime_marker，避免盖住主进程标记；故默认不强制 metrics 对齐。
    严格模式才校验 version/commit/pid（主进程切流后用 publish_preflight）。
    """
    try:
        code = int(health_code)
    except (TypeError, ValueError):
        return False, "health_code_invalid"
    if code != 200:
        return False, f"health_not_200:{code}"
    if not require_runtime_align:
        return True, "ok_http_200"
    return _runtime_align(
        runtime_version=runtime_version,
        disk_version=disk_version,
        runtime_commit=runtime_commit,
        disk_commit=disk_commit,
        runtime_pid=runtime_pid,
    )


def render_upstream_conf(port: int, *, host: str = "127.0.0.1") -> str:
    """生成 nginx upstream 片段（整文件内容）。"""
    p = int(port)
    if p < 1 or p > 65535:
        raise ValueError(f"invalid_port:{port}")
    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    return (
        f"# managed by publish_kanban blue-green — do not hand-edit\n"
        f"upstream kanban_api {{\n"
        f"    server {h}:{p};\n"
        f"    keepalive 8;\n"
        f"}}\n"
    )


def parse_upstream_port(conf_text: str) -> int | None:
    """从 render_upstream_conf 产物解析端口；解析失败返回 None。"""
    import re

    m = re.search(r"server\s+[\w\.\-]+:(\d+)\s*;", conf_text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def cutover_plan(
    *,
    primary_port: int = 8018,
    candidate_port: int = 8019,
    candidate_ok: bool,
    nginx_cutover: bool,
) -> dict[str, Any]:
    """返回有序步骤列表（供 shell 执行/测试断言）。

    candidate_ok=False → 仅 abort，不碰主流量。
    nginx_cutover=False → 预热后 systemctl 重启主端口（短窗口断连，仍优于盲重启）。
    nginx_cutover=True → 先把 upstream 切到候选，再回收主端口，最后切回主端口。
    """
    if primary_port == candidate_port:
        return {
            "ok": False,
            "reason": "ports_must_differ",
            "steps": [],
        }
    if not candidate_ok:
        return {
            "ok": False,
            "reason": "candidate_not_ready",
            "steps": [
                {"action": "kill_candidate", "port": candidate_port},
                {"action": "abort_keep_primary", "port": primary_port},
            ],
        }
    if not nginx_cutover:
        return {
            "ok": True,
            "reason": "warm_then_reload_primary",
            "steps": [
                {"action": "reload_primary", "port": primary_port},
                {"action": "verify_primary", "port": primary_port},
                {"action": "kill_candidate", "port": candidate_port},
            ],
        }
    return {
        "ok": True,
        "reason": "nginx_cutover",
        "steps": [
            {"action": "write_upstream", "port": candidate_port},
            {"action": "nginx_reload"},
            {"action": "verify_via_upstream", "port": candidate_port},
            {"action": "reload_primary", "port": primary_port},
            {"action": "verify_primary", "port": primary_port},
            {"action": "write_upstream", "port": primary_port},
            {"action": "nginx_reload"},
            {"action": "kill_candidate", "port": candidate_port},
            {"action": "verify_primary", "port": primary_port},
        ],
    }


def should_reset_git_on_candidate_fail(
    *,
    pulled: bool,
    candidate_ok: bool,
    prev_commit: str | None,
) -> bool:
    """pull 后候选失败且有 prev_commit → 应 reset 磁盘回 prev（主进程尚未切）。"""
    if candidate_ok:
        return False
    if not pulled:
        return False
    return bool((prev_commit or "").strip())


def commits_match(a: str | None, b: str | None) -> bool:
    aa, bb = (a or "").strip(), (b or "").strip()
    if not aa or not bb:
        return False
    return _commits_compatible(aa, bb)
