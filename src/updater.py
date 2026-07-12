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


# ---------------- 依赖自动同步（拉取引入新 pip 包时避免重启缺包崩溃） ----------------
def _run_pip(root) -> tuple[int, str, str]:
    """用**当前正在跑服务的解释器**的 pip 装 requirements.txt（装进同一个 venv）。
    返回 (rc, stdout, stderr)。独立成函数便于测试替换（stub）。"""
    import sys
    req = _root(root) / "requirements.txt"
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)],
                           capture_output=True, text=True, timeout=600)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:  # pip 不存在 / 超时 / 其它
        return 1, "", f"{type(e).__name__}: {e}"


def _requirements_changed(root, before_ref) -> bool:
    """更新前后 requirements.txt 是否有变化（决定要不要 pip install）。
    无此文件→False（无需装）；更新前没有此文件（新加的）→True（装一次）。"""
    root = _root(root)
    req = root / "requirements.txt"
    if not req.exists():
        return False
    try:
        new = req.read_text(encoding="utf-8")
    except OSError:
        return False
    rc, old, _ = _git(root, "show", f"{before_ref}:requirements.txt")
    if rc != 0:
        return True
    return old != new


def _sync_deps_if_changed(root, before_ref) -> dict:
    """requirements.txt 变了就 pip install，没变则跳过。返回 {ok, changed, detail}。"""
    if not _requirements_changed(root, before_ref):
        return {"ok": True, "changed": False, "detail": "依赖无变化，跳过安装"}
    rc, out, err = _run_pip(root)
    if rc == 0:
        return {"ok": True, "changed": True, "detail": "依赖已按 requirements.txt 安装"}
    return {"ok": False, "changed": True, "detail": (err or out or "pip install 失败")[-800:]}


# ---------------- 更新回滚点（看门狗据此在"更新后启动即崩"时自动回滚一次） ----------------
def rollback_marker_path(root=None) -> Path:
    return _root(root) / ".update_rollback"


def write_rollback_marker(root, commit) -> None:
    """记录"更新前 commit"给看门狗。写失败不抛（不能因此挡住更新）。"""
    try:
        rollback_marker_path(root).write_text(str(commit or "").strip() + "\n", encoding="utf-8")
    except OSError:
        pass


def read_rollback_marker(root=None) -> str:
    try:
        return rollback_marker_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def clear_rollback_marker(root=None) -> None:
    """服务正常启动一段时间后清标记 = 确认这版没崩、无需回滚（server.serve 起 N 秒后调）。"""
    try:
        rollback_marker_path(root).unlink()
    except OSError:
        pass


def check_update(root=None, remote="origin", do_fetch=True) -> dict:
    """检测远端有没有新版本。do_fetch=True 时先 `git fetch`（只读）拿最新远端引用。
    remote=对标哪个远端（默认 origin；部署机从 Gitee clone 则 origin 即 Gitee，或配 update_remote 指定）。
    返回 available/supported/behind/ahead/dirty/can_update/reason/log(近10条远端提交摘要)。"""
    root = _root(root)
    remote = str(remote or "origin").strip() or "origin"
    if not is_repo(root):
        return {"supported": False, "available": False, "remote": remote,
                "reason": "非 git 仓库，一键更新不可用（需 git clone 部署）"}
    branch = _current_branch(root)
    if not branch:
        return {"supported": False, "available": False, "remote": remote,
                "reason": "当前处于游离 HEAD，无法判断分支，暂不支持一键更新"}
    up = f"{remote}/{branch}"
    if do_fetch:
        rc, _, err = _git(root, "fetch", "--quiet", remote, branch, timeout=90)
        if rc != 0:
            return {"supported": True, "available": False, "branch": branch, "remote": remote,
                    "reason": f"从远端「{remote}」拉取信息失败（网络/权限/远端不存在？）：{err or '未知错误'}"}
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
    return {"supported": True, "available": behind > 0, "branch": branch, "remote": remote,
            "ahead": ahead, "behind": behind, "dirty": dirty, "can_update": can_update,
            "reason": reason, "log": log,
            "local": _short(root, "HEAD"), "remote_rev": _short(root, up)}


def apply_update(root=None, remote="origin") -> dict:
    """安全拉取：先复检护栏（只读 fetch+比对），满足才 `git pull --ff-only <remote>`，
    拉取后**依赖变了自动 `pip install`**（装失败→回滚这次拉取、不重启），成功则写回滚点给看门狗。
    返回 {ok, reason, pulled, from, to, detail, deps, rolled_back}。**本函数不重启**；重启由调用方 request_restart。"""
    root = _root(root)
    remote = str(remote or "origin").strip() or "origin"
    chk = check_update(root, remote=remote, do_fetch=True)
    if not chk.get("supported"):
        return {"ok": False, "reason": chk.get("reason", "不支持一键更新")}
    if not chk.get("can_update"):
        return {"ok": False, "reason": chk.get("reason", "无需更新或不满足更新条件"),
                "behind": chk.get("behind", 0)}
    branch = chk["branch"]
    before = chk.get("local", "")
    rc, out, err = _git(root, "pull", "--ff-only", remote, branch, timeout=180)
    if rc != 0:
        return {"ok": False, "reason": f"git pull --ff-only 失败：{err or out or '未知错误'}"}
    # 依赖同步：requirements.txt 变了就装（拉取引入新包时不装，重启会缺包崩溃）
    deps = _sync_deps_if_changed(root, before)
    if not deps["ok"]:
        # 装依赖失败 → 回滚这次拉取，不带着装不上的新代码重启（更新期自愈）
        rb_rc, _, rb_err = _git(root, "reset", "--hard", before, timeout=60)
        return {"ok": False, "rolled_back": rb_rc == 0, "deps": deps,
                "reason": f"拉取成功但安装依赖失败，已回滚到更新前版本（{before}）：{deps['detail']}"
                          + ("" if rb_rc == 0 else f"；⚠回滚也失败（{rb_err}），请人工 `git reset --hard {before}`")}
    # 写"回滚点"给看门狗：这版若启动即崩，看门狗据此自动回滚一次（正常起 N 秒后 server 会清掉此标记）
    write_rollback_marker(root, before)
    return {"ok": True, "pulled": chk.get("behind", 0), "from": before,
            "to": _short(root, "HEAD"), "branch": branch, "detail": out, "deps": deps}


def request_restart(delay: float = 1.0) -> None:
    """触发进程重启：后台线程延时后以 RESTART_EXIT_CODE 退出（让 HTTP 响应先发回）；
    看门狗据码用新代码重新拉起。**没有看门狗时=服务停掉**（部署手册要求用 看门狗启动.bat 起）。"""
    def _bye():
        time.sleep(max(0.1, delay))
        os._exit(RESTART_EXIT_CODE)
    threading.Thread(target=_bye, daemon=True).start()
