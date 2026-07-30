# -*- coding: utf-8 -*-
"""运行时版本/commit marker（3.5.0）。

reload / health 用此文件证明「新进程 + 新构建」，不依赖磁盘 VERSION 单点，
也不依赖 serve 进程能否在沙箱里执行 git 或读 .git。

写入路径：``数据/runtime_marker.json``（在 ReadWritePaths 内）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


MARKER_NAME = "runtime_marker.json"


def marker_path(root: Path | str) -> Path:
    root = Path(root)
    data = root / "数据"
    # 与 loaders 默认 data_dir 一致；若无「数据」夹则落程序根（仅兜底）
    if data.is_dir() or not (root / "VERSION").exists():
        data.mkdir(parents=True, exist_ok=True)
        return data / MARKER_NAME
    return root / MARKER_NAME


def _read_version(root: Path) -> str:
    try:
        v = (root / "VERSION").read_text(encoding="utf-8").strip()
        return v or ""
    except OSError:
        return ""


def _resolve_git_dir(root: Path) -> Path | None:
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    if git_dir.is_file():
        try:
            text = git_dir.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            gd = Path(text.split(":", 1)[1].strip())
            if not gd.is_absolute():
                gd = (root / gd).resolve()
            return gd if gd.exists() else None
        return None
    return git_dir


def _read_git_commit_from_files(root: Path) -> str:
    git_dir = _resolve_git_dir(root)
    if not git_dir:
        return ""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        try:
            return (git_dir / ref).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return head if len(head) >= 7 else ""


def _read_git_commit(root: Path) -> str:
    """优先读 .git；失败再尝试 git 子进程。"""
    c = _read_git_commit_from_files(root)
    if c:
        return c
    try:
        import subprocess

        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def write_runtime_marker(
    root: Path | str,
    *,
    pid: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写入/刷新 marker；返回写入内容。"""
    root = Path(root)
    payload: dict[str, Any] = {
        "version": _read_version(root),
        "git_commit": _read_git_commit(root),
        "pid": int(pid if pid is not None else os.getpid()),
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": int(time.time()),
    }
    if extra:
        payload.update(extra)
    path = marker_path(root)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def read_runtime_marker(root: Path | str) -> dict[str, Any]:
    """读 marker；缺文件或坏 JSON → {}。"""
    path = marker_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def runtime_identity(root: Path | str) -> dict[str, Any]:
    """供 health：marker 优先，否则即时探测。"""
    m = read_runtime_marker(root)
    root_p = Path(root)
    out = {
        "version": str(m.get("version") or _read_version(root_p) or ""),
        "git_commit": str(m.get("git_commit") or _read_git_commit(root_p) or ""),
        "pid": int(m.get("pid") or os.getpid()),
        "written_at": str(m.get("written_at") or ""),
        "marker": bool(m),
    }
    return out
