#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网双端服务（FastAPI + uvicorn）：用户端只读 + 管理员控制台（明细编辑/手填/年度预算/调整台账）。

- 用户端 `/`：账号+密码登录，按 数据/看板账号.json 权限分流（管理员→/admin、整体→整体页、BU→本 BU 页）。
- 管理员端 `/admin`：账号 lushasha（或任何权限=管理员的号）+ 密码；经手人=登录账号。
- `/api/detail`：明细数据，**仅管理员会话内可用**（服务端挡，未登录 401；非前端藏）。
- `/api/health`：最近一次运行日志（体检状态条数据源）。

安全实现用标准库：会话 HMAC 签名 token；账号明文存 数据/看板账号.json（不进 git）。
会话签名密钥存 数据/管理员密钥.json（只保留 cookie_key；旧 salt/pw_hash 字段读时忽略）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import loaders
import accounts
import bu
import db
import core
import ingest
import render
import assets
import version as product_version
import updater

COOKIE = "kanban_session"
VCOOKIE = "kanban_view"   # 查看端会话：主体=登录账号名（v8.0）
SESSION_TTL = 24 * 3600
# 管理员会话看内嵌看板时隐藏「🔑密码」自改入口（管理员改密走 /admin 设置页，避免误改）
_HIDE_PW_STYLE = '<style>#pwBtn{display:none!important}</style>'
# 兼容旧测试/文档引用（v8.0 起管理员口令在 看板账号.json，不再走密钥哈希）
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", accounts.DEFAULT_ADMIN_PW)
DEFAULT_VIEW_PW = accounts.DEFAULT_VIEW_PW
DEFAULT_ADMIN_ACCOUNT = "lushasha"

# 服务内存态：当前汇总 + 渲染好的两端页面 + 上次规范化的原始记录（供秒级重算）
# refreshing/last_refresh：后台「立即更新」的进行中标记与最近一次结果（/api/refresh_status 用）
_state: dict = {"summary": None, "user_html": "", "admin_html": "", "built_at": None, "records": None,
                "refreshing": None, "last_refresh": None, "bu_pages": {}}
_LOCK = threading.Lock()  # 写库/重算全局互斥（03：写库一把锁，运行中排队）
_EXPORT_LOCK = threading.Lock()  # 导出截图互斥：Playwright 整页截图是重活，同一时刻只跑一张，连发返回 429


