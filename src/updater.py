#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""④ 一键更新 + 安全看门狗（2026-07-12 · 部署侧配套才完全激活）。

职责：只做「检测远端有没有新版本」和「安全地 `git pull --ff-only` 拉取」。
真正的**重启由看门狗脚本（看门狗启动.bat）接管**——服务进程不能干净重启自己，
故拉取成功后本进程以特殊退出码 `RESTART_EXIT_CODE` 退出，看门狗据此用新代码重新拉起。

护栏（安全第一：宁可不更新，也不弄坏部署机）：
- **只认 fast-forward**：`git pull --ff-only`，绝不产生合并/变基/冲突；
- 工作区不干净（有未提交改动）→ 拒绝，不覆盖本机改动；
- 本地领先/分叉远端（有远端没有的提交）→ 拒绝，交人工；
- 非 git 仓库 / 无 origin → 功能关闭（不报错，返回 supported=False）；
- 只在「严格落后且可快进」时才提示有新版本、才允许更新；
- 全部 git 命令带超时、捕获输出，绝不交互式挂起；
- 看门狗侧：非 42 退出=异常，连续多次则停下报警，避免坏版本无限重启。
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

RESTART_EXIT_CODE = 42   # 看门狗据此判「更新后重启」；须与 看门狗启动.bat 里的 42 一致
_TIMEOUT = 30            # 单条 git 命令默认超时（秒）
_ROOT = Path(__file__).resolve().parent.parent  # 程序根=git 仓库工作区（.git/run.py 所在层）


def _root(root=None) -> Path:
    return Path(root) if root else _ROOT


def _git(root, *args, timeout=_TIMEOUT):
    """跑一条 git 命令，返回 (rc, stdout, stderr)（都 strip）。失败/超时不抛，rc≠0。"""
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:  # git 不存在 / 超时 / 其它
        return 1, "", f"{type(e).__name__}: {e}"


def is_repo(root=None) -> bool:
    rc, out, _ = _git(_root(root), "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out == "true"


def _current_branch(root):
    rc, out, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return out if rc == 0 and out and out != "HEAD" else None


def _is_dirty(root) -> bool:
    """工作区有未提交改动（含未跟踪）→ True；查不出状态也当脏（宁可不更新）。"""
    rc, out, _ = _git(root, "status", "--porcelain")
    return bool(out.strip()) if rc == 0 else True


def _short(root, ref):
    rc, out, _ = _git(root, "rev-parse", "--short", ref)
    return out if rc == 0 else ""


def check_update(root=None, do_fetch=True) -> dict:
    """检测远端有没有新版本。do_fetch=True 时先 `git fetch`（只读）拿最新远端引用。
    返回 available/supported/behind/ahead/dirty/can_update/reason/log(近10条远端提交摘要)。"""
    root = _root(root)
    if not is_repo(root):
        return {"supported": False, "available": False,
                "reason": "非 git 仓库，一键更新不可用（需 git clone 部署）"}
    branch = _current_branch(root)
    if not branch:
        return {"supported": False, "available": False,
                "reason": "当前处于游离 HEAD，无法判断分支，暂不支持一键更新"}
    up = f"origin/{branch}"
    if do_fetch:
        rc, _, err = _git(root, "fetch", "--quiet", "origin", branch, timeout=90)
        if rc != 0:
            return {"supported": True, "available": False, "branch": branch,
                    "reason": f"拉取远端信息失败（网络/权限？）：{err or '未知错误'}"}
    rc, out, _ = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{up}")
    ahead = behind = 0
    if rc == 0 and out:
        parts = out.split()
        if len(parts) == 2:
            try:
                ahead, behind = int(parts[0]), int(parts[1])
            except ValueError:
                pass
    dirty = _is_dirty(root)
    log = []
    if behind:
        rc, out, _ = _git(root, "log", "--pretty=%s", f"HEAD..{up}", "-n", "10")
        if rc == 0 and out:
            log = [ln for ln in out.splitlines() if ln.strip()]
    can_update = behind > 0 and ahead == 0 and not dirty
    if behind == 0:
        reason = "已是最新版本"
    elif ahead > 0:
        reason = f"本地有 {ahead} 个未推送提交（与远端分叉），请人工处理，暂不自动更新"
    elif dirty:
        reason = "本地有未提交改动，先提交或还原再更新（避免被覆盖）"
    else:
        reason = f"有新版本：落后远端 {behind} 个提交，可一键更新"
    return {"supported": True, "available": behind > 0, "branch": branch,
            "ahead": ahead, "behind": behind, "dirty": dirty, "can_update": can_update,
            "reason": reason, "log": log,
            "local": _short(root, "HEAD"), "remote": _short(root, up)}


def apply_update(root=None) -> dict:
    """安全拉取：先复检护栏（只读 fetch+比对），满足才 `git pull --ff-only`。
    返回 {ok, reason, pulled, from, to, detail}。**本函数不重启**；重启由调用方 request_restart。"""
    root = _root(root)
    chk = check_update(root, do_fetch=True)
    if not chk.get("supported"):
        return {"ok": False, "reason": chk.get("reason", "不支持一键更新")}
    if not chk.get("can_update"):
        return {"ok": False, "reason": chk.get("reason", "无需更新或不满足更新条件"),
                "behind": chk.get("behind", 0)}
    branch = chk["branch"]
    before = chk.get("local", "")
    rc, out, err = _git(root, "pull", "--ff-only", "origin", branch, timeout=180)
    if rc != 0:
        return {"ok": False, "reason": f"git pull --ff-only 失败：{err or out or '未知错误'}"}
    return {"ok": True, "pulled": chk.get("behind", 0), "from": before,
            "to": _short(root, "HEAD"), "branch": branch, "detail": out}


def request_restart(delay: float = 1.0) -> None:
    """触发进程重启：后台线程延时后以 RESTART_EXIT_CODE 退出（让 HTTP 响应先发回）；
    看门狗据码用新代码重新拉起。**没有看门狗时=服务停掉**（部署手册要求用 看门狗启动.bat 起）。"""
    def _bye():
        time.sleep(max(0.1, delay))
        os._exit(RESTART_EXIT_CODE)
    threading.Thread(target=_bye, daemon=True).start()