# ---------------- 密钥文件（仅会话签名 cookie_key；口令改由 accounts 管） ----------------
def _secret_path(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / "管理员密钥.json"


def _load_or_init_secret(cfg, root=None) -> dict:
    """读/建会话签名密钥。旧文件可能还带 salt/pw_hash/viewer_*（v7.x），读时保留不删、不再使用。"""
    p = _secret_path(cfg, root)
    if p.exists():
        try:
            sec = json.loads(p.read_text(encoding="utf-8"))
            if sec.get("cookie_key"):
                return sec
        except (OSError, ValueError):
            pass
    sec = {"cookie_key": os.urandom(32).hex()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[server] 已生成会话密钥文件：{p}（账号口令见 数据/看板账号.json）")
    return sec


def _save_secret(cfg, root, sec: dict) -> None:
    p = _secret_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- 会话 token（HMAC 签名，含过期） ----------------
def _make_token(sec: dict, user: str, now: float | None = None) -> str:
    """签发会话。user=登录账号名（管理员 cookie 与查看 cookie 都存账号，权限运行时再查）。"""
    now = time.time() if now is None else now
    payload = f"{user}|{int(now + SESSION_TTL)}".encode()
    b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(bytes.fromhex(sec["cookie_key"]), b64, hashlib.sha256).hexdigest()
    return b64.decode() + "." + sig


def _check_token_raw(sec: dict, token: str, now: float | None = None) -> str | None:
    """校验 HMAC+过期，返回主体字符串（账号名）；无效 None。不查权限。"""
    now = time.time() if now is None else now
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expect = hmac.new(bytes.fromhex(sec["cookie_key"]), b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        user, exp = base64.urlsafe_b64decode(b64.encode()).decode().split("|", 1)
    except (ValueError, TypeError):
        return None
    if float(exp) < now:
        return None
    return user or None


def _check_token(sec: dict, token: str, now: float | None = None) -> str | None:
    """管理员会话 cookie → 账号名（是否仍是管理员由调用方再查账号表）。"""
    return _check_token_raw(sec, token, now)


def _check_vsubject(sec: dict, token: str, now: float | None = None) -> str | None:
    """查看端会话（cookie kanban_view）：返回登录账号名；无效 None。
    v8.0 起主体=账号（不再是 main/bu:xxx）；权限在请求时从账号表解析。"""
    return _check_token_raw(sec, token, now)

# ---------------- 渲染缓存 ----------------
def _publish(cfg, summary, html, bu_pages=None):
    _state["summary"] = summary
    _state["user_html"] = html
    _state["admin_html"] = _admin_page(html, summary)
    if bu_pages is not None:
        _state["bu_pages"] = bu_pages
    _state["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    summary, html, ing, bu_pages = core.generate(cfg, today, trigger=trigger)
    _state["records"] = ing.get("records")  # 缓存原始记录供秒级重算
    _publish(cfg, summary, html, bu_pages)
    return ing


def _do_recompute(cfg, root) -> None:
    if not _state.get("records"):
        _do_full(cfg, root, "manual")
        return
    today = loaders.pinned_today(cfg)
    logo = assets.load_logo_base64(cfg)
    conn = db.connect(cfg, root)
    try:
        ingest.reapply(cfg, conn, _state["records"], today)
        summary = core.summary_from_conn(cfg, conn, today)
        bu_pages = core.build_bu_pages(cfg, conn, today, logo, root)
        core.attach_unassigned(cfg, conn, today, summary, root)
    finally:
        conn.close()
    html = render.render_dashboard(summary, cfg, logo)
    _publish(cfg, summary, html, bu_pages)


def refresh(cfg, root=None, trigger="manual") -> dict:
    """完整更新（fetch+重读xlsx+重建+重放）+ 渲染两端，刷新缓存。启动与 /api/refresh 用。"""
    with _LOCK:
        return _do_full(cfg, root, trigger)


def start_refresh_async(cfg, root=None, trigger="manual") -> bool:
    """后台线程跑完整更新（在线抓开着约80秒，不能同步阻塞按钮）。
    拿到锁→起线程返回 True；拿不到（已在更新）返回 False。进度看 _state["refreshing"]/["last_refresh"]。"""
    if not _LOCK.acquire(blocking=False):
        return False
    _state["refreshing"] = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger}

    def _job():
        t0 = time.time()
        try:
            ing = _do_full(cfg, root, trigger)
            _state["last_refresh"] = {"status": "ok", "result": ing.get("result"),
                                      "seconds": round(time.time() - t0, 1),
                                      "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as e:  # 失败也要落状态，前端能看到为啥
            _state["last_refresh"] = {"status": "error", "detail": f"{type(e).__name__}: {e}",
                                      "seconds": round(time.time() - t0, 1),
                                      "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        finally:
            _state["refreshing"] = None
            _LOCK.release()

    threading.Thread(target=_job, daemon=True).start()
    return True


# ---------------- 设置（config.json 可改项：自动更新时间/备份保留天数/在线抓开关） ----------------
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SCHTASK_NAME = "经营驾驶舱每日更新"  # 与 注册每日更新.bat 里的 TN 一致

EDITABLE_SETTINGS = ("schedule_time", "backup_keep_days", "zhiyun_auto_fetch")
MAX_SCHEDULE_TIMES = 6  # 每天最多几个自动更新时间点（09:30/12:00/17:30… 3 个已够，留余量）


def normalize_schedule_times(value, fallback=None) -> list[str]:
    """把「多次更新时间」规范成有序去重的 HH:MM 列表（②多次更新时间）。
    接受：list（元素 HH:MM）/ 单个 "HH:MM" / 顿号·逗号·分号·空白分隔的串。
    每个 HH:MM 走 _TIME_RE 校验（24 小时制）→ 去重、升序；空/非法/超上限 → ValueError。"""
    if value is None:
        value = fallback
    if isinstance(value, str):
        value = re.split(r"[、，,;；\s]+", value.strip())
    if not isinstance(value, (list, tuple)):
        raise ValueError("更新时间格式不对（应为 HH:MM 列表）")
    seen, out = set(), []
    for v in value:
        s = str(v).strip()
        if not s:
            continue
        if not _TIME_RE.match(s):
            raise ValueError(f"更新时间「{s}」格式须为 HH:MM（24小时制），如 09:30")
        if s not in seen:
            seen.add(s)
            out.append(s)
    if not out:
        raise ValueError("至少保留一个自动更新时间点")
    if len(out) > MAX_SCHEDULE_TIMES:
        raise ValueError(f"自动更新时间点最多 {MAX_SCHEDULE_TIMES} 个")
    return sorted(out)


def get_schedule_times(cfg) -> list[str]:
    """读当前配置的更新时间列表：优先 schedule_times（新），缺失则从旧 schedule_time 单值推导。"""
    raw = cfg.get("schedule_times")
    if raw:
        try:
            return normalize_schedule_times(raw)
        except ValueError:
            pass
    try:
        return normalize_schedule_times(cfg.get("schedule_time") or "09:30")
    except ValueError:
        return ["09:30"]


def _schtask_command(root=None) -> str:
    """计划任务要跑的命令：<当前解释器> <run.py> --scheduled（部署机上解释器=venv python）。"""
    import sys
    py = sys.executable or "python"
    runpy = str((root or loaders.ROOT) / "run.py")
    return f'"{py}" "{runpy}" --scheduled'


def _win_task_names(n: int) -> list[str]:
    """n 个时间点对应的计划任务名：第 1 个=主名（铁律，须与 .bat 一致），其余 _2.._n。"""
    return [SCHTASK_NAME] + [f"{SCHTASK_NAME}_{i}" for i in range(2, n + 1)]


def _win_sync_schedule(times: list[str], root=None) -> str:
    """Windows：把计划任务同步成 times 里每个时间点各一个任务（主名 + _2.._n）。
    先试 /Change（改已存在任务的时间，通常不需提权）→ 不存在则 /Create（可能需提权）；
    再删掉多出来的编号任务（时间点变少时）。全程 best-effort + try/except，
    **永不抛异常打断保存**；返回人读备注。非 Windows 不会走到这里。"""
    import subprocess
    tr = _schtask_command(root)
    names = _win_task_names(len(times))
    created = changed = failed = 0
    try:
        for name, t in zip(names, times):
            r = subprocess.run(["schtasks", "/Change", "/TN", name, "/ST", t],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                changed += 1
                continue
            rc = subprocess.run(["schtasks", "/Create", "/TN", name, "/SC", "DAILY",
                                 "/ST", t, "/TR", tr, "/F"], capture_output=True, timeout=15)
            if rc.returncode == 0:
                created += 1
            else:
                failed += 1
        for i in range(len(times) + 1, MAX_SCHEDULE_TIMES + 2):  # 删多余编号任务
            subprocess.run(["schtasks", "/Delete", "/TN", f"{SCHTASK_NAME}_{i}", "/F"],
                           capture_output=True, timeout=15)
    except Exception:
        return "；⚠计划任务同步出错——请以管理员身份重跑 注册每日更新.bat"
    if failed:
        return (f"；⚠有 {failed} 个时间点没同步成（多半需管理员权限）"
                "——请以管理员身份重跑 注册每日更新.bat")
    return f"；计划任务已同步（{len(times)} 个时间点：{'、'.join(times)}）"


def _config_file(root=None) -> Path:
    return (root or loaders.ROOT) / "config.json"


def _zhiyun_cfg_file(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / "智云配置.json"


def read_zhiyun_creds(cfg, root=None) -> dict:
    """读智云账号密码（给设置页显示；管理员会话内可见，与部署机本地明文配置同权限层级）。"""
    p = _zhiyun_cfg_file(cfg, root)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"username": d.get("username", ""), "password": d.get("password", "")}
    except (OSError, ValueError):
        return {"username": "", "password": ""}


def save_zhiyun_creds(cfg, root, username: str, password: str) -> bool:
    """账号或密码变了才写：更新 username/password + 清掉旧会话（md_pss_id/account_id），
    下次更新自动用新账号登录、account_id 登录时自动获取——换陆总号只需在界面填这两样。
    返回是否发生了变更。"""
    p = _zhiyun_cfg_file(cfg, root)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("username") == username and d.get("password") == password:
        return False
    d["username"], d["password"] = username, password
    d["md_pss_id"] = ""      # 旧会话作废，强制新账号重登
    d["account_id"] = ""     # 登录时从页面全局变量自动取新账号的 GUID
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def save_settings(cfg, root, payload: dict) -> dict:
    """校验并落盘设置（支持各卡就近保存：只传要改的字段即可）。
    改运行中 cfg + 重写 config.json。Windows 上改更新时间会顺手同步计划任务（多时间点=多任务）。"""
    # 更新时间：新字段 schedule_times（列表·②多次更新）优先；兼容旧 schedule_time（单值）
    changed_times = ("schedule_times" in payload) or ("schedule_time" in payload)
    if "schedule_times" in payload:
        times = normalize_schedule_times(payload["schedule_times"])
    elif "schedule_time" in payload:
        times = normalize_schedule_times(payload["schedule_time"])
    else:
        times = get_schedule_times(cfg)
    st = times[0]  # 旧字段镜像=最早的时间点（向后兼容 .bat / 读单值的地方）
    if "backup_keep_days" in payload:
        try:
            keep = int(payload.get("backup_keep_days"))
        except (TypeError, ValueError):
            raise ValueError("备份保留天数须为整数")
    else:
        keep = int(cfg.get("backup_keep_days", 30))
    if not (1 <= keep <= 365):
        raise ValueError("备份保留天数须在 1~365 之间")
    auto = bool(payload.get("zhiyun_auto_fetch", cfg.get("zhiyun_auto_fetch", False))) \
        if "zhiyun_auto_fetch" in payload else bool(cfg.get("zhiyun_auto_fetch", False))

    cfg["schedule_time"], cfg["backup_keep_days"], cfg["zhiyun_auto_fetch"] = st, keep, auto
    cfg["schedule_times"] = times
    p = _config_file(root)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["schedule_time"], raw["backup_keep_days"], raw["zhiyun_auto_fetch"] = st, keep, auto
    raw["schedule_times"] = times
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    zu, zp = payload.get("zhiyun_username"), payload.get("zhiyun_password")
    cred_note = ""
    if zu is not None and zp is not None:
        zu, zp = str(zu).strip(), str(zp)
        if not zu or not zp:
            raise ValueError("智云账号和密码都不能为空")
        if save_zhiyun_creds(cfg, root, zu, zp):
            cred_note = "；智云账号已更新（下次更新自动用新账号登录）"

    note = "已保存" + cred_note
    # 仅当本次真的提交了更新时间时才动计划任务（各卡就近保存）
    if changed_times:
        import sys
        if sys.platform == "win32":
            note += _win_sync_schedule(times, root)
        else:
            note += f"（本机非 Windows：{len(times)} 个时间点在部署机上生效）"
    return {"schedule_time": st, "schedule_times": times,
            "backup_keep_days": keep, "zhiyun_auto_fetch": auto, "note": note}


def recompute(cfg, root=None) -> None:
    """**秒级重算**（保存调整/手填后）：缓存记录重置标准表→重放→重算→重渲染，不读 xlsx。"""
    with _LOCK:
        _do_recompute(cfg, root)


# ---------------- 配置变更留痕（C3）：写接口 diff → 人读摘要 → db.log_config_change ----------------
def _audit(cfg, root, account, changes) -> None:
    """写配置变更留痕。changes=(类别,摘要) 或其列表；空摘要跳过。摘要绝不含密码明文（调用方脱敏）。"""
    if not changes:
        return
    if isinstance(changes, tuple):
        changes = [changes]
    conn = db.connect(cfg, root)
    try:
        for cat, summ in changes:
            db.log_config_change(conn, account, cat, summ)
    finally:
        conn.close()


def _join_summary(prefix: str, items: list[str], cap: int = 8) -> str:
    """把多条变更并成一句人读摘要；超过 cap 条只列前 cap 条 + 总数（防超长）。"""
    if len(items) <= cap:
        return prefix + "；".join(items)
    return prefix + "；".join(items[:cap]) + f"；等共 {len(items)} 项"


def _diff_bu_config(old_bus: list, new_bus: list,
                    old_alloc: bool = False, new_alloc: bool = False) -> list:
    """销售归属/BU 结构/分摊比例变化 → [(类别,摘要)]（old/new 均规范化 bus 列表）。"""
    def sale_map(bus):
        m = {}
        for b in bus:
            for s in b.get("销售") or []:
                m[str(s).strip()] = b["name"]
        return m

    om, nm = sale_map(old_bus), sale_map(new_bus)
    moves = [f"{s} {om.get(s) or '未归属'}→{nm.get(s) or '未归属'}"
             for s in sorted(set(om) | set(nm)) if om.get(s) != nm.get(s)]
    onames = {b["name"] for b in old_bus}
    nnames = {b["name"] for b in new_bus}
    oown = {b["name"]: "、".join(b.get("负责人") or []) for b in old_bus}
    nown = {b["name"]: "、".join(b.get("负责人") or []) for b in new_bus}
    struct = ([f"新增 BU {x}" for x in sorted(nnames - onames)]
              + [f"删除 BU {x}" for x in sorted(onames - nnames)]
              + [f"{x} 负责人改为「{nown.get(x) or '（空）'}」"
                 for x in sorted(nnames & onames) if oown.get(x) != nown.get(x)])
    out = []
    if moves:
        out.append(("销售归属", _join_summary("销售归属：", moves)))
    if struct:
        out.append(("BU配置", _join_summary("BU配置：", struct)))
    # 分摊开关 + 各 BU 比例（不存敏感值，只记百分比数字）
    alloc_lines = []
    if bool(old_alloc) != bool(new_alloc):
        alloc_lines.append(f"公共费用分摊 {'开' if new_alloc else '关'}←{'开' if old_alloc else '关'}")
    orat = {b["name"]: b.get("分摊比例") for b in old_bus}
    nrat = {b["name"]: b.get("分摊比例") for b in new_bus}
    for nm in sorted(set(orat) | set(nrat)):
        o, n = orat.get(nm), nrat.get(nm)
        if o != n:
            def _fmt(v):
                return "空" if v is None else f"{v:g}%"
            alloc_lines.append(f"{nm} {_fmt(o)}→{_fmt(n)}")
    if alloc_lines:
        out.append(("分摊", _join_summary("分摊：", alloc_lines)))
    return out


def _diff_accounts(old_accs: list, new_accs: list) -> list:
    """账号增删改（含改权限/改密码/改显示名）→ [(账号,摘要)]。密码只记「改密码」不记值。"""
    om = {a["账号"]: a for a in old_accs}
    nm = {a["账号"]: a for a in new_accs}
    lines = [f"新增 {a}（{nm[a].get('权限')}）" for a in sorted(set(nm) - set(om))]
    lines += [f"删除 {a}" for a in sorted(set(om) - set(nm))]
    for a in sorted(set(om) & set(nm)):
        o, n = om[a], nm[a]
        chg = []
        if o.get("权限") != n.get("权限"):
            chg.append(f"权限 {o.get('权限')}→{n.get('权限')}")
        if str(o.get("密码")) != str(n.get("密码")):
            chg.append("改密码")
        if (o.get("显示名") or "") != (n.get("显示名") or ""):
            chg.append("改显示名")
        if chg:
            lines.append(f"{a} " + "、".join(chg))
    return [("账号", _join_summary("账号：", lines))] if lines else []


def _admin_page(dash_html: str, summary: dict) -> str:
    """管理员控制台：体检条 + 立即更新 + 明细编辑/手填/调整台账 标签页 + 内嵌驾驶舱。"""
    return _ADMIN_CONSOLE


def _run_reasons(report: dict) -> list[str]:
    """从最近一次管道运行日志（体检JSON=report）推导"为啥黄/红"。
    与 ingest._log_run 判定口径一致：fetch 走本地副本/无源、过期调整。
    注意：这是「管道运行」信号（黄/红），与「数据体检」的未填分类等（警）是两套，别糊在一起。"""
    report = report or {}
    reasons: list[str] = []
    fetch = report.get("fetch", {}) or {}
    st = fetch.get("status")
    if st == "no_source":
        reasons.append("收单台账无可用数据源（共享路径与本地副本都没有）→ 判红")
    elif st and st != "fetched":
        reasons.append(f"收单台账未从共享路径拉取、走本地副本（状态：{st}）")
    adj = report.get("adjust", {}) or {}
    if adj.get("expired", 0):
        reasons.append(f"{adj['expired']} 条调整「过期疑似」（源头已改、调整未套用）→ 去『异常处理·数据修正』看")
    if adj.get("missing", 0):
        reasons.append(f"{adj['missing']} 条调整定位键失配未套用（源头行删了/改了金额，剔除或改值没生效）→ 去『异常处理·数据修正』人工复核")
    return reasons


_LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理员登录 · 甲骨易智能经营罗盘</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#1e293b;padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px #0006}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:#94a3b8}}
input{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid #334155;background:#0f172a;color:#e2e8f0;font-size:14px}}
button{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:#f87171;font-size:13px;margin-bottom:10px}}
.hint{{color:#64748b;font-size:12px;margin-top:12px}}</style></head>
<body><form class="card" method="post" action="/admin/login">
<h1>管理员端登录</h1>{err}
<label>账号</label><input name="account" value="{account}" autocomplete="username" autofocus>
<label>密码</label><input type="password" name="password" autocomplete="current-password">
<button type="submit">进入</button>
<div class="hint">管理员账号见「看板账号」表（默认 lushasha）。</div></form></body></html>"""


def _login_page(err: str = "", account: str = "") -> str:
    err_html = f'<div class="err">{err}</div>' if err else ""
    acct = str(account or DEFAULT_ADMIN_ACCOUNT).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return _LOGIN_HTML.format(err=err_html, account=acct)


# 查看端登录页（v8.0）：账号+密码，按权限分流（管理员→/admin、整体→整体页、BU→本 BU 页）。
_VIEW_LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>看板登录 · 甲骨易智能经营罗盘</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#1e293b;padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px #0006}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:#94a3b8}}
input{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid #334155;background:#0f172a;color:#e2e8f0;font-size:14px}}
button{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:#f87171;font-size:13px;margin-bottom:10px}}
.hint{{color:#64748b;font-size:12px;margin-top:12px}}</style></head>
<body><form class="card" method="post" action="/login">
<h1>看板登录</h1>{err}
<label>账号</label><input name="account" value="{account}" autocomplete="username" autofocus>
<label>密码</label><input type="password" name="password" autocomplete="current-password">
<button type="submit">进入</button>
<div class="hint">账号密码问财务部管理员要；登录后可自己改密码。忘记密码找管理员重置。</div></form></body></html>"""


def _view_login_page(err: str = "", account: str = "") -> str:
    err_html = f'<div class="err">{err}</div>' if err else ""
    acct = str(account).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return _VIEW_LOGIN_HTML.format(err=err_html, account=acct)


_ADMIN_CONSOLE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理员控制台 · 甲骨易智能经营罗盘</title>
<style>
:root{--bg:#0b1220;--panel:#151e30;--panel2:#1a2438;--line:#2a364d;--fg:#e8eef9;--mut:#8b9bb4;--vio:#8b5cf6;--vio2:#a78bfa}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,"PingFang SC","Segoe UI",sans-serif;
background:radial-gradient(1200px 600px at 10% -10%,#1a1040 0%,transparent 55%),
radial-gradient(900px 500px at 100% 0%,#0c2a3a 0%,transparent 50%),var(--bg);color:var(--fg);min-height:100vh}
#bar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
padding:10px 16px;background:rgba(21,30,48,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
#bar b{font-size:15px;letter-spacing:.2px}.pill{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;user-select:none}
.g{background:#14532d;color:#86efac}.y{background:#713f12;color:#fde68a}.r{background:#7f1d1d;color:#fca5a5}
button{background:linear-gradient(180deg,#9b6dff,#7c3aed);color:#fff;border:0;border-radius:9px;padding:7px 14px;font-size:13px;cursor:pointer;
box-shadow:0 2px 10px #7c3aed44;font-weight:600}
button:hover{filter:brightness(1.06)}button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg);box-shadow:none}
button.mini{padding:5px 10px;font-size:12px;border-radius:8px}button:disabled{opacity:.5;cursor:wait;filter:none}
a{color:var(--vio2)}a.logout{color:var(--mut);text-decoration:none;font-size:13px;padding:6px 10px;border-radius:8px}
a.logout:hover{background:var(--panel2);color:var(--fg)}
#groups{display:flex;gap:4px;flex-wrap:wrap;padding:10px 16px 0;background:transparent}
.gtab{padding:9px 18px;border-radius:10px 10px 0 0;cursor:pointer;font-size:14px;font-weight:600;color:var(--mut);
border:1px solid transparent;border-bottom:none;transition:.15s}
.gtab:hover{color:var(--fg)}.gtab.on{background:var(--bg);color:var(--fg);border-color:var(--line);box-shadow:0 -2px 12px #0003}
#subnav{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:10px 16px;background:rgba(15,22,36,.65);border-bottom:1px solid var(--line);min-height:0}
.subgrp{display:none;gap:6px;align-items:center;flex-wrap:wrap}
.stab{background:transparent;border:1px solid var(--line);color:var(--mut);padding:6px 14px;border-radius:999px;font-size:13px;cursor:pointer;transition:.12s}
.stab:hover{color:var(--fg);border-color:#475569}.stab.on{background:var(--vio);color:#fff;border-color:var(--vio);box-shadow:0 2px 8px #8b5cf644}
.subsep{width:1px;height:18px;background:var(--line);margin:0 4px}
.subgrp .badge{background:#7f1d1d;color:#fca5a5;border-radius:20px;padding:0 6px;font-size:11px;margin-left:5px}
.subgrp .badge.zero{background:#14532d;color:#86efac}
/* 各页铺满视口宽度（原 max-width:1280 宽屏右侧大片空白） */
.sec{display:none;padding:18px 20px 28px;width:100%;max-width:none;box-sizing:border-box}.sec.on{display:block}
#dash.sec,#history.sec{padding:10px 12px 14px}
input,select{background:#0c1424;border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:8px 10px;font-size:13px}
input:focus,select:focus{outline:none;border-color:var(--vio);box-shadow:0 0 0 3px #8b5cf633}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:0}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;white-space:nowrap}
th{background:#0f172a;position:sticky;top:0;z-index:1;color:var(--mut);font-size:11.5px;font-weight:700;letter-spacing:.02em}
tr.exp{background:#3b1d1d}tr.init-pw td{background:#3b2f0e88 !important}
.wrap{overflow:auto;max-height:calc(100vh - 200px)}
.row-form{margin:6px 0;padding:10px 12px;background:var(--panel2);border-radius:10px;border:1px solid var(--line)}
.muted{color:var(--mut);font-size:12px}
iframe{width:100%;height:calc(100vh - 128px);min-height:520px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 8px 28px #0005;display:block}
.note{color:var(--mut);font-size:12.5px;margin:8px 0;line-height:1.55}
.note.info{border-left:3px solid var(--vio);padding:10px 14px;border-radius:0 10px 10px 0;background:var(--panel2);margin:0 0 12px}
#hDetail{display:none;position:absolute;top:52px;left:14px;z-index:30;max-width:560px;background:var(--panel);
border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:12px;line-height:1.6;box-shadow:0 12px 36px #0009}
#hDetail h4{margin:0 0 4px;font-size:13px}#hDetail .grp{margin-top:10px}
#hDetail .k{color:var(--mut);font-weight:600;margin-bottom:2px}
#hDetail ul{margin:3px 0 0;padding-left:18px}#hDetail .ok{color:#86efac}
#toast{display:none;position:fixed;top:56px;right:18px;z-index:50;background:#14532d;color:#bbf7d0;
padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600;box-shadow:0 8px 24px #0008;max-width:360px}
#toast.err{background:#7f1d1d;color:#fecaca}
.scard{background:linear-gradient(165deg,rgba(30,41,59,.95) 0%,rgba(15,23,42,.98) 100%);
border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 10px 28px #0004}
.scard-h{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line);
background:linear-gradient(180deg,#1e2a42,#172033)}
.scard-h .ico{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;flex-shrink:0;
background:linear-gradient(145deg,#8b5cf633,#6366f122);border:1px solid #8b5cf644;font-size:17px}
.scard-h .ttl{font-size:15px;font-weight:700;letter-spacing:.2px}
.scard-h .sub{font-size:12px;color:var(--mut);margin-top:3px;line-height:1.45}
.scard-b{padding:16px}.scard-f{padding:12px 16px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;align-items:center;
background:rgba(0,0,0,.12)}
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.field.row{flex-direction:row;align-items:center;gap:10px;flex-wrap:wrap}
.field label{font-size:12px;color:var(--mut);font-weight:600}
.field-inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
/* 两列：自动更新|备份、智云账号|账号与权限；full 卡独占一行 */
#settings .sgrid{display:grid;grid-template-columns:minmax(280px,1fr) minmax(420px,1.65fr);gap:16px;width:100%;max-width:none;align-items:stretch}
#settings .sgrid .full{grid-column:1/-1}
#settings .sgrid > .scard{min-width:0;display:flex;flex-direction:column}
#settings .sgrid > .scard .scard-b{flex:1 1 auto}
@media(max-width:960px){#settings .sgrid{grid-template-columns:1fr}}
.tbl-box{border:1px solid var(--line);border-radius:12px;overflow:auto;background:#0c1424}
.tbl-box.sm{max-height:42vh}.tbl-box.lg{max-height:calc(100vh - 240px)}
.tbl-box table{margin:0}.tbl-box th{border-bottom:1px solid var(--line)}
.tbl-box tr:hover td{background:#1a243866}
.tbl-box input,.tbl-box select{border-radius:7px;padding:6px 8px;font-size:12.5px}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 14px;margin-bottom:12px;
border-radius:12px;background:var(--panel);border:1px solid var(--line);box-shadow:0 4px 16px #0003}
.toolbar .grow{flex:1;min-width:8px}
.sec-block{margin-top:18px}
.sec-block .blk-h{font-size:14px;font-weight:700;margin:0 0 8px;display:flex;align-items:center;gap:8px}
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;width:100%;max-width:none}
.ovcard{border-radius:14px !important;transition:transform .15s,box-shadow .15s;box-shadow:0 6px 18px #0003}
.ovcard:hover{transform:translateY(-2px);box-shadow:0 12px 28px #0006}
#dash .note{margin-top:10px}
/* BU 销售拖拽归属 */
.bu-board{display:flex;flex-direction:column;gap:12px}
.bu-pool{border:1px dashed #475569;border-radius:12px;padding:10px 12px;background:#0c142488}
.bu-pool-h,.bu-col-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.bu-pool-h b,.bu-col-title{font-size:13px;font-weight:700}
.bu-pool-h .hint{font-size:11.5px;color:var(--mut)}
.bu-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.bu-col{border:1px solid var(--line);border-radius:12px;padding:10px;background:#0c1424;min-height:140px;
display:flex;flex-direction:column;gap:8px}
.bu-col.drag-over{border-color:var(--vio);box-shadow:0 0 0 2px #8b5cf644}
.bu-col-meta{display:flex;flex-direction:column;gap:6px}
.bu-col-meta input{width:100%}
.bu-chips{display:flex;flex-wrap:wrap;gap:6px;min-height:44px;padding:8px;border-radius:10px;
background:#111827;border:1px solid #1f2937;flex:1;align-content:flex-start}
.bu-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;
background:linear-gradient(180deg,#2a3650,#1e293b);border:1px solid #3d4f6f;color:var(--fg);
font-size:12px;font-weight:600;cursor:grab;user-select:none;max-width:100%}
.bu-chip:active{cursor:grabbing}.bu-chip.dragging{opacity:.45}
.bu-chip .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px}
.bu-chip .c{font-size:10.5px;color:var(--mut);font-weight:500}
.bu-chip .x{border:0;background:transparent;color:#94a3b8;cursor:pointer;padding:0 2px;font-size:14px;line-height:1;box-shadow:none}
.bu-chip .x:hover{color:#f87171}
.bu-empty{font-size:11.5px;color:#64748b;padding:4px 2px;width:100%}
.bu-chip .bu-cb{margin:0 2px 0 0;cursor:pointer;accent-color:var(--vio)}
.bu-batch{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:9px 12px;margin:0 0 12px;
  border-radius:10px;background:linear-gradient(180deg,#2a1f52,#1e2438);border:1px solid var(--vio);font-size:13px}
.bu-batch select{min-width:150px}
#buUnassignedHint b{color:#fbbf24}
.acct-bus{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px;max-width:280px}
.acct-bu{display:inline-flex;align-items:center;gap:3px;font-size:11.5px;color:var(--fg);cursor:pointer;white-space:nowrap}
.acct-bu input{margin:0;accent-color:var(--vio);cursor:pointer}
.sched-times{display:flex;flex-wrap:wrap;gap:8px}
.sched-row{display:inline-flex;align-items:center;gap:4px}
.sched-row input[type=time]{font-size:15px;padding:7px 10px}
.sched-row .mini{padding:4px 8px;font-size:12px}
.ver-pill{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700;cursor:pointer;user-select:none;
  background:linear-gradient(180deg,#312e6e,#211d44);color:#c7b8ff;border:1px solid #5b4bc4}
.ver-pill:hover{filter:brightness(1.12)}
/* 版本与更新日志卡 */
#verCard .ver-now{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}
#verCard .ver-now .num{font-size:26px;font-weight:800;letter-spacing:.5px;color:var(--vio2)}
#verCard .ver-now .stage{font-size:12.5px;font-weight:700;padding:2px 9px;border-radius:999px;
  background:#3b2f0e;color:#fde68a}
#verCard .ver-now .stage.live{background:#14532d;color:#86efac}
#verCard .ver-sub{font-size:12px;color:var(--mut);margin-bottom:12px;line-height:1.5}
#verLog{display:flex;flex-direction:column;gap:12px;max-height:min(46vh,420px);overflow:auto;padding-right:4px}
#verLog .vl{border:1px solid var(--line);border-radius:10px;padding:11px 13px;background:#0c1424}
#verLog .vl-h{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:7px}
#verLog .vl-h .t{font-size:13.5px;font-weight:700}
#verLog .vl-h .d{font-size:11.5px;color:var(--mut)}
#verLog ul{margin:0;padding-left:18px}#verLog li{font-size:12.5px;line-height:1.6;margin:3px 0;color:#cdd7ea}
.ver-update{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line)}
.vu-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
#vuAvail{margin-top:10px}
.vu-avail{border:1px solid #5b4bc4;border-radius:10px;padding:11px 13px;background:#1a1440}
.vu-h{font-size:13px;font-weight:700;margin-bottom:6px}
.vu-sub{font-size:12px;color:var(--mut)}
.vu-log{margin:4px 0 10px;padding-left:18px}.vu-log li{font-size:12px;color:#cdd7ea;margin:2px 0}
</style></head><body>
<div id="bar">
  <b>管理员控制台</b>
  <span id="verPill" class="ver-pill" title="产品版本号（点开看更新日志）" onclick="showGroup('cfg');setTimeout(()=>{var e=document.getElementById('verCard');if(e)e.scrollIntoView({behavior:'smooth',block:'center'});},60)">v…</span>
  <span id="health" class="pill y" onclick="toggleHealth()" title="点开看体检明细">体检…</span>
  <button id="btnRefresh" onclick="doRefresh()">立即更新</button>
  <span id="msg" class="muted"></span>
  <span style="margin-left:auto"></span>
  <a class="logout" href="/admin/logout">退出</a>
</div>
<div id="toast"></div>
<div id="hDetail"></div>
<div id="groups">
  <div class="gtab on" data-g="see" onclick="showGroup('see')">看</div>
  <div class="gtab" data-g="edit" onclick="showGroup('edit')">改数据</div>
  <div class="gtab" data-g="review" onclick="showGroup('review')">异常处理</div>
  <div class="gtab" data-g="cfg" onclick="showGroup('cfg')">设置</div>
</div>
<div id="subnav">
  <span class="subgrp" id="sub-edit" data-g="edit">
    <button class="stab on" data-t="收入明细" onclick="pickTable('收入明细')">收入明细</button>
    <button class="stab" data-t="下单" onclick="pickTable('下单')">下单</button>
    <button class="stab" data-t="回款" onclick="pickTable('回款')">回款</button>
    <button class="stab" data-t="内部译员" onclick="pickTable('内部译员')">内部译员</button>
    <button class="stab" data-t="费用明细" onclick="pickTable('费用明细')">费用明细</button>
    <span class="subsep"></span>
    <button class="stab" data-t="手填" onclick="showManual()">手填</button>
  </span>
  <span class="subgrp" id="sub-review" data-g="review">
    <button class="stab on" data-t="overview" onclick="showReview('overview')">总览</button>
    <button class="stab" data-t="ledger" onclick="showReview('ledger')">数据修正</button>
    <button class="stab" data-t="orderdept" onclick="showReview('orderdept')">下单未填部门<span id="odBadge" class="badge zero">0</span></button>
    <button class="stab" data-t="unclassified" onclick="showReview('unclassified')">费用未分类（台账）<span id="ucBadge" class="badge zero">0</span></button>
    <button class="stab" data-t="history" onclick="showReview('history')">历史快照</button>
    <button class="stab" data-t="audit" onclick="showReview('audit')">配置变更记录</button>
  </span>
</div>

<div id="dash" class="sec on"><iframe id="dashFrame" src="/"></iframe>
  <div class="note info">改数后此看板会自动刷新（秒级重算）。</div></div>

<div id="detail" class="sec">
  <div class="toolbar">
    <span>当前表：<b id="dTableName">收入明细</b></span>
    <span class="field-inline">月份 <select id="dY"></select><select id="dM"></select></span>
    <span class="field-inline">搜索 <input id="dQ" placeholder="订单号/客户…" size="14"></span>
    <button onclick="dQuery()">查询</button>
    <span id="dInfo" class="muted grow"></span>
  </div>
  <div class="note info">改数=写一条调整记录（重抓不丢）；剔除=软删（可在「数据修正」撤销）。滚动到底自动加载更多。</div>
  <div class="tbl-box lg wrap" id="dWrap"><table id="dTbl"></table></div>
</div>

<div id="manual" class="sec">
  <div class="toolbar">
    <span class="field-inline">月份 <select id="mY"></select><select id="mM"></select></span>
    <button onclick="mLoad()">查询</button>
    <span class="muted grow">改手填即留痕（manual_历史），当月覆盖。</span>
  </div>
  <div class="tbl-box sm wrap"><table id="mTbl"></table></div>
  <div class="sec-block">
    <div class="blk-h">📈 年度预算（全公司）</div>
    <div class="note info">下单/回款两个年度数，年初定、年中改留痕；填了老板端回款图即出预算线与完成率。</div>
    <div class="toolbar"><span class="field-inline">年份 <select id="bY"></select></span></div>
    <div class="tbl-box sm wrap"><table id="bTbl"></table></div>
  </div>
  <div class="sec-block">
    <div class="blk-h">🏷 部门费用年预算</div>
    <div class="note info">按收单台账「预算归属部门」逐部门填；填了老板端即出「部门费用预算执行」卡。改已有值需确认、全程留痕。</div>
    <div class="tbl-box sm wrap"><table id="bdTbl"></table></div>
  </div>
</div>

<div id="ledger" class="sec">
  <div class="toolbar">
    <button onclick="lLoad()">刷新台账</button>
    <label class="field-inline muted"><input type="checkbox" id="lExpOnly" onchange="lRender()"> 只看过期疑似</label>
    <button class="mini" id="lBatchBtn" onclick="lBatchAsk()">一键听源头新值（批量撤销过期疑似）</button>
    <span id="lInfo" class="muted grow"></span>
  </div>
  <div class="note info">过期疑似（红）= 源头已改、我的调整未套用，<b>页面现用源头新值</b>。处理：「坚持我的数」=重新生效；「撤销」=认可源头。批量只提供"听源头"方向。</div>
  <div id="lConfirm" class="note info" style="display:none;border-left-color:#f59e0b"></div>
  <div class="tbl-box lg wrap"><table id="lTbl"></table></div>
</div>

<div id="history" class="sec">
  <div class="toolbar">
    <span class="field-inline">看哪天 <select id="hisY"></select><select id="hisM"></select><select id="hisD" style="min-width:220px"></select></span>
    <span id="hisInfo" class="muted grow"></span>
  </div>
  <div class="note info">每天更新完自动存一份当天页面（同天多次=留最后一次）；月末那天随月末快照永久保留。</div>
  <iframe id="hisFrame" style="margin-top:4px"></iframe>
</div>

<div id="settings" class="sec">
  <div class="sgrid">

    <div class="scard full" id="verCard">
      <div class="scard-h"><span class="ico">🧭</span><div><div class="ttl">版本与更新日志</div>
        <div class="sub">当前产品版本 + 每版大白话改了啥。产品号（试运行 0.9，上线升 1.0）跟内部开发号是两套，给管理层看这个。</div></div></div>
      <div class="scard-b">
        <div class="ver-now"><span class="num" id="verNum">v…</span>
          <span class="stage" id="verStage">…</span>
          <span class="muted" style="font-size:12px" id="verNext"></span></div>
        <div class="ver-sub" id="verSub"></div>
        <div id="verLog"></div>
        <div class="ver-update">
          <div class="vu-row"><button class="mini" type="button" onclick="checkUpdate()">检查更新</button>
            <span id="vuMsg" class="muted"></span></div>
          <div class="muted" style="font-size:11.5px;margin-top:6px">从代码仓库检测有没有新版本；有则可「一键更新」（安全快进拉取 + 看门狗自动重启）。需部署机用 <b>看门狗启动.bat</b> 起服务才会自动重启。</div>
          <div id="vuAvail" style="display:none"></div>
        </div>
      </div>
    </div>

    <div class="scard">
      <div class="scard-h"><span class="ico">⏰</span><div><div class="ttl">自动更新</div>
        <div class="sub">每天自动跑完整更新（抓数→重算→出页面）；可设多个时间点，各到点各更新一次</div></div></div>
      <div class="scard-b">
        <div class="field"><label>每日更新时间点（可多个）</label>
          <div id="schedTimes" class="sched-times"></div>
          <button class="ghost mini" type="button" onclick="schedAdd()" style="margin-top:8px">＋ 添加时间点</button></div>
        <div class="muted">如 09:30 / 12:00 / 17:30，各到点各跑一次。Windows 每个时间点建一个计划任务；<b>首次或增删时间点若没生效，以管理员身份跑一次 注册每日更新.bat</b>。平时可点顶栏「立即更新」。</div>
      </div>
      <div class="scard-f">
        <button class="mini" type="button" onclick="saveSchedule()">保存自动更新</button>
        <span id="sTimeMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard">
      <div class="scard-h"><span class="ico">🗄</span><div><div class="ttl">备份清理</div>
        <div class="sub">每次更新备份 看板.db 到 数据/备份/（每天一份）</div></div></div>
      <div class="scard-b">
        <div class="field row"><label>备份保留</label>
          <input id="sKeep" type="number" min="1" max="365" style="width:88px;font-size:15px"><span class="muted">天</span></div>
        <div class="muted">超过天数自动删最旧；月末快照存档永久保留。</div>
        <div id="sBakInfo" class="muted" style="margin-top:8px"></div>
      </div>
      <div class="scard-f">
        <button class="mini" type="button" onclick="saveBackup()">保存备份设置</button>
        <span id="sBakMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard">
      <div class="scard-h"><span class="ico">🔑</span><div><div class="ttl">智云账号</div>
        <div class="sub">在线抓数用；换号只改这两项，下次「立即更新」生效</div></div></div>
      <div class="scard-b">
        <div class="field"><label>账号</label>
          <input id="sZyUser" type="password" autocomplete="off" style="width:100%;max-width:280px"></div>
        <div class="field"><label>密码</label>
          <div class="field-inline">
            <input id="sZyPwd" type="password" autocomplete="off" style="width:100%;max-width:280px">
            <button class="ghost mini" type="button" onclick="toggleZyReveal()" id="sZyEye">👁 显示</button>
          </div></div>
      </div>
      <div class="scard-f">
        <button class="mini" type="button" onclick="saveZhiyun()">保存智云账号</button>
        <span id="sZyMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard">
      <div class="scard-h"><span class="ico">👥</span><div><div class="ttl">账号与权限</div>
        <div class="sub"><b>显示名</b>=备注（谁用这个号，只给人看）。<b>权限</b>：管理员 / 整体（看全公司+全部 BU）/ 按 BU（勾选一组 BU，只看这几块，可多选）。密码明文仅此处可见（点👁）。黄底=初始密码。<b>总账号</b>（lushasha）固定管理员、不可删；另可再加其他管理员。</div></div></div>
      <div class="scard-b">
        <div class="tbl-box sm wrap" style="max-height:min(42vh,360px)"><table id="acctTbl"></table></div>
      </div>
      <div class="scard-f">
        <button class="ghost mini" type="button" onclick="acctAdd()">＋ 加账号</button>
        <button class="mini" type="button" onclick="acctSave()">保存账号</button>
        <span id="acctMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard full">
      <div class="scard-h"><span class="ico">🏢</span><div><div class="ttl">BU 数据归属（销售归属）</div>
        <div class="sub">销售归到哪个 BU=该人口径进那张 BU 利润表（一人一 BU）。<b>勾选多人→选 BU→批量指定</b>，或直接拖动；改完点「保存数据归属」即重算。与登录账号无关。未归属不进任何 BU 子页。没配 BU=分页关闭。</div></div></div>
      <div class="scard-b">
        <div id="buUnassignedHint" class="note" style="display:none;border-left:3px solid #f59e0b;padding:8px 12px;border-radius:0 8px 8px 0;background:var(--panel2);margin:0 0 12px"></div>
        <div class="bu-batch" id="buBatch" style="display:none">
          <span>已勾选 <b id="buPickN">0</b> 人 →</span>
          <select id="buPickTo"></select>
          <button class="mini" type="button" onclick="buApplyBatch()">批量指定</button>
          <button class="ghost mini" type="button" onclick="buClearPick()">清除勾选</button>
        </div>
        <div class="bu-board" id="buBoard">
          <div class="bu-pool">
            <div class="bu-pool-h"><b>未归属销售</b><span class="hint" id="buPoolHint">从库四源汇总 · 勾选批量或拖到下方 BU</span></div>
            <div class="bu-chips" id="buPool" data-zone="pool"></div>
          </div>
          <div class="bu-cols" id="buCols"></div>
        </div>
        <table id="buTbl" style="display:none"></table>
        <div style="margin:14px 0 4px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <button class="ghost mini" type="button" onclick="buAdd()">＋ 加一个 BU</button>
          <span class="muted" style="font-size:12px">先加 BU、拖销售；分摊比例在下方（全空=不分摊）</span>
        </div>
        <div id="buAllocBox" style="margin-top:12px;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--panel2)">
          <div style="font-weight:600;margin-bottom:6px">公共费用分摊</div>
          <div class="muted" style="font-size:12px;margin-bottom:10px">各 BU 填比例 %（0~100）。<b>全部留空 = 暂不分摊</b>（BU 页公共费用不显示金额）；一旦填写则每个 BU 都要填且合计须为 100%。只摊台账 5 类，手填人力不摊，公式在系统里。</div>
          <div id="buAllocRows"></div>
          <div id="buAllocSum" class="muted" style="font-size:12px;margin-top:6px"></div>
        </div>
      </div>
      <div class="scard-f">
        <button class="mini" type="button" onclick="buSave()">保存数据归属</button>
        <span id="buMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard full">
      <div class="scard-h"><span class="ico">🔌</span><div><div class="ttl">数据从哪来</div>
        <div class="sub">固定两路抓数：智云四表 + 共享盘台账；抓不到沿用本地文件 + 体检黄</div></div></div>
      <div class="scard-b">
        <div class="tbl-box sm wrap"><table id="sSrcTbl"></table></div>
      </div>
    </div>

  </div>
</div>

<div id="unclassified" class="sec">
  <div class="toolbar">
    <button onclick="ucLoad()">刷新清单</button>
    <span id="ucInfo" class="muted grow"></span>
  </div>
  <div class="note info">收单（费用）台账明细还没填「对应报表大类」→ 暂未计入费用（利润会略偏高）。请在源头补填，下次更新自动计入。</div>
  <div class="tbl-box lg wrap" id="ucWrap"><table id="ucTbl"></table></div>
</div>

<div id="overview" class="sec">
  <div class="note info">分诊台：0=绿=不用管；有数=点卡片进对应清单。处理动作与「改数据」同一套调整机制。</div>
  <div id="ovCards" class="ov-grid"></div>
  <div class="note info" style="margin-top:14px">闭环：在「下单未填部门」归类后，若销售在智云补了部门，会变「过期疑似」——去「数据修正」选听源头或坚持我的数。</div>
</div>

<div id="audit" class="sec">
  <div class="toolbar">
    <button onclick="auLoad()">刷新</button>
    <span class="field-inline">类别 <select id="auCat" onchange="auLoad()"><option value="">全部</option></select></span>
    <span id="auInfo" class="muted grow"></span>
  </div>
  <div class="note info">谁在什么时候改了哪项配置（销售归属 / BU / 分摊 / 账号 / 设置 / 密码）都在这里，倒序、最近 200 条。只记变更摘要，<b>不含密码明文</b>。</div>
  <div class="tbl-box lg wrap"><table id="auTbl"></table></div>
</div>

<div id="orderdept" class="sec">
  <div class="toolbar">
    <button onclick="odLoad()">刷新清单</button>
    <span id="odInfo" class="muted grow"></span>
  </div>
  <div class="note info">智云下单源头没填「部门」→ 排名灰显「（未填）」。此处选部门保存=写调整；也可让销售在智云补填。</div>
  <div class="tbl-box lg wrap" id="odWrap"><table id="odTbl"></table></div>
</div>

<script>
let ADJ_FIELDS={};  // R1：可调字段由服务端下发（schema 黑名单制推导），不再前端写死
async function loadAdjFields(){try{ADJ_FIELDS=await jget("/api/adjust_fields");}catch(e){}}
const STD={"收入明细":"std_收入明细","下单":"std_下单","回款":"std_回款","内部译员":"std_内部译员","费用明细":"std_费用明细"};
const MANUAL_ITEMS=["营销人力成本","管理人力成本","研发人力成本","财务费用补充","PM人力成本","VM人力成本",
"实际内部译员成本","税费损失","技术流量成本","其他（生产成本）","其他损益"];
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function msg(t){document.getElementById("msg").textContent=t||"";}
async function api(path,opts){const r=await fetch(path,Object.assign({credentials:"same-origin"},opts||{}));
  if(r.status===401){location.href="/admin";throw new Error("401");}return r;}
async function jget(p){const r=await api(p);return r.json();}
async function jpost(p,body){const r=await api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));return d;}
function showSec(id){document.querySelectorAll(".sec").forEach(e=>e.classList.toggle("on",e.id===id));}
// 顶层四区：看 / 改数据 / 异常处理 / 设置
function showGroup(g){document.querySelectorAll(".gtab").forEach(e=>e.classList.toggle("on",e.dataset.g===g));
  document.querySelectorAll(".subgrp").forEach(e=>e.style.display=e.dataset.g===g?"flex":"none");
  if(g==="see")showSec("dash");
  else if(g==="edit")pickTable(curTable);
  else if(g==="review")showReview("overview");
  else if(g==="cfg"){showSec("settings");loadVersion();loadSettings();loadBuCfg();loadAccts();}}
function reloadDash(){try{document.getElementById("dashFrame").contentWindow.location.reload();}catch(e){}}
function showToast(t,isErr){const el=document.getElementById("toast");el.textContent=t||"";
  el.className=isErr?"err":"";el.style.display="block";
  clearTimeout(window._toastT);window._toastT=setTimeout(()=>{el.style.display="none";},4000);}
function _shortReason(h){const rr=(h.run_reasons||[])[0]||"";
  if(rr)return rr.length>36?rr.slice(0,36)+"…":rr;
  const w=(h.warnings||[])[0]||"";return w?(w.length>36?w.slice(0,36)+"…":w):"";}
async function loadHealth(){try{const h=await jget("/api/health");window._health=h;const el=document.getElementById("health");
  const c=h.result==="绿"?"g":h.result==="红"?"r":"y";el.className="pill "+c;
  const nWarn=(h.warnings&&h.warnings.length)||0;
  let label="体检 "+(h.result||"?");
  if(h.result&&h.result!=="绿"){const s=_shortReason(h);if(s)label+=" · "+s;}
  else if(nWarn)label+=" · "+nWarn+"警";
  el.textContent=label+" ▾";
  if(document.getElementById("hDetail").style.display==="block")renderHealth(h);}catch(e){}}
function toggleHealth(){const d=document.getElementById("hDetail");
  if(d.style.display==="block"){d.style.display="none";return;}renderHealth(window._health||{});d.style.display="block";}
function renderHealth(h){h=h||{};const reasons=h.run_reasons||[],warns=h.warnings||[];
  let html="<h4>体检明细 · 运行 "+esc(h.run_time||"?")+"</h4>";
  html+="<div class='grp'><div class='k'>① 管道运行："+esc(h.result||"?")+"</div>";
  html+=reasons.length?("<ul>"+reasons.map(r=>"<li>"+esc(r)+"</li>").join("")+"</ul>")
    :"<div class='ok'>✓ 运行正常（fetch/调整无异常）</div>";
  html+="</div><div class='grp'><div class='k'>② 数据体检："+(warns.length?(warns.length+" 警"):"无")+"</div>";
  html+=warns.length?("<ul>"+warns.map(w=>"<li>"+esc(w)+"</li>").join("")+"</ul>")
    :"<div class='ok'>✓ 无数据质量告警</div>";
  html+="</div><div class='grp'><div class='k'>数据源覆盖</div><div>"+
    (h.sources||[]).map(s=>esc(s.name)+"："+s.rows+"行").join("　")+"</div></div>";
  document.getElementById("hDetail").innerHTML=html;}
// 立即更新：后台跑+轮询进度；完成后 toast
let refT0=0;
async function doRefresh(){const b=document.getElementById("btnRefresh");b.disabled=true;refT0=Date.now();
  try{await jpost("/api/refresh",{});}catch(e){/* 409=已在更新 → 直接跟着轮询 */}
  msg("更新中…");pollRefresh();}
async function pollRefresh(){const b=document.getElementById("btnRefresh");
  try{const s=await jget("/api/refresh_status");
    if(s.running){const el=Math.round((Date.now()-refT0)/1000);
      msg("更新中… "+el+"s"+(s.zhiyun_auto_fetch?"（含智云在线抓数，约1~2分钟）":""));
      setTimeout(pollRefresh,2000);return;}
    b.disabled=false;const L=s.last;
    if(L&&L.status==="error"){msg("更新失败："+L.detail);showToast("更新失败："+(L.detail||""),true);}
    else{const t="已更新"+(L&&L.seconds?("（"+L.seconds+"s）"):"");msg(t);showToast("✓ "+t);}
    reloadDash();loadHealth();refreshUcBadge();
  }catch(e){b.disabled=false;msg("查询更新状态失败:"+e.message);}}
// 设置页
const SRC_MAP=[["下单(智云)","智云在线抓（自动登录，每次更新）"],
  ["回款(智云)","智云在线抓（自动登录，每次更新）"],
  ["项目明细(智云)","智云在线抓（自动登录，每次更新）"],
  ["内部译员·IN-HOUSE(智云)","智云在线抓（当前账号权限不足时自动沿用现有文件·体检黄，待专用账号）"],
  ["收单台账","共享盘自动拉取（部署机内网；不可达沿用本地副本·体检黄）"],
  ["手填与调整","管理员端「改数据→手填」填写，全程留痕"]];
function toggleZyReveal(){const u=document.getElementById("sZyUser"),p=document.getElementById("sZyPwd"),
  e=document.getElementById("sZyEye"),show=u.type==="password";
  u.type=p.type=show?"text":"password";e.textContent=show?"🙈 隐藏":"👁 显示";}
async function loadSettings(){try{const s=await jget("/api/settings");
  schedTimes=(s.schedule_times&&s.schedule_times.length)?s.schedule_times.slice():[s.schedule_time||"09:30"];
  renderSchedTimes();
  document.getElementById("sKeep").value=s.backup_keep_days||30;
  document.getElementById("sZyUser").value=s.zhiyun_username||"";
  document.getElementById("sZyPwd").value=s.zhiyun_password||"";
  const b=s.backup_stats||{};
  document.getElementById("sBakInfo").textContent="当前备份："+(b.count||0)+" 份，共 "+(b.mb||0)+" MB";
  const rows={};(window._health&&window._health.sources||[]).forEach(x=>rows[x.name]=x.rows);
  document.getElementById("sSrcTbl").innerHTML="<tr><th>数据</th><th>从哪来</th><th>当前行数</th></tr>"+
    SRC_MAP.map(([n,src])=>"<tr><td>"+esc(n)+"</td><td>"+esc(src)+"</td><td>"+
      (rows[n]!=null?rows[n]:"—")+"</td></tr>").join("");
  }catch(e){msg("读取设置失败:"+e.message);}}
// 版本与更新日志（产品号，与内部开发号分开）
async function loadVersion(){try{const v=await jget("/api/version");
  const num="v"+(v.version||"?"),stage=v.stage||"";
  const pill=document.getElementById("verPill");if(pill)pill.textContent=num+(stage?" · "+stage:"");
  const nEl=document.getElementById("verNum");if(nEl)nEl.textContent=num;
  const sEl=document.getElementById("verStage");if(sEl){sEl.textContent=stage;sEl.className="stage"+(stage==="正式版"?" live":"");}
  const nx=document.getElementById("verNext");if(nx)nx.textContent=stage==="试运行"?"· 正式上线后升 v1.0":"";
  const sub=document.getElementById("verSub");if(sub)sub.textContent="下面按时间倒序（最新在最上面），只讲这版能多干啥；内部开发号另计、不在此显示。";
  const log=document.getElementById("verLog");if(log){const cl=v.changelog||[];
    log.innerHTML=cl.length?cl.map(e=>"<div class='vl'><div class='vl-h'><span class='t'>"+esc(e.title||"")+
      "</span><span class='d'>"+esc(e.date||"")+"</span></div><ul>"+
      (e.items||[]).map(it=>"<li>"+esc(it)+"</li>").join("")+"</ul></div>").join("")
      :"<div class='muted'>暂无更新日志</div>";}
  }catch(e){const pill=document.getElementById("verPill");if(pill)pill.textContent="版本?";}}
// ④一键更新：检查远端有没有新版本 → 一键快进拉取 + 看门狗重启
async function checkUpdate(){const m=document.getElementById("vuMsg"),box=document.getElementById("vuAvail");
  m.textContent="检查中…（联网比对远端）";box.style.display="none";box.innerHTML="";
  try{const d=await jget("/api/update/check");
    if(!d.supported){m.textContent=d.reason||"一键更新不可用";return;}
    if(!d.available){m.textContent="✓ "+(d.reason||"已是最新版本")+(d.local?("（当前 "+esc(d.local)+"）"):"");return;}
    m.textContent="";
    const logs=(d.log||[]).map(s=>"<li>"+esc(s)+"</li>").join("");
    let html="<div class='vu-avail'><div class='vu-h'>🔔 发现新版本 · 落后 "+(d.behind||0)+" 个提交（"+esc(d.local||"")+" → "+esc(d.remote||"")+"）</div>";
    if(logs)html+="<div class='vu-sub'>更新内容（远端提交）：</div><ul class='vu-log'>"+logs+"</ul>";
    if(d.can_update)html+="<button class='mini' type='button' onclick='applyUpdate()'>一键更新并重启</button>"
      +"<span class='muted' style='margin-left:8px'>拉取新代码后服务自动重启（约 10 秒，页面自动刷新）</span>";
    else html+="<div class='muted' style='color:#fbbf24'>⚠ "+esc(d.reason||"当前不满足自动更新条件，请人工处理")+"</div>";
    html+="</div>";box.innerHTML=html;box.style.display="block";
  }catch(e){m.textContent="检查失败："+e.message;}}
async function applyUpdate(){if(!confirm("确认一键更新？将拉取新代码并重启服务（约 10 秒内不可用）。"))return;
  const box=document.getElementById("vuAvail");
  box.innerHTML="<div class='vu-avail'><div class='vu-h'>更新中…拉取新代码…</div></div>";
  try{const d=await jpost("/api/update/apply",{});
    if(d.ok){box.innerHTML="<div class='vu-avail'><div class='vu-h'>✓ 已拉取 "+esc(d.from||"")+" → "+esc(d.to||"")
      +"，服务重启中…</div><div class='muted'>约 10 秒后自动刷新页面；若没刷新请手动刷新。</div></div>";
      setTimeout(()=>location.reload(),12000);}
    else box.innerHTML="<div class='vu-avail'><div class='muted' style='color:#fbbf24'>未更新："+esc(d.reason||"")+"</div></div>";
  }catch(e){ // 更新成功后服务重启会切断连接→请求可能抛错，按"正在重启"处理
    box.innerHTML="<div class='vu-avail'><div class='vu-h'>更新请求已发出，服务可能正在重启…</div>"
      +"<div class='muted'>约 10 秒后自动刷新页面。</div></div>";
    setTimeout(()=>location.reload(),12000);}}
// ②多次更新时间：可增删多个时间点，各到点各跑一次
let schedTimes=["09:30"];
function renderSchedTimes(){const box=document.getElementById("schedTimes");if(!box)return;
  if(!schedTimes.length)schedTimes=["09:30"];
  box.innerHTML=schedTimes.map((t,i)=>
    "<span class='sched-row'><input type='time' value='"+esc(t)+"' onchange='schedTimes["+i+"]=this.value'>"
    +(schedTimes.length>1?"<button class='ghost mini' type='button' title='删除此时间点' onclick='schedDel("+i+")'>✕</button>":"")
    +"</span>").join("");}
function schedAdd(){const m=document.getElementById("sTimeMsg");
  if(schedTimes.length>=6){m.textContent="最多 6 个时间点";return;}
  m.textContent="";schedTimes.push("12:00");renderSchedTimes();}
function schedDel(i){if(schedTimes.length<=1)return;schedTimes.splice(i,1);renderSchedTimes();}
// 各卡就近保存（无底部全局保存）
async function saveSchedule(){const m=document.getElementById("sTimeMsg");m.textContent="保存中…";
  const times=schedTimes.map(t=>String(t||"").trim()).filter(Boolean);
  if(!times.length){m.textContent="至少保留一个时间点";return;}
  try{const d=await jpost("/api/settings",{schedule_times:times});
    if(d.schedule_times&&d.schedule_times.length){schedTimes=d.schedule_times.slice();renderSchedTimes();}
    m.textContent=d.note||"已保存";}catch(e){m.textContent="失败："+e.message;}}
async function saveBackup(){const m=document.getElementById("sBakMsg");m.textContent="保存中…";
  try{const d=await jpost("/api/settings",{backup_keep_days:document.getElementById("sKeep").value});
    m.textContent=d.note||"已保存";}catch(e){m.textContent="失败："+e.message;}}
async function saveZhiyun(){const m=document.getElementById("sZyMsg");m.textContent="保存中…";
  try{const d=await jpost("/api/settings",{zhiyun_username:document.getElementById("sZyUser").value,
    zhiyun_password:document.getElementById("sZyPwd").value});
    m.textContent=d.note||"已保存";}catch(e){m.textContent="失败："+e.message;}}
// 账号与权限卡
let acctList=[],acctPwShow={};
// 权限类型：管理员 / 整体 / BU（可绑多个）。旧账号权限=单个 BU 名 → 视作 BU 类型、可见BU=[该名]
function _permType(a){const p=a.权限||"";if(p==="管理员")return"管理员";if(p==="整体")return"整体";return"BU";}
function _permCellHtml(i,a){
  const ty=_permType(a);
  const sel='<select onchange="acctSetType('+i+',this.value)">'
    +[["管理员","管理员"],["整体","整体（看全部）"],["BU","按 BU（可多选）"]].map(o=>
      "<option value='"+o[0]+"'"+(o[0]===ty?" selected":"")+">"+esc(o[1])+"</option>").join("")
    +'</select>';
  if(ty!=="BU")return sel;
  const names=buList.map(b=>b.name).filter(Boolean);
  const chosen=new Set(a.可见BU||[]);
  const boxes=names.length?names.map(bn=>
    "<label class='acct-bu'><input type='checkbox'"+(chosen.has(bn)?" checked":"")
    +" data-bn=\""+esc(bn)+"\" onchange=\"acctToggleBu("+i+",this.getAttribute('data-bn'),this.checked)\">"
    +esc(bn)+"</label>").join("")
    :"<span class='muted' style='font-size:11px'>先在下方「BU 数据归属」建 BU</span>";
  const warn=(names.length&&chosen.size===0)?"<span class='muted' style='color:#fbbf24;font-size:11px'>未选=看不到任何页</span>":"";
  return sel+"<div class='acct-bus'>"+boxes+warn+"</div>";}
function acctSetType(i,t){const a=acctList[i];
  if(t==="BU"){a.权限="BU";if(!Array.isArray(a.可见BU))a.可见BU=[];}
  else{a.权限=t;a.可见BU=[];}
  acctRender();}
function acctToggleBu(i,bn,on){const a=acctList[i];a.权限="BU";  // 编辑 BU 集即固化为 BU 类型（旧名迁移）
  const s=new Set(a.可见BU||[]);if(on)s.add(bn);else s.delete(bn);a.可见BU=Array.from(s);}
let ACCT_MASTER="lushasha";  // 服务端 /api/accounts 会回 master_account 覆盖
function _adminCount(){return acctList.filter(a=>(a.权限||"")==="管理员").length;}
/** 总账号：按登录名锁定（与当前权限无关），永久不可删、登录名不可改 */
function _isMaster(a){return String(a.账号||"").trim()===ACCT_MASTER;}
function acctRender(){const t=document.getElementById("acctTbl");
  if(!acctList.length){t.innerHTML="<tr><td class='muted'>暂无账号——点「＋ 加账号」</td></tr>";return;}
  t.innerHTML="<tr><th>账号</th><th>显示名（备注）</th><th>权限</th><th>密码</th><th>最后登录</th><th></th></tr>"+
    acctList.map((a,i)=>{
      const init=!!a.初始密码,show=!!acctPwShow[i],master=_isMaster(a);
      const pw=a.密码==null?"":String(a.密码);
      if(master)a.权限="管理员";
      const delCell=master
        ?"<span class='muted' title='总账号永久不可删除' style='font-size:11px'>总账号</span>"
        :"<button class='ghost mini' type='button' onclick='acctDel("+i+")'>删</button>";
      const acctInput=master
        ?'<input style="width:110px;opacity:.9" value="'+esc(a.账号)+'" readonly title="总账号登录名固定，不可改">'
        :'<input style="width:110px" value="'+esc(a.账号)+'" onchange="acctList['+i+'].账号=this.value">';
      const permCell=master
        ?'<span class="muted" style="display:inline-block;padding:6px 10px;border:1px solid var(--line);border-radius:8px;font-size:12px" title="总账号固定为管理员">管理员</span>'
        :_permCellHtml(i,a);
      return "<tr class='"+(init?"init-pw":"")+"'>"+
        "<td>"+acctInput+"</td>"+
        "<td><input style='width:90px' title='备注：谁用这个号，不影响权限' value=\""+esc(a.显示名||"")+"\" onchange='acctList["+i+"].显示名=this.value'></td>"+
        "<td>"+permCell+"</td>"+
        "<td><input type='"+(show?"text":"password")+"' autocomplete='off' style='width:110px' value=\""+esc(pw)+"\" onchange='acctList["+i+"].密码=this.value;acctList["+i+"].初始密码=false'>"+
        " <button class='ghost mini' type='button' onclick='acctTogglePw("+i+")'>"+(show?"🙈":"👁")+"</button>"+
        (init?" <span title='仍是初始密码' style='color:#fde68a'>⚠初始</span>":"")+"</td>"+
        "<td class='muted'>"+esc(a.最后登录||"—")+"</td>"+
        "<td>"+delCell+"</td></tr>";}).join("");}
function acctTogglePw(i){acctPwShow[i]=!acctPwShow[i];acctRender();}
function acctAdd(){acctList.push({账号:"",显示名:"",权限:"整体",密码:"8888",初始密码:true,最后登录:""});acctRender();}
function acctDel(i){
  const a=acctList[i];
  if(_isMaster(a)){alert("总账号「"+ACCT_MASTER+"」永久不可删除（即使改成别的权限也不行）。部署机也靠它进管理端。");return;}
  if((a.权限||"")==="管理员"&&_adminCount()<=1){alert("至少保留一个「管理员」权限账号，否则没人能登录管理端");return;}
  if(!confirm("删除该账号？立即失效"))return;
  acctList.splice(i,1);acctRender();}
async function loadAccts(){try{const d=await jget("/api/accounts");acctList=d.accounts||[];
  if(d.master_account)ACCT_MASTER=d.master_account;acctPwShow={};acctRender();}
  catch(e){document.getElementById("acctMsg").textContent="读取失败:"+e.message;}}
async function acctSave(){const m=document.getElementById("acctMsg");m.textContent="保存中…";
  if(!_adminCount()){m.textContent="保存失败：至少保留一个「管理员」权限账号";return;}
  if(!acctList.some(a=>String(a.账号||"").trim()===ACCT_MASTER)){
    m.textContent="保存失败：总账号「"+ACCT_MASTER+"」不可删除";return;}
  try{const d=await jpost("/api/accounts",{accounts:acctList});acctList=d.accounts||[];
    if(d.master_account)ACCT_MASTER=d.master_account;acctPwShow={};acctRender();
    m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个）";}catch(e){m.textContent="保存失败："+e.message;}}
// BU 数据归属（销售归属·A1）+ 公共费用分摊（迭代17·A2：全空=不分摊，无总开关）
let buList=[], salesPool=[], buPicked=new Set(), buUnassigned={};
function _salesArr(v){if(Array.isArray(v))return v.map(s=>String(s).trim()).filter(Boolean);
  return String(v||"").split(/[、，,;；\n]/).map(s=>s.trim()).filter(Boolean);}
function _claimedSales(){const s=new Set();buList.forEach(b=>_salesArr(b.销售).forEach(x=>s.add(x)));return s;}
function _chipHtml(name,withX){const p=salesPool.find(p=>p.name===name)||{};
  const ref=p.ref_disp?('<span class="c" title="当年下单参考">'+esc(p.ref_disp)+'</span>'):'';
  const x=withX?'<button type="button" class="x" title="移回未归属" data-unassign="1">×</button>':'';
  const ck=buPicked.has(name)?' checked':'';
  return '<span class="bu-chip" draggable="true" data-name="'+esc(name)+'">'
    +'<input type="checkbox" class="bu-cb"'+ck+' data-name="'+esc(name)+'" onchange="buPick(this)" title="勾选后可批量指定 BU">'
    +'<span class="n" title="'+esc(name)+'">'+esc(name)+'</span>'+ref+x+'</span>';}
/** 分摊是否启用：任一比例非空即视为要分摊（保存时全填+合计100%）；全空=不分摊 */
function buAllocEnabledFromList(){
  return buList.some(b=>b.分摊比例!=null&&b.分摊比例!==""&&!isNaN(Number(b.分摊比例)));}
function buRenderAlloc(){const rows=document.getElementById("buAllocRows");
  if(!rows)return;
  rows.innerHTML=buList.map((b,i)=>{
    const v=b.分摊比例==null||b.分摊比例===""?"":b.分摊比例;
    return '<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
      +'<span style="min-width:100px">'+esc(b.name||("BU"+(i+1)))+'</span>'
      +'<input type="number" min="0" max="100" step="0.01" style="width:90px" value="'+esc(v)+'" '
      +'placeholder="空" '
      +'onchange="buList['+i+'].分摊比例=this.value===\'\'?null:Number(this.value);buRenderAllocSum()" '
      +'oninput="buList['+i+'].分摊比例=this.value===\'\'?null:Number(this.value);buRenderAllocSum()">'
      +'<span class="muted">%</span></div>';}).join("")
    ||'<div class="muted">请先点上方「＋ 加一个 BU」</div>';
  buRenderAllocSum();}
function buRenderAllocSum(){const sum=document.getElementById("buAllocSum");if(!sum)return;
  if(!buList.length){sum.textContent="";return;}
  let filled=0,t=0,bad=false;
  buList.forEach(b=>{const r=b.分摊比例;
    if(r==null||r==="")return;
    filled++;
    if(isNaN(Number(r))||Number(r)<0||Number(r)>100)bad=true;
    else t+=Number(r);});
  if(filled===0){sum.textContent="全部留空 → 暂不分摊（保存后 BU 页公共费用不摊）";sum.style.color="#94a3b8";return;}
  if(filled<buList.length||bad){sum.textContent="已填 "+filled+"/"+buList.length+" —— 要分摊请每个 BU 都填，或全部清空=不分摊";sum.style.color="#fbbf24";return;}
  const diff=Math.abs(t-100);
  sum.textContent="合计 "+t.toFixed(2)+"% "+(diff<=0.05?"✓ 可保存（启用分摊）":"← 须为 100% 才能保存");
  sum.style.color=diff<=0.05?"#86efac":"#fbbf24";}
// 批量多选归属（勾选若干人→选目标 BU→应用）
function buPick(cb){const n=cb.getAttribute("data-name");if(cb.checked)buPicked.add(n);else buPicked.delete(n);buRenderBatch();}
function buClearPick(){buPicked.clear();buRender();}
function buRenderBatch(){const bar=document.getElementById("buBatch");if(!bar)return;
  const n=buPicked.size;bar.style.display=n?"flex":"none";
  const c=document.getElementById("buPickN");if(c)c.textContent=n;
  const sel=document.getElementById("buPickTo");if(sel){const cur=sel.value;
    sel.innerHTML='<option value="__pool__">保持未归属</option>'+
      buList.map((b,i)=>'<option value="'+i+'">'+esc(b.name||("BU"+(i+1)))+'</option>').join("");
    if(cur&&Array.from(sel.options).some(o=>o.value===cur))sel.value=cur;}}
function buApplyBatch(){const sel=document.getElementById("buPickTo");if(!sel)return;
  const to=sel.value,names=Array.from(buPicked);if(!names.length)return;
  names.forEach(n=>{buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==n);});   // 先从各 BU 摘掉（一人一 BU）
    if(to!=="__pool__"){const i=+to;if(i>=0&&i<buList.length){const cur=_salesArr(buList[i].销售);
      if(cur.indexOf(n)<0)cur.push(n);buList[i].销售=cur;}}});
  buPicked.clear();buRender();
  const tgt=(to==="__pool__")?"未归属":(buList[+to]&&buList[+to].name)||("BU"+(+to+1));
  document.getElementById("buMsg").textContent="已把 "+names.length+" 人批量指定到「"+tgt+"」——点「保存数据归属」生效并重算";}
function buUpdateUnassignedHint(){const el=document.getElementById("buUnassignedHint");if(!el)return;
  const n=(buUnassigned&&buUnassigned.unassigned_count)||0;
  if(!n){el.style.display="none";return;}el.style.display="";
  el.innerHTML="⚠ 未归属销售 <b>"+n+"</b> 人，当年下单合计 <b>"+esc(buUnassigned.unassigned_orders_disp||"")+
    "</b> —— 这部分业务不进任何 BU 页（各 BU 合计小于全公司）。归属后点保存即计入。<span class='muted'>（金额=上次保存后快照，保存后刷新）</span>";}
function _bindDrag(root){if(!root)return;
  root.querySelectorAll(".bu-chip").forEach(ch=>{
    ch.addEventListener("dragstart",e=>{
      if(e.target&&e.target.getAttribute&&e.target.getAttribute("data-unassign")){e.preventDefault();return;}
      e.dataTransfer.setData("text/plain",ch.getAttribute("data-name")||"");
      e.dataTransfer.effectAllowed="move";ch.classList.add("dragging");});
    ch.addEventListener("dragend",()=>ch.classList.remove("dragging"));
    const xb=ch.querySelector("[data-unassign]");
    if(xb)xb.addEventListener("click",e=>{e.preventDefault();e.stopPropagation();
      buMoveToPool(ch.getAttribute("data-name")||"");});});
  root.querySelectorAll("[data-zone]").forEach(z=>{
    z.addEventListener("dragover",e=>{e.preventDefault();e.dataTransfer.dropEffect="move";
      z.classList.add("drag-over");const col=z.closest(".bu-col");if(col)col.classList.add("drag-over");});
    z.addEventListener("dragleave",()=>{z.classList.remove("drag-over");
      const col=z.closest(".bu-col");if(col)col.classList.remove("drag-over");});
    z.addEventListener("drop",e=>{e.preventDefault();z.classList.remove("drag-over");
      const col=z.closest(".bu-col");if(col)col.classList.remove("drag-over");
      const name=(e.dataTransfer.getData("text/plain")||"").trim();if(!name)return;
      const zone=z.getAttribute("data-zone");
      if(zone==="pool")buMoveToPool(name);else if(zone&&zone.indexOf("bu:")===0)buMoveToBu(+zone.slice(3),name);});});}
function buMoveToPool(name){if(!name)return;buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});buRender();}
function buMoveToBu(i,name){if(!name||i<0||i>=buList.length)return;
  buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});
  const cur=_salesArr(buList[i].销售);if(cur.indexOf(name)<0)cur.push(name);buList[i].销售=cur;buRender();}
function buRender(){const claimed=_claimedSales();
  // 池：库里有且未归属 + 配置 orphan 已在 claimed 外
  const poolNames=salesPool.map(p=>p.name).filter(n=>!claimed.has(n));
  claimed.forEach(n=>{if(!salesPool.some(p=>p.name===n)){/* assigned-only names stay in cols */}});
  const pool=document.getElementById("buPool");
  if(pool){pool.innerHTML=poolNames.length?poolNames.map(n=>_chipHtml(n,false)).join("")
    :'<div class="bu-empty">暂无未归属销售（库空或已全部分完）</div>';
    const h=document.getElementById("buPoolHint");
    if(h)h.textContent="共 "+salesPool.length+" 人 · 未归属 "+poolNames.length+" · 勾选批量或拖到下方 BU（一人一 BU）";}
  const cols=document.getElementById("buCols");
  if(cols){if(!buList.length){cols.innerHTML='<div class="muted" style="padding:8px">未配置 BU（功能关闭）——点「＋ 加一个 BU」</div>';}
    else{cols.innerHTML=buList.map((b,i)=>{
      const sales=_salesArr(b.销售);
      const owner=Array.isArray(b.负责人)?b.负责人.join("、"):String(b.负责人||"");
      return '<div class="bu-col"><div class="bu-col-meta">'
        +'<input placeholder="BU 名" value="'+esc(b.name||"")+'" onchange="buList['+i+'].name=this.value;if(acctList.length)acctRender()">'
        +'<input placeholder="负责人备注（顿号分隔）" value="'+esc(owner)+'" onchange="buList['+i+'].负责人=this.value">'
        +'<div style="display:flex;justify-content:space-between;align-items:center">'
        +'<span class="bu-col-title muted">销售 '+(sales.length)+' 人</span>'
        +'<button class="ghost mini" type="button" onclick="buDel('+i+')">删 BU</button></div></div>'
        +'<div class="bu-chips" data-zone="bu:'+i+'">'
        +(sales.length?sales.map(n=>_chipHtml(n,true)).join(""):'<div class="bu-empty">拖销售到这里</div>')
        +'</div></div>';}).join("");}}
  _bindDrag(document.getElementById("buBoard"));
  buRenderBatch();buUpdateUnassignedHint();buRenderAlloc();
  if(acctList.length)acctRender();}
function buAdd(){buList.push({name:"",负责人:[],销售:[],分摊比例:null});buRender();}
function buDel(i){if(!confirm("删除该 BU？对应权限账号将无法看到页面；销售回未归属池"))return;
  buList.splice(i,1);buRender();}
async function loadBuCfg(){try{
  const [d,pool]=await Promise.all([jget("/api/bu_config"),jget("/api/sales_pool").catch(()=>({sales:[]}))]);
  buList=(d.bus||[]).map(b=>({name:b.name,负责人:b.负责人||[],销售:_salesArr(b.销售),
    分摊比例:(b.分摊比例==null||!d.公共费用分摊启用)?null:Number(b.分摊比例)}));
  // 未启用分摊时界面显示全空（与「全空=不分摊」一致）；启用时回填比例
  salesPool=pool.sales||[];buPicked.clear();
  buUnassigned={unassigned_count:pool.unassigned_count||0,unassigned_orders_disp:pool.unassigned_orders_disp||""};
  buRender();}
  catch(e){document.getElementById("buMsg").textContent="读取失败:"+e.message;}}
async function buSave(){const m=document.getElementById("buMsg");m.textContent="保存并重算中…";
  try{// 规范化：全空比例 → 不分摊；有填 → 启用并校验 100%
    const payload=buList.map(b=>({name:b.name,负责人:b.负责人,销售:_salesArr(b.销售),分摊比例:b.分摊比例}));
    const d=await jpost("/api/bu_config",{bus:payload,公共费用分摊启用:buAllocEnabledFromList()});
    buList=(d.bus||[]).map(b=>({name:b.name,负责人:b.负责人||[],销售:_salesArr(b.销售),
      分摊比例:(b.分摊比例==null||!d.公共费用分摊启用)?null:Number(b.分摊比例)}));
    buRender();m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个 BU）";reloadDash();}
  catch(e){m.textContent="保存失败："+e.message;}}

// ---- 明细编辑（无限滚动加载）----
let curTable="收入明细";
const detail={page:0,pages:1,loading:false,loaded:0,
  url(p){let u="/api/detail?table="+encodeURIComponent(curTable)+"&page="+p+"&page_size=50";
    const m=ymVal("dY","dM"),q=document.getElementById("dQ").value.trim();
    if(m)u+="&month="+encodeURIComponent(m);if(q)u+="&q="+encodeURIComponent(q);return u;},
  reset(){this.page=0;this.pages=1;this.loaded=0;document.getElementById("dTbl").innerHTML="";
    document.getElementById("dWrap").scrollTop=0;this.next();},
  async next(){if(this.loading||this.page>=this.pages)return;this.loading=true;
    try{const d=await jget(this.url(this.page+1));this.page=d.page;this.pages=d.pages;
      const cols=d.columns,tbl=document.getElementById("dTbl");
      if(this.page===1)tbl.innerHTML="<tr>"+cols.map(c=>"<th>"+esc(c)+"</th>").join("")+"<th>操作</th></tr>";
      let h="";d.rows.forEach(r=>{const key=r["定位键"];h+="<tr>"+cols.map(c=>"<td>"+esc(r[c])+"</td>").join("")+
        '<td><button class="mini" onclick=\'editRow("'+STD[curTable]+'","'+encodeURIComponent(key)+'","'+curTable+'")\'>改</button> '+
        '<button class="mini ghost" onclick=\'removeRow("'+STD[curTable]+'","'+encodeURIComponent(key)+'")\'>剔除</button></td></tr>';});
      tbl.insertAdjacentHTML("beforeend",h);this.loaded+=d.rows.length;
      document.getElementById("dInfo").textContent="共"+d.total+"行（已载入"+this.loaded+"）";
    }catch(e){msg("查询失败:"+e.message);}this.loading=false;}};
function pickTable(t){curTable=t;
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  document.getElementById("dTableName").textContent=t;showSec("detail");detail.reset();}
function showManual(){document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on",b.dataset.t==="手填"));
  showSec("manual");mLoad();}
function dQuery(){detail.reset();}
function editRow(std,keyEnc,tkey){const key=decodeURIComponent(keyEnc);
  document.querySelectorAll("#detail .row-form").forEach(b=>b.remove());  // 同屏只留一个编辑器：重复点“改”=替换不追加
  const opts=(ADJ_FIELDS[tkey]||[]).map(f=>"<option>"+f+"</option>").join("");
  const id="ef_"+Math.random().toString(36).slice(2);
  const box=document.createElement("div");box.className="row-form";box.innerHTML=
    "定位键 "+esc(key)+" ｜ 字段<select id='"+id+"_f'>"+opts+"</select> 新值<input id='"+id+"_v' size='12'> "+
    "原因<input id='"+id+"_r' size='14'> <button class='mini' id='"+id+"_s'>保存</button> "+
    "<button class='mini ghost' id='"+id+"_c'>取消</button>";
  document.getElementById("detail").appendChild(box);
  document.getElementById(id+"_c").onclick=()=>box.remove();
  document.getElementById(id+"_s").onclick=async()=>{try{
    await jpost("/api/adjust",{目标表:std,定位键:key,字段:document.getElementById(id+"_f").value,
      新值:document.getElementById(id+"_v").value,原因:document.getElementById(id+"_r").value,类型:"改值"});
    box.remove();msg("已保存调整（秒级重算）");reloadDash();loadHealth();refreshUcBadge();dQuery();}catch(e){alert("保存失败："+e.message);}};}
async function removeRow(std,keyEnc){const key=decodeURIComponent(keyEnc);if(!confirm("剔除该行？（软删，可撤销）"))return;
  try{await jpost("/api/adjust",{目标表:std,定位键:key,字段:"",新值:"",原因:"剔除",类型:"剔除"});
    msg("已剔除");reloadDash();loadHealth();refreshUcBadge();dQuery();}catch(e){alert("失败："+e.message);}}

// ---- 手填 ----
async function mLoad(){const m=ymVal("mY","mM");if(!m){return;}
  const cur=await jget("/api/manual?month="+encodeURIComponent(m));const map={};cur.forEach(x=>map[x["项目"]]=x["金额"]);
  let h="<tr><th>项目</th><th>当前金额</th><th>新值</th><th></th></tr>";
  MANUAL_ITEMS.forEach(it=>{const id="mi_"+MANUAL_ITEMS.indexOf(it);
    h+="<tr><td>"+esc(it)+"</td><td>"+esc(map[it]!=null?map[it]:"（空）")+"</td>"+
    "<td><input id='"+id+"' size='12' value='"+(map[it]!=null?map[it]:"")+"'></td>"+
    "<td><button class='mini' onclick=\"mSave('"+encodeURIComponent(m)+"','"+encodeURIComponent(it)+"','"+id+"')\">保存</button></td></tr>";});
  document.getElementById("mTbl").innerHTML=h;bLoad();}
const BUDGET_METRICS=["下单年预算","回款年预算"];
async function bLoad(){const sel=document.getElementById("bY");
  if(!sel.options.length){const my=document.getElementById("mY");
    sel.innerHTML=my.innerHTML;sel.value=my.value;sel.onchange=bLoad;}
  const y=sel.value;const cur=await jget("/api/budget?year="+encodeURIComponent(y));
  const map={};cur.forEach(x=>map[x["指标"]]=x["金额"]);
  let h="<tr><th>指标</th><th>当前金额(元)</th><th>新值</th><th></th></tr>";
  BUDGET_METRICS.forEach((it,ix)=>{const id="bi_"+ix;
    const old=map[it]!=null?map[it]:null;
    h+="<tr><td>"+esc(it)+"</td><td>"+esc(old!=null?old:"（未填·图上无预算线）")+"</td>"+
    "<td><input id='"+id+"' size='14' value='"+(old!=null?old:"")+"'></td>"+
    "<td><button class='mini' onclick=\"bSave('"+encodeURIComponent(y)+"','"+encodeURIComponent(it)+"','"+id+"',null,"+(old!=null?"'"+old+"'":"null")+")\">保存</button></td></tr>";});
  document.getElementById("bTbl").innerHTML=h;bdLoad(y);}
async function bSave(yEnc,itEnc,id,scope,oldVal){const v=document.getElementById(id).value.trim();
  if(v===""||isNaN(parseFloat(v))){alert("请输入数字金额（元）");return;}
  if(oldVal!=null&&!confirm("「"+decodeURIComponent(itEnc)+(scope?"·"+decodeURIComponent(scope):"")+"」已有预算 "+oldVal+"，确认改为 "+v+"？（改动会留痕）"))return;
  const body={年份:decodeURIComponent(yEnc),指标:decodeURIComponent(itEnc),金额:parseFloat(v)};
  if(scope)body["范围"]=decodeURIComponent(scope);
  try{await jpost("/api/budget",body);
    msg("已保存年度预算（留痕·看板已重算）");reloadDash();bLoad();}catch(e){alert("保存失败："+e.message);}}
async function bdLoad(y){
  const [depts,cur]=await Promise.all([jget("/api/budget_depts"),jget("/api/budget?year="+encodeURIComponent(y))]);
  const map={};cur.filter(x=>x["指标"]==="费用年预算").forEach(x=>map[x["范围"]]=x["金额"]);
  if(!depts.length){document.getElementById("bdTbl").innerHTML="<tr><td class='muted'>台账暂无「预算归属部门」数据（老台账没这列或全空）</td></tr>";return;}
  let h="<tr><th>预算归属部门</th><th>当前年预算(元)</th><th>新值</th><th></th></tr>";
  depts.forEach((d,ix)=>{const id="bd_"+ix;const old=map[d]!=null?map[d]:null;
    h+="<tr><td>"+esc(d)+"</td><td>"+esc(old!=null?old:"（未填·不进执行卡）")+"</td>"+
    "<td><input id='"+id+"' size='14' value='"+(old!=null?old:"")+"'></td>"+
    "<td><button class='mini' onclick=\"bSave('"+encodeURIComponent(y)+"','"+encodeURIComponent("费用年预算")+"','"+id+"','"+encodeURIComponent(d)+"',"+(old!=null?"'"+old+"'":"null")+")\">保存</button></td></tr>";});
  document.getElementById("bdTbl").innerHTML=h;}
async function mSave(mEnc,itEnc,id){const v=document.getElementById(id).value.trim();if(v===""){alert("填金额");return;}
  try{await jpost("/api/manual",{归属月:decodeURIComponent(mEnc),项目:decodeURIComponent(itEnc),金额:parseFloat(v)});
    msg("手填已保存（留痕+重算）");reloadDash();loadHealth();mLoad();}catch(e){alert("失败："+e.message);}}

// ---- 异常处理（总览 / 调整台账 / 下单未填部门 / 费用未分类 / 历史快照）----
function showReview(which){document.querySelectorAll("#sub-review .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===which));
  showSec(which);if(which==="overview")ovLoad();if(which==="ledger")lLoad();
  if(which==="orderdept")odLoad();if(which==="unclassified")ucLoad();if(which==="history")hisLoad();
  if(which==="audit")auLoad();}

// 操作记录（C3 配置变更留痕）：倒序、可按类别筛、最近200
let AU_CATS_FILLED=false;
async function auLoad(){const info=document.getElementById("auInfo"),tbl=document.getElementById("auTbl");
  const cat=document.getElementById("auCat").value;
  try{const d=await jget("/api/config_changes"+(cat?("?category="+encodeURIComponent(cat)):""));
    if(!AU_CATS_FILLED&&d.categories){const sel=document.getElementById("auCat");
      sel.innerHTML='<option value="">全部</option>'+d.categories.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join("");
      sel.value=cat;AU_CATS_FILLED=true;}
    const rows=d.changes||[];info.textContent="共 "+rows.length+" 条"+(cat?("（"+cat+"）"):"");
    if(!rows.length){tbl.innerHTML="<tr><td class='muted'>暂无记录（发生配置变更后自动出现）</td></tr>";return;}
    tbl.innerHTML="<tr><th>时间</th><th>操作账号</th><th>类别</th><th>变更摘要</th></tr>"+
      rows.map(r=>"<tr><td class='muted'>"+esc(r["时间"])+"</td><td>"+esc(r["操作账号"])+
        "</td><td>"+esc(r["类别"])+"</td><td>"+esc(r["摘要"])+"</td></tr>").join("");
  }catch(e){info.textContent="加载失败："+e.message;}}

// 总览：异常计数卡（新增一类异常=EXC_CARDS 注册一条 + /api/exceptions 加一个键；R4 冲突待确认已留位）
const EXC_CARDS=[
  {key:"order_unfilled_dept",label:"下单未填部门",desc:"智云源头没填部门，排名灰显待归类",go:()=>showReview("orderdept")},
  {key:"expense_unclassified",label:"费用未分类（台账）",desc:"收单台账没填对应报表大类，暂未计入费用",go:()=>showReview("unclassified")},
  {key:"adjust_expired",label:"过期疑似调整",desc:"源头已改、我的调整未套用，需拍板听谁的",go:()=>showReview("ledger")},
  {key:"adjust_missing",label:"调整失配",desc:"调整定位键在源头找不到了（行删了/键变了）",go:()=>showReview("ledger")},
  {key:"__conflict",label:"冲突待确认",desc:"智云改了 vs 这里改了（R4 上线后启用）",disabled:true},
];
async function ovLoad(){const el=document.getElementById("ovCards");
  let ex={};try{ex=await jget("/api/exceptions");}catch(e){el.innerHTML="<div class='muted'>加载失败："+esc(e.message)+"</div>";return;}
  setBadges(ex);
  const h=(window._health||{});const hHtml=(h.result&&h.result!=="绿")||((h.warnings||[]).length)
    ?"<div class='muted' style='margin-top:6px'>另：顶栏体检 "+esc(h.result||"?")+((h.warnings||[]).length?("·"+h.warnings.length+"警"):"")+"（抓数/运行信号，点顶栏「体检」看）</div>":"";
  el.innerHTML=EXC_CARDS.map(c=>{
    if(c.disabled)return "<div class='row-form' style='margin:0;padding:14px 16px;opacity:.45'>"+
      "<div style='font-weight:700'>"+esc(c.label)+"</div><div class='muted' style='margin-top:4px'>"+esc(c.desc)+"</div></div>";
    const n=ex[c.key]||0,ok=!n;
    return "<div class='row-form ovcard' data-k='"+esc(c.key)+"' style='margin:0;padding:14px 16px;cursor:pointer;border:1px solid "+(ok?"#14532d":"#7c2d12")+"'>"+
      "<div style='display:flex;align-items:center;gap:8px'><span style='font-size:22px;font-weight:800;color:"+(ok?"#4ade80":"#fb923c")+"'>"+n+"</span>"+
      "<span style='font-weight:700'>"+esc(c.label)+"</span></div>"+
      "<div class='muted' style='margin-top:4px'>"+(ok?"✓ 无待处理":esc(c.desc))+"</div></div>";}).join("")+hHtml;
  el.querySelectorAll(".ovcard").forEach(d=>{d.onclick=()=>{const c=EXC_CARDS.find(x=>x.key===d.dataset.k);if(c&&c.go)c.go();};});}

// 下单未填部门：清单 + 行内选部门→写调整（复用 /api/adjust，处理后行消失、角标减一）
let OD_DEPTS=[];
function odUrl(p){return "/api/detail?table="+encodeURIComponent("下单")+"&unfilled_dept=1&page="+p+"&page_size=200";}
async function odLoad(){const tbl=document.getElementById("odTbl");tbl.innerHTML="";
  try{OD_DEPTS=await jget("/api/order_depts");}catch(e){}
  let page=1,pages=1,total=0;
  try{do{const d=await jget(odUrl(page));pages=d.pages;total=d.total;
    if(page===1)tbl.innerHTML="<tr><th>下单日期</th><th>订单号</th><th>销售</th><th>金额</th><th>归到哪个部门</th><th></th></tr>";
    let h="";d.rows.forEach(r=>{const key=r["定位键"];
      const opts="<option value=''>选部门…</option>"+OD_DEPTS.map(x=>"<option>"+esc(x)+"</option>").join("");
      h+="<tr><td>"+esc(r["下单日期"])+"</td><td>"+esc(r["订单号"])+"</td><td>"+esc(r["销售"])+"</td><td>"+esc(r["下单预估额"])+
        "</td><td><select data-key='"+esc(encodeURIComponent(key))+"'>"+opts+"</select></td>"+
        "<td><button class='mini' onclick='odSave(this)'>保存</button></td></tr>";});
    tbl.insertAdjacentHTML("beforeend",h);page++;
  }while(page<=pages&&page<=50);}catch(e){msg("查询失败:"+e.message);}
  document.getElementById("odInfo").textContent="待归类 "+total+" 笔";
  const b=document.getElementById("odBadge");b.textContent=total;b.className="badge"+(total?"":" zero");}
async function odSave(btn){const tr=btn.closest("tr"),sel=tr.querySelector("select");
  const dept=sel.value;if(!dept){alert("先选部门");return;}
  const key=decodeURIComponent(sel.dataset.key);btn.disabled=true;
  try{await jpost("/api/adjust",{目标表:"std_下单",定位键:key,字段:"部门",新值:dept,原因:"异常处理·归类部门",类型:"改值"});
    tr.remove();msg("已归类（写入数据修正·秒级重算）");reloadDash();loadHealth();refreshUcBadge();
    const b=document.getElementById("odBadge"),n=Math.max(0,(parseInt(b.textContent,10)||1)-1);
    b.textContent=n;b.className="badge"+(n?"":" zero");
    document.getElementById("odInfo").textContent="待归类 "+n+" 笔";
  }catch(e){btn.disabled=false;alert("保存失败："+e.message);}}
// 历史快照：年→月→日 级联回看（每天最后一次更新的页面原样；快照多了也不乱）
let HIS=[];
function _hisSel(id){return document.getElementById(id);}
async function hisLoad(){const info=_hisSel("hisInfo");
  try{HIS=await jget("/api/history");   // 已按天倒序
    if(!HIS.length){info.textContent="还没有历史快照（每次更新后自动生成，明天起就有了）";
      _hisSel("hisFrame").src="about:blank";["hisY","hisM","hisD"].forEach(i=>_hisSel(i).innerHTML="");return;}
    info.textContent="共 "+HIS.length+" 天";
    const years=[...new Set(HIS.map(x=>x.day.slice(0,4)))];
    _hisSel("hisY").innerHTML=years.map(y=>'<option value="'+y+'">'+y+'年</option>').join("");
    _hisSel("hisY").onchange=()=>hisFillM();
    _hisSel("hisM").onchange=()=>hisFillD();
    _hisSel("hisD").onchange=()=>hisShow(_hisSel("hisD").value);
    hisFillM();
  }catch(e){info.textContent="加载失败:"+e.message;}}
function hisFillM(){const y=_hisSel("hisY").value;
  const months=[...new Set(HIS.filter(x=>x.day.slice(0,4)===y).map(x=>x.day.slice(4,6)))];
  _hisSel("hisM").innerHTML=months.map(m=>'<option value="'+m+'">'+(+m)+'月</option>').join("");
  hisFillD();}
function hisFillD(){const y=_hisSel("hisY").value,m=_hisSel("hisM").value;
  const days=HIS.filter(x=>x.day.slice(0,4)===y&&x.day.slice(4,6)===m);
  _hisSel("hisD").innerHTML=days.map(x=>'<option value="'+x.day+'">'+(+x.day.slice(6))+'日（存于 '+esc(x.saved_at)+'）</option>').join("");
  if(days.length)hisShow(days[0].day);}
function hisShow(day){_hisSel("hisFrame").src="/api/history/"+day;}
let LADJ=[];
async function lLoad(){LADJ=await jget("/api/adjustments");lRender();}
function lRender(){const expOnly=document.getElementById("lExpOnly").checked;
  const d=expOnly?LADJ.filter(a=>a["状态"]==="过期疑似"):LADJ;
  const nExp=LADJ.filter(a=>a["状态"]==="过期疑似").length;
  document.getElementById("lInfo").textContent="共 "+LADJ.length+" 条（过期疑似 "+nExp+"）";
  document.getElementById("lBatchBtn").style.display=nExp?"":"none";
  let h="<tr><th>id</th><th>时间</th><th>操作账号</th><th>目标表</th><th>字段</th><th>原值→新值</th><th>类型</th><th>状态</th><th></th></tr>";
  d.forEach(a=>{const exp=a["状态"]==="过期疑似";
    let ops="";
    if(exp&&a["类型"]==="改值")ops+="<button class='mini' onclick='lRearm("+a.id+")'>坚持我的数</button> ";
    if(a["状态"]!=="已撤销")ops+="<button class='mini ghost' onclick='lRevoke("+a.id+")'>撤销</button>";
    h+="<tr class='"+(exp?"exp":"")+"'><td>"+a.id+"</td><td>"+esc(a["创建时间"])+"</td><td>"+esc(a["经手人"])+
    "</td><td>"+esc(a["目标表"])+"</td><td>"+esc(a["字段"])+"</td><td>"+esc(a["原值"])+" → "+esc(a["新值"])+"</td><td>"+esc(a["类型"])+
    "</td><td>"+esc(a["状态"])+"</td><td>"+ops+"</td></tr>";});
  document.getElementById("lTbl").innerHTML=h;}
async function lRevoke(id){if(!confirm("撤销该调整？（=认可源头新值，页面继续用源头值）"))return;
  try{await jpost("/api/adjust/"+id+"/revoke",{});
  msg("已撤销");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}
async function lRearm(id){const a=LADJ.find(x=>x.id===id)||{};
  if(!confirm("坚持我的数？\n"+(a["目标表"]||"")+" · "+(a["字段"]||"")+"：将继续使用你改的值「"+(a["新值"]||"")+"」，覆盖源头新值。"))return;
  try{await jpost("/api/adjust/"+id+"/rearm",{});
  msg("已重新生效");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}
function lBatchAsk(){const n=LADJ.filter(a=>a["状态"]==="过期疑似").length;if(!n)return;
  const box=document.getElementById("lConfirm");
  box.innerHTML="将批量撤销 <b>"+n+"</b> 条「过期疑似」调整 = 全部认可源头新值（页面本就在用新值，此操作确认事实、清掉黄灯）。"+
    "撤销后如需恢复某条，去明细里重新改即可。 "+
    "<button class='mini' onclick='lBatchDo()'>确认保存</button> <button class='mini ghost' onclick='lBatchCancel()'>取消</button>";
  box.style.display="";}
function lBatchCancel(){const box=document.getElementById("lConfirm");box.style.display="none";box.innerHTML="";}
async function lBatchDo(){lBatchCancel();
  try{const r=await jpost("/api/adjust/expired/revoke_all",{});
  msg("已批量撤销 "+r.revoked+" 条");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}

// ---- 未填分类：只读清单（不提供当场补；请在源头收单台账补填，下次更新自动计入）----
let ucTotal=0;
function ucUrl(p){return "/api/detail?table="+encodeURIComponent("费用明细")+"&unclassified=1&page="+p+"&page_size=200";}
async function ucLoad(){const tbl=document.getElementById("ucTbl");tbl.innerHTML="";
  let page=1,pages=1;
  try{do{const d=await jget(ucUrl(page));pages=d.pages;ucTotal=d.total;
    if(page===1)tbl.innerHTML="<tr><th>收单日期</th><th>金额</th><th>预算明细费用类型</th></tr>";
    let h="";d.rows.forEach(r=>{
      h+="<tr><td>"+esc(r["收单日期"]||r["收单月份"])+"</td><td>"+esc(r["含税金额"])+
        "</td><td>"+esc(r["预算明细费用类型"])+"</td></tr>";});
    tbl.insertAdjacentHTML("beforeend",h);page++;
  }while(page<=pages&&page<=50);}catch(e){msg("查询失败:"+e.message);}
  document.getElementById("ucInfo").textContent="未分类 "+ucTotal+" 笔";setUcBadge(ucTotal);}
function setUcBadge(n){const b=document.getElementById("ucBadge");b.textContent=n;b.className="badge"+(n?"":" zero");}
function setBadges(ex){setUcBadge(ex.expense_unclassified||0);
  const b=document.getElementById("odBadge"),n=ex.order_unfilled_dept||0;
  b.textContent=n;b.className="badge"+(n?"":" zero");}
async function refreshUcBadge(){try{setBadges(await jget("/api/exceptions"));}catch(e){}}

// ---- 年月下拉（数据自2026起，年份随时间自动往后长；2026前不给选）----
function pad2(n){return String(n).padStart(2,"0");}
function ymVal(y,m){const yy=document.getElementById(y).value,mm=document.getElementById(m).value;return (yy&&mm)?(yy+"-"+pad2(mm)):"";}
function fillY(sel,withAll){const top=Math.max(new Date().getFullYear(),2026);let h=withAll?'<option value="">全部年</option>':"";
  for(let y=top;y>=2026;y--)h+="<option value='"+y+"'>"+y+"年</option>";document.getElementById(sel).innerHTML=h;}
function fillM(sel,withAll){let h=withAll?'<option value="">全部月</option>':"";
  for(let m=1;m<=12;m++)h+="<option value='"+m+"'>"+m+"月</option>";document.getElementById(sel).innerHTML=h;}
function initYM(){const d=new Date();
  fillY("mY",false);fillM("mM",false);                                  // 手填：必选、默认当前年月
  document.getElementById("mY").value=String(Math.max(d.getFullYear(),2026));document.getElementById("mM").value=d.getMonth()+1;
  fillY("dY",true);fillM("dM",true);}                                   // 明细筛选：可选、默认全部
initYM();
document.getElementById("dWrap").addEventListener("scroll",function(){
  if(this.scrollTop+this.clientHeight>=this.scrollHeight-80)detail.next();});
loadHealth();refreshUcBadge();loadAdjFields();loadVersion();setInterval(loadHealth,30000);
// 打开页面时若更新已在跑（别处/定时触发），按钮跟着进入进度态
jget("/api/refresh_status").then(s=>{if(s.running){document.getElementById("btnRefresh").disabled=true;refT0=Date.now();pollRefresh();}}).catch(()=>{});
</script></body></html>"""


# ---------------- FastAPI 应用 ----------------
def create_app(cfg, root=None) -> FastAPI:
    app = FastAPI(title="甲骨易智能经营罗盘", docs_url=None, redoc_url=None, openapi_url=None)
    sec = _load_or_init_secret(cfg, root)
    # 确保账号文件存在（部署零配置）
    accounts.load_accounts(cfg, root, create=True)

    def _user(request: Request) -> str | None:
        """管理员会话：cookie 主体=账号名，且账号表里权限仍是「管理员」。经手人=该账号。"""
        name = _check_token(sec, request.cookies.get(COOKIE, ""))
        if not name:
            return None
        acc = accounts.find_account(cfg, root, name)
        return name if accounts.is_admin(acc) else None

    def _vacct(request: Request) -> str | None:
        """查看端会话：返回登录账号名（权限运行时再解析）。"""
        return _check_vsubject(sec, request.cookies.get(VCOOKIE, ""))

    def _vacc_row(request: Request) -> dict | None:
        name = _vacct(request)
        return accounts.find_account(cfg, root, name) if name else None

    def _can_view_main(request: Request) -> bool:
        """整体页/全公司口径：整体权限账号 或 管理员会话。BU 账号不行。"""
        if _user(request):
            return True
        acc = _vacc_row(request)
        return accounts.is_main(acc)

    def _can_view_bu(request: Request, bu_name: str) -> bool:
        if _user(request):
            return True
        acc = _vacc_row(request)
        if not acc:
            return False
        if accounts.is_main(acc):
            return True
        return accounts.can_see_bu(acc, bu_name)  # 多 BU：在其绑定名单内即可

    def _bu_switcher_html(my_names, current: str) -> str:
        """多 BU 账号看 BU 页时顶部的「我的 BU」切换条：**只列该账号绑定且仍存在的 BU**
        （绝不列他 BU，铁律12）。单个绑定不出条。"""
        from urllib.parse import quote

        def esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        existing = [n for n in my_names if n in _state.get("bu_pages", {})]
        if len(existing) <= 1:
            return ""
        links = "".join(
            f'<a class="bu-nav-a" href="/bu/{quote(n)}"'
            + (' aria-current="page" style="border-color:var(--blue)"' if n == current else "")
            + f'>{esc(n)}</a>' for n in existing)
        return ('<div class="bu-nav" role="navigation" aria-label="我的 BU 分页">'
                '<span class="bu-nav-label">我的 BU</span>'
                '<span class="bu-nav-links">' + links + '</span></div>')

    def _bu_view_html(name: str, my_names=None, hide_pw: bool = False) -> str:
        """渲染某 BU 页 + 可选注入（管理员隐藏自改密码 / 多 BU 账号的切换条）。缺页返回空串。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            return ""
        parts = []
        if hide_pw:
            parts.append(_HIDE_PW_STYLE)
        if my_names:
            parts.append(_bu_switcher_html(my_names, name))
        html = page["html"]
        if any(parts):
            html = html.replace('<div class="wrap">', "".join(parts) + '<div class="wrap">', 1)
        return html

    def _set_vcookie(resp, account: str):
        resp.set_cookie(VCOOKIE, _make_token(sec, account), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        return resp

    def _set_acookie(resp, account: str):
        resp.set_cookie(COOKIE, _make_token(sec, account), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        return resp

    @app.get("/", response_class=HTMLResponse)
    def user_page(request: Request):
        """看板统一入口（v8.0）：
        管理员会话 → 整体页；整体权限 → 整体页（带 BU 入口条）；BU 权限 → 本 BU 页；
        未登录 → 登录页。"""
        if _user(request):
            return HTMLResponse(_main_with_nav(hide_pw=True) or "<h1>数据尚未生成，请稍候刷新</h1>")
        acc = _vacc_row(request)
        if acc:
            if accounts.is_main(acc):
                return HTMLResponse(_main_with_nav() or "<h1>数据尚未生成，请稍候刷新</h1>")
            names = accounts.bu_names_of(acc)  # 多 BU：绑定名单（旧单 BU 账号=[该名]）
            if names:
                existing = [n for n in names if n in _state.get("bu_pages", {})]
                if not existing:
                    return HTMLResponse(_view_login_page(
                        "你绑定的 BU 已被管理员移除，请重新登录或联系管理员"))
                # 落在第一个绑定的 BU；绑定多个时顶部带「我的 BU」切换条
                return HTMLResponse(_bu_view_html(existing[0], names))
            # 管理员账号误走查看 cookie：引导去 /admin
            if accounts.is_admin(acc):
                return RedirectResponse("/admin", status_code=303)
        return HTMLResponse(_view_login_page())

    def _main_with_nav(hide_pw: bool = False) -> str:
        """整体页 + BU 入口条（只有整体/管理员会话能拿到本页，无泄漏面）+ A3 未归属提示（随周期切）。
        hide_pw=True（管理员会话看）：隐藏右上「🔑密码」自改密码入口——管理员改密码走 /admin「设置→账号与权限」，
        避免在内嵌看板里误改（管理员本无查看会话，点了也只会 401，属确认无用的入口）。"""
        html = _state["user_html"]
        if not html:
            return html
        from urllib.parse import quote

        def _esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        parts = []
        if hide_pw:
            parts.append(_HIDE_PW_STYLE)
        names = list(_state.get("bu_pages", {}))
        if names:
            links = "".join(f'<a class="bu-nav-a" href="/bu/{quote(n)}">{_esc(n)}</a>' for n in names)
            parts.append('<div class="bu-nav" role="navigation" aria-label="BU 分页">'
                         '<span class="bu-nav-label">业务 BU 分页</span>'
                         '<span class="bu-nav-links">' + links + '</span>'
                         + _unassigned_hint_html(_state.get("summary"), _esc) + '</div>')
        if parts:
            return html.replace('<div class="wrap">', "".join(parts) + '<div class="wrap">', 1)
        return html

    def _unassigned_hint_html(summary, esc) -> str:
        """A3 整体页未归属提示（只在整体/管理员会话出现，BU 页绝不渲染）：
        每周期一个预渲染 .pv 块（前端按周期切显示，零金额运算=铁律2）；未归属人数 N=0 → 整行不渲染。"""
        un = ((summary or {}).get("meta") or {}).get("unassigned") or {}
        n = int(un.get("count") or 0)
        by = un.get("by_period") or {}
        if n <= 0 or not by:
            return ""
        yk = (summary["meta"]).get("year_key")
        blocks = "".join(
            f'<span class="pv" data-blk="{esc(k)}" style="{"" if k == yk else "display:none"}">'
            f'另有未归属 BU 的业务 <b>{esc(disp)}</b>（{n} 名销售待配置归属，未计入任何 BU 页）</span>'
            for k, disp in by.items())
        return ('<span class="bu-unassigned" role="note" title="这部分业务的销售还没归到任何 BU，'
                '故各 BU 合计小于全公司——去管理端设置页「BU 数据归属」勾选即计入">' + blocks + '</span>')

    @app.post("/login")
    def viewer_login(account: str = Form(""), password: str = Form("")):
        """账号+密码登录，按权限分流：管理员→/admin；整体→/；BU→/。
        账号不存在与密码错同一文案。"""
        account = account.strip()
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc:
            return HTMLResponse(_view_login_page("账号或密码不正确", account), status_code=401)
        accounts.mark_login(cfg, root, account)
        if accounts.is_admin(acc):
            return _set_acookie(RedirectResponse("/admin", status_code=303), account)
        return _set_vcookie(RedirectResponse("/", status_code=303), account)

    @app.get("/bu/{name}", response_class=HTMLResponse)
    def bu_page(name: str, request: Request):
        """BU 页：本 BU 权限账号（含多 BU 绑定）/ 整体账号 / 管理员可看；未登录出登录页；不存在 404。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            return HTMLResponse(_view_login_page())
        if _user(request):  # 管理员看 BU 页也隐藏「🔑密码」自改入口（与整体页一致）
            return HTMLResponse(page["html"].replace(
                '<div class="wrap">', _HIDE_PW_STYLE + '<div class="wrap">', 1))
        # 多 BU 账号：注入「我的 BU」切换条（只列其绑定的 BU）；整体账号 bu_names_of=[] 不注入
        my = accounts.bu_names_of(_vacc_row(request))
        return HTMLResponse(_bu_view_html(name, my))

    @app.post("/api/my_passwd")
    def api_my_passwd(request: Request, payload: dict = Body(default={})):
        """看的人自改密码（整体页/BU 页右上 🔑）：验旧设新，写回 看板账号.json 明文。"""
        name = _vacct(request)
        if not name:
            raise HTTPException(status_code=401, detail="请先登录看板")
        old, new = str(payload.get("old") or ""), str(payload.get("new") or "")
        err = accounts.change_password(cfg, root, name, old, new)
        if err:
            raise HTTPException(status_code=400, detail=err)
        _audit(cfg, root, name, ("密码", f"账号 {name} 自改密码"))  # C3：不记密码内容
        return {"note": "密码已修改"}

    @app.get("/api/accounts")
    def api_accounts_get(request: Request):
        """账号表（管理员会话）：含明文密码。绝不出现在其他出口。"""
        _require(request)
        rows = [accounts.public_row(a, with_password=True) for a in accounts.load_accounts(cfg, root)]
        return {"accounts": rows, "count": len(rows),
                "master_account": accounts.MASTER_ACCOUNT}

    @app.post("/api/accounts")
    def api_accounts_post(request: Request, payload: dict = Body(default={})):
        """保存账号表（管理员）。至少保留一个管理员；总账号不可删。C3：变更留痕（密码只记「改密码」）。"""
        user = _require(request)
        raw = payload.get("accounts")
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="accounts 须为列表")
        if len(raw) > 50:
            raise HTTPException(status_code=400, detail="账号数量过多（上限 50）")
        old_accs = accounts.load_accounts(cfg, root, create=False)
        try:
            saved = accounts.save_accounts(cfg, root, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        _audit(cfg, root, user, _diff_accounts(old_accs, saved))
        rows = [accounts.public_row(a, with_password=True) for a in saved]
        return {"accounts": rows, "count": len(rows), "note": "已保存",
                "master_account": accounts.MASTER_ACCOUNT}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        if _user(request):
            return HTMLResponse(_state["admin_html"] or "<h1>数据尚未生成</h1>")
        return HTMLResponse(_login_page())

    @app.post("/admin/login")
    def admin_login(account: str = Form(""), password: str = Form(""),
                    identity: str = Form("")):  # identity 兼容旧表单字段名，忽略
        account = (account or identity or "").strip()
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc or not accounts.is_admin(acc):
            return HTMLResponse(_login_page("账号或密码不正确", account), status_code=401)
        accounts.mark_login(cfg, root, account)
        return _set_acookie(RedirectResponse("/admin", status_code=303), account)

    @app.get("/admin/logout")
    def admin_logout():
        resp = RedirectResponse("/admin", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/api/detail")
    def api_detail(request: Request, table: str = Query("收入明细"), month: str | None = None,
                   q: str | None = None, page: int = 1, page_size: int = 50,
                   unclassified: bool = False, unfilled_dept: bool = False):
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        conn = db.connect(cfg, root)
        try:
            try:
                return JSONResponse(db.query_detail(conn, table, month, q, page, page_size,
                                                    unclassified, unfilled_dept))
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()

    @app.get("/api/daily")
    def api_daily(request: Request, start: str = Query(""), end: str = Query(""), top: int = Query(10)):
        """按天明细（用户端「明细」入口·迭代计划13批次B）：任意日期区间的逐日下单/回款 + 期内排名。
        v7.8 起要求整体页/管理员会话（全公司口径出口，BU 会话不给——否则 BU 链接持有者可绕过页面隔离）；
        **纯只读**、无任何写路径；金额显示串全部后端算好（铁律2）。入参严格校验：ISO日期、start<=end、区间≤366天。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        import datetime as _dt
        try:
            s = _dt.date.fromisoformat(start)
            e = _dt.date.fromisoformat(end)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYY-MM-DD")
        if e < s:
            raise HTTPException(status_code=400, detail="结束日期须不早于开始日期")
        if (e - s).days > 366:
            raise HTTPException(status_code=400, detail="区间最长 366 天")
        top = max(1, min(2000, int(top)))   # 排名条数：默认前10，「其余点开看明细」传 2000 拿全量
        conn = db.connect(cfg, root)
        try:
            orders = db.load_orders(cfg, conn)
            receipts = db.load_receipts(cfg, conn)
        finally:
            conn.close()
        import charts
        import profit as _profit
        d = _profit.compute_daily(orders, receipts, cfg["columns"], s, e, top=top)

        def _wan(v):   # 显示串：与排名卡一致（负数全角−）
            return ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"

        for row in d["days"]:
            row["orders_disp"], row["receipts_disp"] = _wan(row.pop("orders")), _wan(row.pop("receipts"))
        t = d["totals"]
        t["orders_disp"], t["receipts_disp"] = _wan(t.pop("orders")), _wan(t.pop("receipts"))
        for rk in d["rankings"].values():
            for it in rk["items"]:
                it["disp"] = _wan(it.pop("amount"))
            if rk.get("others"):
                rk["others"]["disp"] = _wan(rk["others"].pop("amount"))
            if rk.get("unfilled"):
                rk["unfilled"]["disp"] = _wan(rk["unfilled"].pop("amount"))
            rk.pop("total", None)   # 用不到就不下发，防前端拿去做运算
        return {"start": start, "end": end, **d}

    @app.get("/api/profit_ranking")
    def api_profit_ranking(request: Request, dim: str = Query(""), start: str = Query(""),
                           end: str = Query(""), top: int = Query(5000)):
        """板块③「收入与毛利结构」全量明细（「其余 N 个」点开）：确认口径 收入/毛利 按客户/销售。
        与 /api/daily 同为全公司口径出口——要整体页/管理员会话（BU 会话 401，防绕过页面隔离）；
        **纯只读**；金额/毛利率显示串全部后端算好（铁律2）。入参严格校验：dim∈{customer,sales}、ISO 日期、区间≤366天。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        name_col = {"customer": "客户", "sales": "销售"}.get(dim)
        if not name_col:
            raise HTTPException(status_code=400, detail="dim 须为 customer 或 sales")
        import datetime as _dt
        try:
            s = _dt.date.fromisoformat(start)
            e = _dt.date.fromisoformat(end)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYY-MM-DD")
        if e < s:
            raise HTTPException(status_code=400, detail="结束日期须不早于开始日期")
        if (e - s).days > 366:
            raise HTTPException(status_code=400, detail="区间最长 366 天")
        top = max(1, min(5000, int(top)))
        conn = db.connect(cfg, root)
        try:
            project = db.load_project_detail(cfg, conn)
        finally:
            conn.close()
        import charts
        import profit as _profit
        vat = cfg["tax"]["vat_rate"]
        rk = _profit.compute_profit_ranking(project, name_col, cfg["columns"], s, e, vat, top=top)

        def _wan(v):
            return ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"

        def _mg(mp):
            return f"项目毛利率 {mp:.0f}%" if mp is not None else "项目毛利率 —"

        items = [{"name": it["name"], "revenue_disp": _wan(it["revenue"]), "margin_disp": _mg(it["margin_pct"])}
                 for it in rk["items"]]
        if rk.get("unfilled"):
            uf = rk["unfilled"]
            items.append({"name": "（未填）", "revenue_disp": _wan(uf["revenue"]),
                          "margin_disp": _mg(uf["margin_pct"]), "unfilled": True})
        return {"dim": dim, "start": start, "end": end, "items": items}

    @app.get("/api/exceptions")
    def api_exceptions(request: Request):
        """异常处理「总览」计数（管理员）。体检黄红是运行信号，留在 /api/health，不在这。"""
        _require(request)  # 同函数作用域下文定义，调用时已存在
        conn = db.connect(cfg, root)
        try:
            return db.exceptions_summary(conn)
        finally:
            conn.close()

    @app.get("/api/order_depts")
    def api_order_depts(request: Request):
        """下单表已出现过的部门清单（「下单未填部门」归类下拉用）。"""
        _require(request)
        conn = db.connect(cfg, root)
        try:
            return db.list_order_depts(conn)
        finally:
            conn.close()

    @app.get("/api/health")
    def api_health():
        """体检状态条数据源（公开：只给绿/黄/红 + 时间 + 各源行数，不含金额/客户名）。"""
        conn = db.connect(cfg, root)
        try:
            run_log = db.latest_run(conn)
        finally:
            conn.close()
        meta = (_state.get("summary") or {}).get("meta", {})
        health = meta.get("health", {})
        result = (run_log or {}).get("结果")               # 黄/红/绿：管道运行日志
        reasons = _run_reasons((run_log or {}).get("体检", {}))  # 「黄/红」：为啥（fetch/过期调整）
        # A3：未归属销售>0 → 至少判黄 + 顶栏短原因（沿用 v8.0 机制；不覆盖已判红）
        n_un = int((meta.get("unassigned") or {}).get("count") or 0)
        if n_un > 0:
            reasons = [f"{n_un} 名销售未归属 BU（业务不进任何 BU 页，各 BU 合计小于全公司）"] + reasons
            if result in ("绿", None):   # 未判红时至少判黄（无运行日志时 result 为 None 也升黄）
                result = "黄"
        return {
            "result": result,
            "run_time": (run_log or {}).get("时间"),
            "built_at": _state.get("built_at"),
            "sources": health.get("sources", []),
            "warnings": health.get("warnings", []),          # 「警」：数据体检（未填分类等）
            "run_reasons": reasons,
        }

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @app.post("/api/refresh")
    def api_refresh(request: Request):
        """立即更新=完整 pipeline（fetch+重读+重建+重放），后台线程跑、立即返回（在线抓约80秒）。
        运行中互斥，重复点返回进行中；进度轮询 /api/refresh_status。"""
        _require(request)
        if not start_refresh_async(cfg, root, "manual"):
            return JSONResponse({"status": "running", "detail": "更新进行中，请稍候"}, status_code=409)
        return {"status": "started", "refreshing": _state["refreshing"]}

    @app.get("/api/refresh_status")
    def api_refresh_status(request: Request):
        _require(request)
        return {"running": bool(_state["refreshing"]), "refreshing": _state["refreshing"],
                "last": _state["last_refresh"], "built_at": _state["built_at"],
                "zhiyun_auto_fetch": bool(cfg.get("zhiyun_auto_fetch"))}

    @app.get("/export.png")
    def api_export_png(request: Request, blk: str = ""):
        """导出=当前所选周期的整页 PNG（服务端 Playwright 截图）。v7.8 起要求整体页/管理员会话
        （导出的是全公司主页）。"""
        if not _can_view_main(request):
            raise HTTPException(status_code=401, detail="请先登录看板")
        html = _state.get("user_html")
        if not html:
            raise HTTPException(status_code=503, detail="页面尚未构建，稍后再试")
        keys = set(((_state.get("summary") or {}).get("periods") or {}).keys())
        if blk and keys and blk not in keys:
            raise HTTPException(status_code=400, detail="未知周期")
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一张导出图，请稍候几秒再点")
        try:
            png = _screenshot_png(html, blk)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 chromium 未装/超时等
            raise HTTPException(status_code=503,
                                detail=f"截图失败（{type(e).__name__}: {e}）；部署机需先 playwright install chromium")
        finally:
            _EXPORT_LOCK.release()
        label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        from urllib.parse import quote
        fn = quote(f"甲骨易智能经营罗盘_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
        return Response(content=png, media_type="image/png",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}",
                                 "X-Filename": fn})

    @app.get("/api/history")
    def api_history(request: Request):
        """历史页面快照列表（按天，倒序）。供管理员端「历史快照」页。"""
        _require(request)
        bdir = loaders.data_dir(cfg, root) / "备份"
        out = []
        for p in sorted(bdir.glob("页面_*.html"), reverse=True):
            d = p.stem.split("_")[1]
            out.append({"day": d, "label": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                        "saved_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                        "kb": round(p.stat().st_size / 1024)})
        return out

    @app.get("/api/history/{day}")
    def api_history_page(request: Request, day: str):
        """回看某天的看板页面（当天最后一次更新的原样快照）。"""
        _require(request)
        if not re.fullmatch(r"\d{8}", day):
            raise HTTPException(status_code=400, detail="日期格式须为 YYYYMMDD")
        p = loaders.data_dir(cfg, root) / "备份" / f"页面_{day}.html"
        if not p.exists():
            raise HTTPException(status_code=404, detail="该日无页面快照")
        return HTMLResponse(p.read_text(encoding="utf-8"))

    @app.get("/api/bu_config")
    def api_bu_config_get(request: Request):
        """BU 配置（管理员会话）：BU 清单/负责人/销售名单/分摊比例 + 分摊总开关。"""
        _require(request)
        bucfg = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        return {"bus": bucfg["bus"], "count": len(bucfg["bus"]),
                "公共费用分摊启用": bool(bucfg.get("公共费用分摊启用"))}

    @app.get("/api/sales_pool")
    def api_sales_pool(request: Request):
        """四源销售池（管理员·A1 归属页）：供批量/拖拽归属。含配置里有、库里暂无的名字（rows=0）。
        每人带当年下单笔数+金额参考串（服务端算好=铁律2）；顶层带 A3 未归属计数+当年未归属下单额。"""
        _require(request)
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, root)
        try:
            from_db = db.list_salespeople(conn)
            ostats = db.order_stats_by_sales(conn, today.year)
            snap = core.unassigned_snapshot(cfg, conn, today, root)
        finally:
            conn.close()
        by = {x["name"]: x["rows"] for x in from_db}
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        for b in bucfg.get("bus", []):
            for s in b.get("销售") or []:
                s = str(s).strip()
                if s and s not in by:
                    by[s] = 0

        def _ref(name):
            st = ostats.get(name)
            if not st or not st["count"]:
                return {"orders_count": 0, "ref_disp": "当年无下单"}
            return {"orders_count": st["count"],
                    "ref_disp": f'{st["count"]} 笔 · {core._unassigned_wan(st["amount"])[1:]}'}

        people = [{"name": n, "rows": by[n], **_ref(n)}
                  for n in sorted(by.keys(), key=lambda k: (-by[k], k))]
        return {"sales": people, "count": len(people), **snap}

    @app.post("/api/bu_config")
    def api_bu_config_post(request: Request, payload: dict = Body(default={})):
        """保存 BU 数据归属 + 公共费用分摊，并立即重算重渲染 BU 页（一人一 BU）。C3：变更留痕。"""
        user = _require(request)
        bus = payload.get("bus")
        if not isinstance(bus, list):
            raise HTTPException(status_code=400, detail="bus 须为列表")
        if len(bus) > 20:
            raise HTTPException(status_code=400, detail="BU 数量过多（上限 20）")
        old = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        old_bus, old_alloc = old["bus"], bool(old.get("公共费用分摊启用"))
        new_alloc = bool(payload.get("公共费用分摊启用", False))
        try:
            saved = bu.save_bu_config(cfg, root, bus, 公共费用分摊启用=new_alloc)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        recompute(cfg, root)
        _audit(cfg, root, user, _diff_bu_config(
            old_bus, saved["bus"], old_alloc, bool(saved.get("公共费用分摊启用"))))
        return {"bus": saved["bus"], "count": len(saved["bus"]),
                "公共费用分摊启用": bool(saved.get("公共费用分摊启用")),
                "note": "已保存并重算"}

    @app.get("/api/config_changes")
    def api_config_changes(request: Request, category: str | None = None, limit: int = 200):
        """C3 操作记录（管理员）：配置变更留痕倒序，可按类别筛。仅摘要，无密码明文。"""
        _require(request)
        conn = db.connect(cfg, root)
        try:
            return {"changes": db.list_config_changes(conn, category or None, limit),
                    "categories": list(db.CONFIG_CHANGE_CATEGORIES)}
        finally:
            conn.close()

    @app.get("/api/version")
    def api_version(request: Request):
        """产品版本号 + 面向用户的更新日志（管理员会话）。
        版本号=根目录 VERSION（现 0.9 试运行），与 git 开发号(v8.x)分开、不给普通用户看。"""
        _require(request)
        return product_version.version_info()

    @app.get("/api/update/check")
    def api_update_check(request: Request):
        """④ 检测远端有没有新版本（管理员会话）：git fetch + 比对 HEAD 与 origin/分支。
        只读、带护栏（非仓库/分叉/脏工作区不给更新），返回是否有新版本与"要更新啥"。"""
        _require(request)
        return updater.check_update(loaders.ROOT)

    @app.post("/api/update/apply")
    def api_update_apply(request: Request):
        """④ 一键更新（管理员会话）：复检护栏 → git pull --ff-only → 触发看门狗重启。
        拉取成功才重启（进程以退出码 42 退出，看门狗用新代码拉起）；失败原样返回不重启。"""
        user = _require(request)
        res = updater.apply_update(loaders.ROOT)
        if res.get("ok"):
            _audit(cfg, root, user,
                   ("更新", f"一键更新 {res.get('from') or '?'}→{res.get('to') or '?'}"
                            f"（{res.get('pulled') or 0} 个提交）"))
            updater.request_restart()   # 后台延时退出→看门狗重启；HTTP 响应先发回
            res["restarting"] = True
        return res

    @app.get("/api/settings")
    def api_settings_get(request: Request):
        _require(request)
        out = {k: cfg.get(k) for k in EDITABLE_SETTINGS}
        out["schedule_times"] = get_schedule_times(cfg)  # ②多次更新：列表（缺失从旧单值推导）
        creds = read_zhiyun_creds(cfg, root)
        out["zhiyun_username"], out["zhiyun_password"] = creds["username"], creds["password"]
        bdir = loaders.data_dir(cfg, root) / "备份"
        baks = (sorted(bdir.glob("看板_*.db")) + sorted(bdir.glob("页面_*.html"))) if bdir.exists() else []
        out["backup_stats"] = {"count": len(baks),
                               "mb": round(sum(p.stat().st_size for p in baks) / 1048576, 1)}
        return out

    @app.post("/api/settings")
    def api_settings_post(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        old_times = get_schedule_times(cfg)
        old_keep = cfg.get("backup_keep_days")
        try:
            res = save_settings(cfg, root, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        chg = []  # C3：设置变更留痕（智云账号只记「已更换」不记值）
        if ("schedule_times" in payload or "schedule_time" in payload) \
                and res["schedule_times"] != old_times:
            chg.append(f"更新时间 {'、'.join(old_times) or '—'}→{'、'.join(res['schedule_times'])}")
        if "backup_keep_days" in payload and res["backup_keep_days"] != old_keep:
            chg.append(f"备份保留 {old_keep}→{res['backup_keep_days']} 天")
        if "智云账号已更新" in (res.get("note") or ""):
            chg.append("智云账号已更换")
        if chg:
            _audit(cfg, root, user, ("设置", "设置：" + "；".join(chg)))
        return res

    @app.post("/api/adjust")
    def api_adjust(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        conn = _conn()
        try:
            aid = db.add_adjustment(conn, user, payload.get("目标表", ""),
                                    payload.get("定位键", ""), payload.get("字段", ""),
                                    payload.get("新值", ""), payload.get("原因", ""),
                                    payload.get("类型", "改值"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "adj_id": aid, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/revoke")
    def api_revoke(request: Request, adj_id: int):
        _require(request)
        conn = _conn()
        try:
            ok = db.revoke_adjustment(conn, adj_id)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok" if ok else "noop", "built_at": _state["built_at"]}

    @app.post("/api/adjust/expired/revoke_all")
    def api_revoke_all_expired(request: Request):
        """批量撤销全部「过期疑似」=一键听源头新值。前端走"点按钮→确认保存"两步，这里只管执行。"""
        _require(request)
        conn = _conn()
        try:
            n = db.revoke_expired_adjustments(conn)
        finally:
            conn.close()
        if n:
            recompute(cfg, root)
        return {"status": "ok", "revoked": n, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/rearm")
    def api_rearm(request: Request, adj_id: int):
        """坚持我的数（仅过期疑似、仅逐条）：原值刷新为源头现值→重新生效→立即重算。"""
        _require(request)
        conn = _conn()
        try:
            db.rearm_adjustment(conn, adj_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/adjustments")
    def api_adjustments(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_adjustments(conn)
        finally:
            conn.close()

    @app.get("/api/manual")
    def api_manual_get(request: Request, month: str | None = None):
        _require(request)
        conn = _conn()
        try:
            return db.get_manual(conn, month)
        finally:
            conn.close()

    @app.post("/api/manual")
    def api_manual_set(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        item = payload.get("项目", "")
        if item not in {it["name"] for it in cfg["manual_items"]}:
            raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
        try:
            金额 = float(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字")
        conn = _conn()
        try:
            db.set_manual(conn, payload.get("归属月", ""), item, 金额, user)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/budget")
    def api_budget_get(request: Request, year: str | None = None):
        _require(request)
        conn = _conn()
        try:
            return db.get_budget(conn, year)
        finally:
            conn.close()

    @app.post("/api/budget")
    def api_budget_set(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        metric = payload.get("指标", "")
        if metric not in db.BUDGET_METRICS:
            raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
        year = str(payload.get("年份", "")).strip()
        if not (year.isdigit() and len(year) == 4):
            raise HTTPException(status_code=400, detail="年份须为4位数字")
        try:
            金额 = float(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字")
        scope = str(payload.get("范围", "全公司")).strip() or "全公司"
        if metric == "费用年预算" and scope == "全公司":
            raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
        if metric != "费用年预算" and scope != "全公司":
            raise HTTPException(status_code=400, detail=f"{metric} 只支持全公司口径")
        conn = _conn()
        try:
            db.set_budget(conn, year, metric, 金额, user, 范围=scope)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/budget_depts")
    def api_budget_depts(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_budget_depts(conn)
        finally:
            conn.close()

    @app.get("/api/adjust_fields")
    def api_adjust_fields(request: Request):
        """R1：各明细表可调整字段（schema 黑名单制推导），管理员端字段下拉数据源。"""
        _require(request)
        return db.adjustable_fields()

    return app


def _screenshot_png(html: str, blk: str = "", width: int = 1440) -> bytes:
    """把用户页 HTML 在无头浏览器里渲开并整页截图。blk 非空=先切到该周期视图。
    reduced_motion 关掉全部动效（粒子/扫描线/生长动画），截出来是静止完整帧。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            ctx = br.new_context(viewport={"width": width, "height": 900},
                                 reduced_motion="reduce", device_scale_factor=2)
            pg = ctx.new_page()
            pg.set_content(html, wait_until="load")
            if blk:
                pg.evaluate(
                    "k=>{document.querySelectorAll('.pv').forEach(x=>{"
                    "x.style.display=x.getAttribute('data-blk')===k?'':'none';});"
                    "var b=document.getElementById('periodBtn');"
                    "if(b)b.childNodes[0].textContent=k+' ';}", blk)
            # 截图里去掉纯装饰/交互件（粒子层、导出与主题按钮）
            pg.add_style_tag(content=".particles,#exportBtn,#themeBtn{display:none!important}")
            pg.wait_for_timeout(400)
            return pg.screenshot(full_page=True, type="png")
        finally:
            br.close()


def serve(cfg=None, root=None):
    cfg = cfg or loaders.load_config()
    print("[server] 首次构建页面（跑管道+渲染）……")
    try:
        refresh(cfg, root)
        print(f"[server] 就绪 built_at={_state['built_at']}")
    except Exception as e:  # 数据有问题也让服务起来、页面提示
        print(f"[server] ⚠ 构建失败：{type(e).__name__}: {e}（服务仍启动，修数据后 /api/refresh 或重启）")
    app = create_app(cfg, root)
    import uvicorn
    host = cfg.get("server_host", "0.0.0.0")
    # 环境变量 KANBAN_PORT 可覆盖端口（本机多会话调试时避开 config 固定端口，不影响部署默认值）
    port = int(os.environ.get("KANBAN_PORT") or cfg.get("server_port", 8018))
    print(f"[server] 内网服务：用户端 http://<本机IP>:{port}/   管理员端 http://<本机IP>:{port}/admin")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
