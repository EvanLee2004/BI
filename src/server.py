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
import profit
import ingest
import render
import assets
import version as product_version
import updater
import api_v1

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
    _state["admin_html"] = _admin_page(html, summary, cfg)
    if bu_pages is not None:
        _state["bu_pages"] = bu_pages
    _state["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _apply_profile(html: str, profile: str) -> str:
    """把渲染缓存里默认的 <html … data-profile="full"> 换成本次服务对象的视图档案（Phase 1）。
    executive=姜总精简版（CSS 隐藏公式/解释标注，页面数字不变）；full/空/非法 → 不改（安全默认=完整）。
    纯替换根节点属性一次；'data-profile="full"' 只在 <html> 标签出现，replace(...,1) 命中它。"""
    if not html or profile == accounts.VIEW_FULL or profile not in accounts.VIEW_PROFILES:
        return html
    return html.replace('data-profile="full"', f'data-profile="{profile}"', 1)


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


def read_zhiyun_conn(cfg, root=None) -> dict:
    """读智云连接配置的**生效值**（内置默认 ZHIYUN_DEFAULTS + 本地覆盖合并后）：服务器地址 + 四表ID。"""
    from ingest import fetch_zhiyun
    zy = fetch_zhiyun._load_zhiyun_cfg(cfg, root)
    tables = {s: str(((zy.get("tables") or {}).get(s) or {}).get("worksheetId", ""))
              for s in fetch_zhiyun.SOURCES}
    return {"base_url": zy.get("base_url", ""), "tables": tables}


def save_zhiyun_conn(cfg, root, base_url: str, tables: dict) -> bool:
    """保存界面填的服务器地址/四表ID到 数据/智云配置.json 覆盖层。
    与内置默认相同的项**删除覆盖**（文件保持精简、跟着代码默认走）；不同才写覆盖。
    改了服务器地址顺带清旧会话（token 绑服务器）。返回生效值是否发生变更。"""
    from ingest import fetch_zhiyun
    defaults = fetch_zhiyun.ZHIYUN_DEFAULTS
    before = read_zhiyun_conn(cfg, root)
    base_url = str(base_url or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("智云服务器地址不能为空")
    p = _zhiyun_cfg_file(cfg, root)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if base_url == defaults["base_url"]:
        d.pop("base_url", None)
    else:
        d["base_url"] = base_url
    over = d.get("tables") or {}
    for s in fetch_zhiyun.SOURCES:
        wid = str((tables or {}).get(s) or "").strip()
        if not wid:
            raise ValueError("四张表的表ID都不能为空")
        if wid == defaults["tables"][s]["worksheetId"]:
            if s in over:
                over[s].pop("worksheetId", None)
                if not over[s]:
                    over.pop(s)
        else:
            over.setdefault(s, {})["worksheetId"] = wid
    if over:
        d["tables"] = over
    else:
        d.pop("tables", None)
    if base_url != before["base_url"]:
        d["md_pss_id"] = ""  # 换服务器旧 token 必失效，强制重登
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    after = read_zhiyun_conn(cfg, root)
    return after != before


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
    # 落到机器本地覆盖文件（数据/本地配置.json），**绝不写 config.json** → git 工作区干净 → 一键更新可用。
    updates = {"schedule_time": st, "schedule_times": times,
               "backup_keep_days": keep, "zhiyun_auto_fetch": auto}
    # 收单台账共享盘路径（部署机专属·界面填）：传了才改，一并落覆盖文件
    if "ledger_share_path" in payload:
        lsp = str(payload.get("ledger_share_path") or "").strip()
        cfg["ledger_share_path"] = lsp
        updates["ledger_share_path"] = lsp
    loaders.write_local_config(cfg, root, updates)

    zu, zp = payload.get("zhiyun_username"), payload.get("zhiyun_password")
    cred_note = ""
    if zu is not None and zp is not None:
        zu, zp = str(zu).strip(), str(zp)
        if not zu or not zp:
            raise ValueError("智云账号和密码都不能为空")
        if save_zhiyun_creds(cfg, root, zu, zp):
            cred_note = "；智云账号已更新（下次更新自动用新账号登录）"

    # 智云连接配置（服务器地址/四表ID·内置默认可界面覆盖）：两键都传才处理（界面总是整组提交）
    conn_note = ""
    if "zhiyun_base_url" in payload or "zhiyun_tables" in payload:
        cur = read_zhiyun_conn(cfg, root)
        bu = payload.get("zhiyun_base_url", cur["base_url"])
        tb = dict(cur["tables"])
        for k, v in (payload.get("zhiyun_tables") or {}).items():
            if k in tb:
                tb[k] = v
        if save_zhiyun_conn(cfg, root, bu, tb):
            conn_note = "；智云连接配置已更新（下次更新生效）"

    note = "已保存" + cred_note + conn_note
    # 仅当本次真的提交了更新时间时才动计划任务（各卡就近保存）
    if changed_times:
        import sys
        if sys.platform == "win32":
            note += _win_sync_schedule(times, root)
        else:
            note += f"（本机非 Windows：{len(times)} 个时间点在部署机上生效）"
    return {"schedule_time": st, "schedule_times": times,
            "backup_keep_days": keep, "zhiyun_auto_fetch": auto,
            "ledger_share_path": cfg.get("ledger_share_path", ""), "note": note}


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


def _admin_page(dash_html: str, summary: dict, cfg: dict | None = None) -> str:
    """管理员控制台：体检条 + 立即更新 + 明细编辑/手填/调整台账 标签页 + 内嵌驾驶舱。
    手填项目清单从 config.manual_items 注入（迭代22修硬编码：config 加项后填写页要自动出现）。"""
    import json as _json
    items = [it["name"] for it in (cfg or {}).get("manual_items") or []] or [
        "营销人力成本", "管理人力成本", "研发人力成本", "财务费用补充", "PM人力成本", "VM人力成本",
        "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）", "其他损益"]
    return _ADMIN_CONSOLE.replace("__MANUAL_ITEMS__",
                                  _json.dumps(items, ensure_ascii=False, separators=(",", ":")))


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
<script>try{{if(localStorage.getItem("cockpit-theme")==="light")document.documentElement.classList.add("theme-light")}}catch(e){{}}</script>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--fg:#e2e8f0;--mut:#94a3b8;--line:#334155;--input-bg:#0f172a;--hint:#64748b;--err:#f87171}}
html.theme-light{{--bg:#eef1f5;--card:#fff;--fg:#1d2836;--mut:#525c68;--line:#e3e8ef;--input-bg:#fff;--hint:#64748b;--err:#dc2626}}
body{{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg);
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;position:relative}}
.card{{background:var(--card);padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px rgba(0,0,0,.2);border:1px solid var(--line)}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:var(--mut)}}
input{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid var(--line);background:var(--input-bg);color:var(--fg);font-size:14px}}
button[type=submit]{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:var(--err);font-size:13px;margin-bottom:10px}}
.hint{{color:var(--hint);font-size:12px;margin-top:12px}}
#themeBtn{{position:fixed;top:14px;right:16px;background:transparent;border:1px solid var(--line);color:var(--fg);
padding:6px 12px;border-radius:8px;font-size:13px;cursor:pointer}}
#themeBtn:hover{{border-color:#8b5cf6}}
</style></head>
<body>
<button type="button" id="themeBtn" title="深色/浅色（全局同步）">◑ 浅色</button>
<form class="card" method="post" action="/admin/login">
<h1>管理员端登录</h1>{err}
<label>账号</label><input name="account" value="{account}" autocomplete="username" autofocus>
<label>密码</label><input type="password" name="password" autocomplete="current-password">
<button type="submit">进入</button>
<div class="hint">管理员账号见「看板账号」表（默认 lushasha）。</div></form>
<script>
(function(){{var r=document.documentElement,b=document.getElementById("themeBtn");
function setL(l){{r.classList.toggle("theme-light",!!l);if(b)b.textContent=l?"◐ 深色":"◑ 浅色";}}
try{{setL(localStorage.getItem("cockpit-theme")==="light");}}catch(e){{}}
if(b)b.onclick=function(){{var l=!r.classList.contains("theme-light");try{{localStorage.setItem("cockpit-theme",l?"light":"dark");}}catch(e){{}}setL(l);}};
window.addEventListener("storage",function(e){{if(e.key==="cockpit-theme")setL(e.newValue==="light");}});}})();
</script></body></html>"""


# 首次部署引导页（2026-07-14 部署日踩坑 F-02 修复）：admin_html 只在首次取数成功后生成，
# 而填智云账号的设置页又长在 admin_html 里——空机器登录管理端只见"数据尚未生成"，鸡生蛋死循环。
# 此页自包含（不依赖任何已生成数据）：填智云账号(+可改台账路径)→保存→立即更新→轮询→成功自动进完整管理端。
_BOOTSTRAP_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>首次取数 · 甲骨易智能经营罗盘</title>
<style>
body{margin:0;background:#0b1020;color:#dbe4ff;font:14px/1.7 -apple-system,"Microsoft YaHei",sans-serif;
display:flex;justify-content:center;padding:48px 16px}
.card{width:100%;max-width:460px;background:#121a33;border:1px solid #26314f;border-radius:14px;padding:28px}
h1{font-size:18px;margin:0 0 6px}.sub{color:#8fa1c7;font-size:12.5px;margin:0 0 18px}
label{display:block;font-size:12px;color:#8fa1c7;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;background:#0b1020;border:1px solid #2c3a5e;border-radius:8px;
color:#dbe4ff;padding:9px 10px;font-size:14px}
button{margin-top:18px;width:100%;padding:11px;border:0;border-radius:8px;background:#22d3ee;color:#08111f;
font-weight:700;font-size:14px;cursor:pointer}button:disabled{opacity:.5;cursor:default}
.msg{margin-top:12px;font-size:12.5px;color:#8fa1c7;min-height:20px;white-space:pre-wrap}
.msg.err{color:#f87171}.msg.ok{color:#34d399}</style></head><body><div class="card">
<h1>系统已装好，还差第一次取数</h1>
<p class="sub">填入智云账号后点下方按钮，系统自动抓数并生成看板（约 2~3 分钟）；完成后本页自动进入完整管理端。台账路径与四张表地址已内置默认，一般不用改。</p>
<label>智云账号</label><input id="u" autocomplete="off">
<label>智云密码</label><input id="p" type="password" autocomplete="off">
<label>收单台账共享盘路径（已预填默认，共享盘没搬家就别动）</label><input id="lp" autocomplete="off" spellcheck="false">
<button id="go" onclick="go()">保存并开始首次取数</button>
<div class="msg" id="m"></div></div>
<script>
async function jj(url,opt){const r=await fetch(url,opt);if(!r.ok&&r.status!==409)throw new Error((await r.json().catch(()=>({}))).detail||("HTTP "+r.status));return r.json().catch(()=>({}));}
jj("/api/settings").then(s=>{document.getElementById("u").value=s.zhiyun_username||"";
  document.getElementById("p").value=s.zhiyun_password||"";
  document.getElementById("lp").value=s.ledger_share_path||"";}).catch(()=>{});
let t0=0;
async function go(){const m=document.getElementById("m"),b=document.getElementById("go");
  const u=document.getElementById("u").value.trim(),p=document.getElementById("p").value;
  m.className="msg";
  if(!u||!p){m.className="msg err";m.textContent="智云账号和密码都要填";return;}
  b.disabled=true;m.textContent="保存配置…";
  try{const pay={zhiyun_username:u,zhiyun_password:p};
    const lp=document.getElementById("lp").value.trim();if(lp)pay.ledger_share_path=lp;
    await jj("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(pay)});
  }catch(e){m.className="msg err";m.textContent="保存失败："+e.message;b.disabled=false;return;}
  m.textContent="开始取数…（智云在线抓约 80 秒 + 计算约 1 分钟）";t0=Date.now();
  try{await jj("/api/refresh",{method:"POST"});}catch(e){}
  poll();}
async function poll(){const m=document.getElementById("m"),b=document.getElementById("go");
  try{const s=await jj("/api/refresh_status");
    if(s.running){m.textContent="取数中… 已 "+Math.round((Date.now()-t0)/1000)+" 秒（在线抓+32 周期计算，请勿关页）";setTimeout(poll,3000);return;}
    const last=s.last||{};
    if(last.status==="ok"){m.className="msg ok";m.textContent="✓ 完成，正在进入管理端…";setTimeout(()=>location.reload(),1200);return;}
    m.className="msg err";b.disabled=false;
    m.textContent="取数失败："+(last.detail||last.error||"未知原因")+"\\n检查账号密码后可重试；反复失败联系明昊。";
  }catch(e){setTimeout(poll,3000);}}
</script></body></html>"""


def _bootstrap_page() -> str:
    return _BOOTSTRAP_HTML


def _login_page(err: str = "", account: str = "") -> str:
    err_html = f'<div class="err">{err}</div>' if err else ""
    acct = str(account or DEFAULT_ADMIN_ACCOUNT).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return _LOGIN_HTML.format(err=err_html, account=acct)


# 查看端登录页（v8.0）：账号+密码，按权限分流（管理员→/admin、整体→整体页、BU→本 BU 页）。
_VIEW_LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>看板登录 · 甲骨易智能经营罗盘</title>
<script>try{{if(localStorage.getItem("cockpit-theme")==="light")document.documentElement.classList.add("theme-light")}}catch(e){{}}</script>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--fg:#e2e8f0;--mut:#94a3b8;--line:#334155;--input-bg:#0f172a;--hint:#64748b;--err:#f87171}}
html.theme-light{{--bg:#eef1f5;--card:#fff;--fg:#1d2836;--mut:#525c68;--line:#e3e8ef;--input-bg:#fff;--hint:#64748b;--err:#dc2626}}
body{{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg);
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;position:relative}}
.card{{background:var(--card);padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px rgba(0,0,0,.2);border:1px solid var(--line)}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:var(--mut)}}
input{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid var(--line);background:var(--input-bg);color:var(--fg);font-size:14px}}
button[type=submit]{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:var(--err);font-size:13px;margin-bottom:10px}}
.hint{{color:var(--hint);font-size:12px;margin-top:12px}}
#themeBtn{{position:fixed;top:14px;right:16px;background:transparent;border:1px solid var(--line);color:var(--fg);
padding:6px 12px;border-radius:8px;font-size:13px;cursor:pointer}}
#themeBtn:hover{{border-color:#8b5cf6}}
</style></head>
<body>
<button type="button" id="themeBtn" title="深色/浅色（全局同步）">◑ 浅色</button>
<form class="card" method="post" action="/login">
<h1>看板登录</h1>{err}
<label>账号</label><input name="account" value="{account}" autocomplete="username" autofocus>
<label>密码</label><input type="password" name="password" autocomplete="current-password">
<button type="submit">进入</button>
<div class="hint">账号密码问财务部管理员要；登录后可自己改密码。忘记密码找管理员重置。</div></form>
<script>
(function(){{var r=document.documentElement,b=document.getElementById("themeBtn");
function setL(l){{r.classList.toggle("theme-light",!!l);if(b)b.textContent=l?"◐ 深色":"◑ 浅色";}}
try{{setL(localStorage.getItem("cockpit-theme")==="light");}}catch(e){{}}
if(b)b.onclick=function(){{var l=!r.classList.contains("theme-light");try{{localStorage.setItem("cockpit-theme",l?"light":"dark");}}catch(e){{}}setL(l);}};
window.addEventListener("storage",function(e){{if(e.key==="cockpit-theme")setL(e.newValue==="light");}});}})();
</script></body></html>"""


def _view_login_page(err: str = "", account: str = "") -> str:
    err_html = f'<div class="err">{err}</div>' if err else ""
    acct = str(account).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return _VIEW_LOGIN_HTML.format(err=err_html, account=acct)


_ADMIN_CONSOLE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理员控制台 · 甲骨易智能经营罗盘</title>
<script>try{if(localStorage.getItem("cockpit-theme")==="light")document.documentElement.classList.add("theme-light")}catch(e){}</script>
<style>
:root{--bg:#0b1220;--panel:#151e30;--panel2:#1a2438;--line:#2a364d;--fg:#e8eef9;--mut:#8b9bb4;--vio:#8b5cf6;--vio2:#a78bfa;
--input-bg:#0c1424;--th-bg:#0f172a;--bar-bg:rgba(21,30,48,.92);--subnav-bg:rgba(15,22,36,.65);--tbl-bg:#0c1424;
--hover-row:rgba(26,36,56,.4);--note-fg:#cbd5e1;--muted2:#94a3b8;--shadow:rgba(0,0,0,.35)}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,"PingFang SC","Segoe UI",sans-serif;
background:radial-gradient(1200px 600px at 10% -10%,#1a1040 0%,transparent 55%),
radial-gradient(900px 500px at 100% 0%,#0c2a3a 0%,transparent 50%),var(--bg);color:var(--fg);min-height:100vh}
#bar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
padding:10px 16px;background:var(--bar-bg);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
#bar b{font-size:15px;letter-spacing:.2px}.pill{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;user-select:none}
.g{background:#14532d;color:#86efac}.y{background:#713f12;color:#fde68a}.r{background:#7f1d1d;color:#fca5a5}
button{background:linear-gradient(180deg,#9b6dff,#7c3aed);color:#fff;border:0;border-radius:9px;padding:7px 14px;font-size:13px;cursor:pointer;
box-shadow:0 2px 10px #7c3aed44;font-weight:600}
button:hover{filter:brightness(1.06)}button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg);box-shadow:none}
button.mini{padding:5px 10px;font-size:12px;border-radius:8px}button:disabled{opacity:.5;cursor:wait;filter:none}
button#themeBtn{background:transparent;border:1px solid var(--line);color:var(--fg);box-shadow:none;font-weight:600;padding:6px 12px}
button#themeBtn:hover{border-color:var(--vio);color:var(--vio2)}
a{color:var(--vio2)}a.logout{color:var(--mut);text-decoration:none;font-size:13px;padding:6px 10px;border-radius:8px}
a.logout:hover{background:var(--panel2);color:var(--fg)}
#groups{display:flex;gap:4px;flex-wrap:wrap;padding:10px 16px 0;background:transparent}
.gtab{padding:9px 18px;border-radius:10px 10px 0 0;cursor:pointer;font-size:14px;font-weight:600;color:var(--mut);
border:1px solid transparent;border-bottom:none;transition:.15s}
.gtab:hover{color:var(--fg)}.gtab.on{background:var(--bg);color:var(--fg);border-color:var(--line);box-shadow:0 -2px 12px rgba(0,0,0,.2)}
#subnav{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:10px 16px;background:var(--subnav-bg);border-bottom:1px solid var(--line);min-height:0}
.subgrp{display:none;gap:6px;align-items:center;flex-wrap:wrap}
.stab{background:transparent;border:1px solid var(--line);color:var(--mut);padding:6px 14px;border-radius:999px;font-size:13px;cursor:pointer;transition:.12s}
.stab:hover{color:var(--fg);border-color:#475569}.stab.on{background:var(--vio);color:#fff;border-color:var(--vio);box-shadow:0 2px 8px #8b5cf644}
.subsep{width:1px;height:18px;background:var(--line);margin:0 4px}
.subgrp .badge{background:#7f1d1d;color:#fca5a5;border-radius:20px;padding:0 6px;font-size:11px;margin-left:5px}
.subgrp .badge.zero{background:#14532d;color:#86efac}
/* 各页铺满视口宽度（原 max-width:1280 宽屏右侧大片空白） */
.sec{display:none;padding:18px 20px 28px;width:100%;max-width:none;box-sizing:border-box}.sec.on{display:block}
#dash.sec,#history.sec{padding:10px 12px 14px}
input,select{background:var(--input-bg);border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:8px 10px;font-size:13px}
input:focus,select:focus{outline:none;border-color:var(--vio);box-shadow:0 0 0 3px #8b5cf633}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:0}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;white-space:nowrap}
th{background:var(--th-bg);position:sticky;top:0;z-index:1;color:var(--mut);font-size:11.5px;font-weight:700;letter-spacing:.02em}
tr.exp{background:#3b1d1d}tr.init-pw td{background:#3b2f0e88 !important}
.wrap{overflow:auto;max-height:calc(100vh - 200px)}
.row-form{margin:6px 0;padding:10px 12px;background:var(--panel2);border-radius:10px;border:1px solid var(--line)}
.muted{color:var(--muted2);font-size:13px}
iframe{width:100%;height:calc(100vh - 128px);min-height:520px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 8px 28px var(--shadow);display:block}
.note{color:var(--note-fg);font-size:13.5px;margin:8px 0;line-height:1.6}
.note.info{border-left:3px solid var(--vio);padding:12px 16px;border-radius:0 10px 10px 0;background:var(--panel2);margin:0 0 12px;color:var(--fg);font-size:13.5px}
.scard-h .sub{font-size:13px!important;color:var(--muted2)!important}
#hDetail{display:none;position:absolute;top:52px;left:14px;z-index:30;max-width:560px;background:var(--panel);
border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:12px;line-height:1.6;box-shadow:0 12px 36px var(--shadow)}
#hDetail h4{margin:0 0 4px;font-size:13px}#hDetail .grp{margin-top:10px}
#hDetail .k{color:var(--mut);font-weight:600;margin-bottom:2px}
#hDetail ul{margin:3px 0 0;padding-left:18px}#hDetail .ok{color:#16a34a}
#toast{display:none;position:fixed;top:56px;right:18px;z-index:50;background:#14532d;color:#bbf7d0;
padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600;box-shadow:0 8px 24px var(--shadow);max-width:360px}
#toast.err{background:#7f1d1d;color:#fecaca}
#toast.warn{background:#78350f;color:#fde68a}
#toast.clickable{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
.scard{background:var(--panel);
border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 10px 28px var(--shadow)}
.scard-h{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line);
background:var(--panel2)}
.scard-h .ico{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;flex-shrink:0;
background:linear-gradient(145deg,#8b5cf633,#6366f122);border:1px solid #8b5cf644;font-size:17px}
.scard-h .ttl{font-size:15px;font-weight:700;letter-spacing:.2px}
.scard-h .sub{font-size:12px;color:var(--mut);margin-top:3px;line-height:1.45}
.scard-b{padding:16px}.scard-f{padding:12px 16px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;align-items:center;
background:var(--subnav-bg)}
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
.tbl-box{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--tbl-bg)}
.tbl-box.sm{max-height:42vh}.tbl-box.lg{max-height:calc(100vh - 240px)}
/* 人工填写/业绩目标：整页展示，不在表内再套一层滚动 */
.tbl-box.no-scroll{max-height:none!important;overflow:visible}
.tbl-box table{margin:0}.tbl-box th{border-bottom:1px solid var(--line)}
.tbl-box tr:hover td{background:var(--hover-row)}
.tbl-box input,.tbl-box select{border-radius:7px;padding:6px 8px;font-size:12.5px}
.tbl-box tr.dirty td{background:rgba(139,92,246,.08)}
.pct-suffix{color:var(--muted2);font-size:12.5px;margin-left:4px;font-weight:600}
/* 底部批量保存条 */
.save-bar{position:sticky;bottom:0;z-index:20;display:none;align-items:center;gap:12px;flex-wrap:wrap;
  margin-top:16px;padding:12px 16px;border-radius:12px;border:1px solid #8b5cf666;
  background:var(--panel2);box-shadow:0 -8px 28px var(--shadow)}
.save-bar.on{display:flex}
.save-bar .sb-n{font-size:13.5px;color:var(--fg);font-weight:600;flex:1;min-width:160px}
.save-bar .sb-n b{color:var(--vio2)}
.save-bar button.primary{background:var(--vio);color:#fff;font-weight:700;padding:9px 18px;font-size:14px}
.save-bar button.ghost{opacity:.9}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 14px;margin-bottom:12px;
border-radius:12px;background:var(--panel);border:1px solid var(--line);box-shadow:0 4px 16px var(--shadow)}
.toolbar .grow{flex:1;min-width:8px}
.sec-block{margin-top:18px}
.sec-block .blk-h{font-size:14px;font-weight:700;margin:0 0 8px;display:flex;align-items:center;gap:8px}
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;width:100%;max-width:none}
.ovcard{border-radius:14px !important;transition:transform .15s,box-shadow .15s;box-shadow:0 6px 18px var(--shadow)}
.ovcard:hover{transform:translateY(-2px);box-shadow:0 12px 28px var(--shadow)}
#dash .note{margin-top:10px}
/* BU 销售拖拽归属 */
.bu-board{display:flex;flex-direction:column;gap:12px}
.bu-pool{border:1px dashed var(--line);border-radius:12px;padding:10px 12px;background:var(--tbl-bg)}
.bu-pool-h,.bu-col-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.bu-pool-h b,.bu-col-title{font-size:13px;font-weight:700}
.bu-pool-h .hint{font-size:11.5px;color:var(--mut)}
.bu-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.bu-col{border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--tbl-bg);min-height:140px;
display:flex;flex-direction:column;gap:8px}
.bu-col.drag-over{border-color:var(--vio);box-shadow:0 0 0 2px #8b5cf644}
.bu-col-meta{display:flex;flex-direction:column;gap:6px}
.bu-col-meta input{width:100%}
.bu-chips{display:flex;flex-wrap:wrap;gap:6px;min-height:44px;padding:8px;border-radius:10px;
background:var(--panel2);border:1px solid var(--line);flex:1;align-content:flex-start}
.bu-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;
background:var(--panel);border:1px solid var(--line);color:var(--fg);
font-size:12px;font-weight:600;cursor:grab;user-select:none;max-width:100%}
.bu-chip:active{cursor:grabbing}.bu-chip.dragging{opacity:.45}
.bu-chip .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px}
.bu-chip .c{font-size:10.5px;color:var(--mut);font-weight:500}
.bu-chip .x{border:0;background:transparent;color:var(--muted2);cursor:pointer;padding:0 2px;font-size:14px;line-height:1;box-shadow:none}
.bu-chip .x:hover{color:#f87171}
.bu-empty{font-size:11.5px;color:var(--mut);padding:4px 2px;width:100%}
.bu-chip .bu-cb{margin:0 2px 0 0;cursor:pointer;accent-color:var(--vio)}
.bu-batch{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:9px 12px;margin:0 0 12px;
  border-radius:10px;background:var(--panel2);border:1px solid var(--vio);font-size:13px}
.bu-batch select{min-width:150px}
#buUnassignedHint b{color:#d97706}
.acct-bus{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px;max-width:280px}
.acct-bu{display:inline-flex;align-items:center;gap:3px;font-size:11.5px;color:var(--fg);cursor:pointer;white-space:nowrap}
.acct-bu input{margin:0;accent-color:var(--vio);cursor:pointer}
.sched-times{display:flex;flex-wrap:wrap;gap:8px}
.sched-row{display:inline-flex;align-items:center;gap:4px}
.sched-row input[type=time]{font-size:15px;padding:7px 10px}
.sched-row .mini{padding:4px 8px;font-size:12px}
.ver-pill{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700;cursor:pointer;user-select:none;
  background:var(--panel2);color:var(--vio2);border:1px solid var(--vio)}
.ver-pill:hover{filter:brightness(1.06)}
/* 版本卡：默认只显示摘要；更新日志走右侧抽屉 */
#verCard .ver-now{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px}
#verCard .ver-now .num{font-size:26px;font-weight:800;letter-spacing:.5px;color:var(--vio2)}
#verCard .ver-now .stage{font-size:12.5px;font-weight:700;padding:2px 9px;border-radius:999px;
  background:#3b2f0e;color:#fde68a}
#verCard .ver-now .stage.live{background:#14532d;color:#86efac}
#verCard .ver-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px}
#verLog{display:flex;flex-direction:column;gap:12px;padding-right:2px}
#verLog .vl{border:1px solid var(--line);border-radius:10px;padding:11px 13px;background:var(--tbl-bg)}
#verLog .vl-h{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:7px}
#verLog .vl-h .t{font-size:13.5px;font-weight:700}
#verLog .vl-h .d{font-size:11.5px;color:var(--mut)}
#verLog ul{margin:0;padding-left:18px}#verLog li{font-size:12.5px;line-height:1.6;margin:3px 0;color:var(--note-fg)}
.vu-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
#vuAvail{margin-top:10px}
.vu-avail{border:1px solid var(--vio);border-radius:10px;padding:11px 13px;background:var(--panel2)}
.vu-h{font-size:13px;font-weight:700;margin-bottom:6px}
.vu-sub{font-size:12px;color:var(--mut)}
.vu-log{margin:4px 0 10px;padding-left:18px}.vu-log li{font-size:12px;color:var(--note-fg);margin:2px 0}
/* 版本日志右侧抽屉（默认折叠；点开从右滑入） */
.ver-drawer{position:fixed;inset:0;z-index:90;visibility:hidden;pointer-events:none}
.ver-drawer.open{visibility:visible;pointer-events:auto}
.ver-drawer-mask{position:absolute;inset:0;background:rgba(4,8,20,.55);opacity:0;transition:opacity .25s;
  -webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.ver-drawer.open .ver-drawer-mask{opacity:1}
.ver-drawer-panel{position:absolute;top:0;right:0;height:100%;width:min(420px,92vw);
  background:var(--tbl-bg);border-left:1px solid var(--line);box-shadow:-14px 0 44px var(--shadow);
  transform:translateX(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column}
.ver-drawer.open .ver-drawer-panel{transform:none}
.ver-drawer-h{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;
  border-bottom:1px solid var(--line);flex:0 0 auto}
.ver-drawer-h span{font-size:15px;font-weight:700;color:var(--fg)}
.ver-drawer-x{cursor:pointer;background:none;border:0;color:var(--mut);font-size:24px;line-height:1;padding:0 6px;font-family:inherit}
.ver-drawer-x:hover{color:var(--fg)}
.ver-drawer-body{padding:12px 16px 28px;overflow-y:auto;flex:1 1 auto}
.ver-drawer-body .ver-sub{font-size:12px;color:var(--mut);margin-bottom:12px;line-height:1.5}

/* —— 亮色主题（与驾驶舱共用 localStorage cockpit-theme）—— */
html.theme-light{
  --bg:#eef1f5;--panel:#ffffff;--panel2:#f8fafc;--line:#e3e8ef;--fg:#1d2836;--mut:#525c68;
  --vio:#7c5cbf;--vio2:#6d4fa8;--input-bg:#ffffff;--th-bg:#f1f5f9;--bar-bg:rgba(255,255,255,.94);
  --subnav-bg:#f1f5f9;--tbl-bg:#ffffff;--hover-row:#f1f5f9;--note-fg:#3d4756;--muted2:#64748b;
  --shadow:rgba(31,58,95,.1)}
html.theme-light body{background:var(--bg);color:var(--fg)}
html.theme-light .g{background:#dcfce7;color:#166534}
html.theme-light .y{background:#fef3c7;color:#92400e}
html.theme-light .r{background:#fee2e2;color:#991b1b}
html.theme-light tr.exp{background:#fee2e2}
html.theme-light tr.init-pw td{background:#fef3c788 !important}
html.theme-light #verCard .ver-now .stage{background:#fef3c7;color:#92400e}
html.theme-light #verCard .ver-now .stage.live{background:#dcfce7;color:#166534}
html.theme-light .ver-drawer-mask{background:rgba(15,23,42,.35)}
html.theme-light .scard-h .ico{background:linear-gradient(145deg,rgba(124,92,191,.12),rgba(99,102,241,.06));border-color:rgba(124,92,191,.25)}
html.theme-light button{box-shadow:0 2px 8px rgba(124,92,191,.25)}
html.theme-light button.ghost,html.theme-light button#themeBtn{box-shadow:none}
html.theme-light .gtab.on{box-shadow:0 -1px 8px rgba(31,58,95,.06)}
html.theme-light .subgrp .badge{background:#fee2e2;color:#991b1b}
html.theme-light .subgrp .badge.zero{background:#dcfce7;color:#166534}
html.theme-light #buUnassignedHint b{color:#b45309}
html.theme-light .stab:hover{border-color:#94a3b8}
</style></head><body>
<div id="bar">
  <b>管理员控制台</b>
  <span id="verPill" class="ver-pill" title="产品版本号（点开看更新日志）" onclick="showGroup('cfg');setTimeout(openVerDrawer,80)">v…</span>
  <span id="health" class="pill y" onclick="toggleHealth()" title="点开看体检明细">体检…</span>
  <button id="btnRefresh" onclick="doRefresh()" title="从智云/台账重新抓数并重算看板">更新数据</button>
  <span id="msg" class="muted"></span>
  <span style="margin-left:auto"></span>
  <button type="button" class="ghost" id="profBtn" title="预览下方看板：完整（你/陆总看的）↔ 精简（姜总看的，隐藏公式与解释标注）">👁 完整视图</button>
  <button type="button" class="ghost" id="themeBtn" title="深色/浅色（与看板共用，全局同步）"><span>◑</span> 浅色</button>
  <a class="logout" href="/admin/logout">退出</a>
</div>
<div id="toast"></div>
<div id="hDetail"></div>
<div id="groups">
  <div class="gtab on" data-g="see" onclick="showGroup('see')">看</div>
  <div class="gtab" data-g="edit" onclick="showGroup('edit')">数据调整</div>
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
    <button class="stab" data-t="人工填写" onclick="showManual()">人工填写</button>
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
    <span class="field-inline">搜索 <input id="dQ" placeholder="订单号/定位键/客户…" size="18"></span>
    <button onclick="dQuery()">查询</button>
    <button class="mini ghost" type="button" onclick="exportDetail()" title="导出当前表+筛选结果为 Excel">导出 Excel</button>
    <span id="dInfo" class="muted grow"></span>
  </div>
  <div class="note info">改数=写一条调整记录（重抓不丢）；剔除=软删（可在「数据修正」撤销）。滚动到底自动加载更多。搜索支持订单号、定位键、客户等。</div>
  <div id="editDock" class="row-form" style="display:none"></div>
  <div class="tbl-box lg wrap" id="dWrap"><table id="dTbl"></table></div>
</div>

<div id="manual" class="sec">
  <div class="toolbar">
    <span class="field-inline">月份 <select id="mY"></select><select id="mM"></select></span>
    <span class="field-inline">范围 <select id="mScope"><option value="全公司">全公司</option></select></span>
    <button onclick="mLoadSafe()">查询</button>
    <span class="muted grow">可改多格后底部一键保存。金额填<strong>元</strong>（千分位）；当月未填=0（不再沿用上月）。全公司与各 BU 手填分开存。</span>
  </div>
  <div class="note info">人工填写：人力/补充等。选「范围」可按全公司或某个业务 BU 填。可批量改数，离开会提醒。业绩目标金额请填<strong>万元</strong>。</div>
  <div class="tbl-box no-scroll"><table id="mTbl"></table></div>
  <div class="sec-block" id="allocBlock" style="display:none">
    <div class="blk-h">🏦 公共费用分摊比例（按月）</div>
    <div class="note info">本月公共费用总额 <strong id="allocTotal">—</strong> 元（台账「利润归属中心=公共」5 类合计）。
      各 BU 填比例 %；<b>合计可以小于 100%</b>（剩余留公司层不分摊）、超过 100% 不能保存；
      <b>没填的月份自动沿用最近一次填写的比例</b>（改了从当月起生效）；要让某 BU 当月不分摊请填 <b>0</b>。
      BU 名单与「设置→BU 数据归属」同源。与上方共用底部「保存全部」。</div>
    <div class="muted" id="allocInherit" style="margin:4px 0 0"></div>
    <div class="tbl-box no-scroll"><table id="aTbl"></table></div>
    <div class="muted" id="allocSum" style="margin-top:6px"></div>
  </div>
  <div class="sec-block" id="detaxBlock" style="display:none">
    <div class="blk-h">💧 费用去税率（按类别·全公司）</div>
    <div class="note info">台账费用多为<b>含税</b>金额。能抵扣进项的费用（<b>主要是房租/物业</b>）可填增值税率 %，
      看板把它按「<b>不含税额 = 含税额 ÷ (1 + 税率%)</b>」还原成真实费用；<b>大部分费用抵不了税（业务招待、水电等）留空即可</b>。
      <b>默认全空 = 不去税，页面数字一分不变</b>；类别按全年金额从大到小排（大头在前，按重要性挑填）。全公司一套、常年沿用。与上方共用底部「保存全部」。</div>
    <div class="tbl-box no-scroll"><table id="dxTbl"></table></div>
  </div>
  <div class="sec-block">
    <div class="blk-h">🎯 业绩目标（优先）</div>
    <div class="note info">下单 / 回款目标填<strong>万元</strong>（如 8000 = 8000 万）；毛利率填百分数（35 = 35%）。<b>跟随顶部「月份」的年份与「范围」</b>（全公司 / 某 BU）。与上方共用底部「保存全部」。</div>
    <div class="tbl-box no-scroll"><table id="bTbl"></table></div>
  </div>
  <div id="saveBar" class="save-bar">
    <span class="sb-n">有 <b id="dirtyCount">0</b> 项未保存</span>
    <button type="button" class="ghost" onclick="discardDirty()">放弃更改</button>
    <button type="button" class="primary" id="btnBatchSave" onclick="batchSaveAll()">保存全部更改</button>
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
      <div class="scard-h"><span class="ico">🧭</span><div><div class="ttl">版本与更新</div>
        <div class="sub">默认只显示当前版本；点「更新日志」在右侧看明细。检查更新 / 一键更新在此完成。</div></div></div>
      <div class="scard-b">
        <div class="ver-now"><span class="num" id="verNum">v…</span>
          <span class="stage" id="verStage">…</span>
          <span class="muted" style="font-size:12px" id="verNext"></span></div>
        <div class="ver-actions">
          <button class="mini" type="button" onclick="checkUpdate()">检查更新</button>
          <button class="mini ghost" type="button" onclick="openVerDrawer()">更新日志 ›</button>
          <span id="vuMsg" class="muted"></span>
        </div>
        <div class="muted" style="font-size:11.5px;margin-top:8px">从代码仓库检测新版本；有则可「一键更新」（快进拉取 + 看门狗重启）。部署机用 <b>看门狗启动.bat</b> 起服务才会自动重启。</div>
        <div id="vuAvail" style="display:none"></div>
      </div>
    </div>

    <div class="scard" id="setCardSched">
      <div class="scard-h"><span class="ico">⏰</span><div><div class="ttl">自动更新</div>
        <div class="sub">每天自动跑完整更新（抓数→重算→出页面）；可设多个时间点，各到点各更新一次</div></div></div>
      <div class="scard-b">
        <div class="field"><label>每日更新时间点（可多个）</label>
          <div id="schedTimes" class="sched-times"></div>
          <button class="ghost mini" type="button" onclick="schedAdd()" style="margin-top:8px">＋ 添加时间点</button></div>
        <div class="muted">如 09:30 / 12:00 / 17:30，各到点各跑一次。Windows 每个时间点建一个计划任务；<b>首次或增删时间点若没生效，以管理员身份跑一次 注册每日更新.bat</b>。平时可点顶栏「更新数据」。</div>
      </div>
      <div class="scard-f"><span id="sTimeMsg" class="muted"></span></div>
    </div>

    <div class="scard" id="setCardBackup">
      <div class="scard-h"><span class="ico">🗄</span><div><div class="ttl">备份清理</div>
        <div class="sub">每次更新备份 看板.db 到 数据/备份/（每天一份）</div></div></div>
      <div class="scard-b">
        <div class="field row"><label>备份保留</label>
          <input id="sKeep" type="number" min="1" max="365" style="width:88px;font-size:15px"><span class="muted">天</span></div>
        <div class="muted">超过天数自动删最旧；月末快照存档永久保留。</div>
        <div id="sBakInfo" class="muted" style="margin-top:8px"></div>
      </div>
      <div class="scard-f"><span id="sBakMsg" class="muted"></span></div>
    </div>

    <div class="scard" id="setCardZy">
      <div class="scard-h"><span class="ico">🔑</span><div><div class="ttl">智云账号 · 台账路径</div>
        <div class="sub">本机专属连接设置；只存本机（不进代码库），换号/换路径下次「更新数据」生效</div></div></div>
      <div class="scard-b">
        <div class="field"><label>智云账号</label>
          <input id="sZyUser" type="password" autocomplete="off" style="width:100%;max-width:280px"></div>
        <div class="field"><label>智云密码</label>
          <div class="field-inline">
            <input id="sZyPwd" type="password" autocomplete="off" style="width:100%;max-width:280px">
            <button class="ghost mini" type="button" onclick="toggleZyReveal()" id="sZyEye">👁 显示</button>
          </div></div>
        <div class="field"><label>收单台账共享盘路径</label>
          <input id="sLedgerPath" type="text" autocomplete="off" spellcheck="false"
                 placeholder="\\\\服务器\\财务部\\...\\收单台账.xlsx" style="width:100%;max-width:420px">
          <div class="muted" style="font-size:11px;margin-top:3px">部署机填真实共享盘路径；只存本机 `数据\\本地配置.json`，config.json 不动（这样一键更新才不会被"工作区脏"卡住）。留空=沿用默认/本地副本。</div>
        </div>
        <details id="sZyConnBox" style="margin-top:6px">
          <summary class="muted" style="cursor:pointer;font-size:12px">智云服务器与抓取表（默认已内置，一般不用改）</summary>
          <div class="field" style="margin-top:8px"><label>智云服务器地址</label>
            <input id="sZyUrl" type="text" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px"></div>
          <div class="field"><label>下单 表ID</label>
            <input id="sTblOrders" type="text" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px"></div>
          <div class="field"><label>回款记录 表ID</label>
            <input id="sTblReceipts" type="text" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px"></div>
          <div class="field"><label>项目明细 表ID</label>
            <input id="sTblProject" type="text" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px"></div>
          <div class="field"><label>内部译员（任务表）表ID</label>
            <input id="sTblInhouse" type="text" autocomplete="off" spellcheck="false" style="width:100%;max-width:420px"></div>
          <div class="muted" style="font-size:11px;margin-top:3px">四张表地址随程序内置、开箱即用；智云换服务器/换表才需要改。改动只存本机 `数据\\智云配置.json`。</div>
        </details>
      </div>
      <div class="scard-f"><span id="sZyMsg" class="muted"></span></div>
    </div>

    <div class="scard" id="setCardAcct">
      <div class="scard-h"><span class="ico">👥</span><div><div class="ttl">账号与权限</div>
        <div class="sub"><b>显示名</b>=备注（谁用这个号，只给人看）。<b>权限</b>：管理员 / 整体（看全公司+全部 BU）/ 按 BU（勾选一组 BU，只看这几块，可多选）。密码明文仅此处可见（点👁）。黄底=初始密码。<b>总账号</b>（lushasha）固定管理员、不可删；另可再加其他管理员。</div></div></div>
      <div class="scard-b">
        <div class="tbl-box sm wrap" style="max-height:min(42vh,360px)"><table id="acctTbl"></table></div>
      </div>
      <div class="scard-f">
        <button class="ghost mini" type="button" onclick="acctAdd()">＋ 加账号</button>
        <span id="acctMsg" class="muted"></span>
      </div>
    </div>

    <div class="scard full" id="setCardBu">
      <div class="scard-h"><span class="ico">🏢</span><div><div class="ttl">BU 数据归属（销售归属）</div>
        <div class="sub">销售归到哪个 BU=该人口径进那张 BU 利润表（一人一 BU）。<b>勾选多人→选 BU→批量指定</b>，或直接拖动；改完点底部「保存全部设置」即重算。与登录账号无关。未归属不进任何 BU 子页。没配 BU=分页关闭。</div></div></div>
      <div class="scard-b">
        <div id="buUnassignedHint" class="note" style="display:none;border-left:3px solid #f59e0b;padding:8px 12px;border-radius:0 8px 8px 0;background:var(--panel2);margin:0 0 12px"></div>
        <div id="buUnknownPcHint" class="note" style="display:none;border-left:3px solid #f59e0b;padding:8px 12px;border-radius:0 8px 8px 0;background:var(--panel2);margin:0 0 12px"></div>
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
          <div class="muted" style="font-size:12px">分摊比例已改为<b>按月填写</b>——去「数据调整 → 人工填写 → 公共费用分摊比例（按月）」填；
            合计可小于 100%（剩余留公司层）。只摊台账 5 类，手填人力不摊。</div>
          <div id="buAllocLegacy" class="muted" style="font-size:12px;margin-top:6px;color:#fbbf24;display:none">
            ⚠ 检测到旧的「全年一套」分摊比例配置——已停用不再生效，请到人工填写页按月重填。</div>
        </div>
      </div>
      <div class="scard-f"><span id="buMsg" class="muted"></span></div>
    </div>

    <div class="scard full">
      <div class="scard-h"><span class="ico">🔌</span><div><div class="ttl">数据从哪来</div>
        <div class="sub">固定两路抓数：智云四表 + 共享盘台账；抓不到沿用本地文件 + 体检黄</div></div></div>
      <div class="scard-b">
        <div class="tbl-box sm wrap"><table id="sSrcTbl"></table></div>
      </div>
    </div>

  </div>
  <div id="setSaveBar" class="save-bar">
    <span class="sb-n">有 <b id="setDirtyN">0</b> 处设置未保存</span>
    <button type="button" class="ghost" onclick="setDiscard()">放弃更改</button>
    <button type="button" class="primary" id="btnSetSave" onclick="setSaveAll()">保存全部设置</button>
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
  <div class="note info">分诊台：0=绿=不用管；有数=点卡片进对应清单。处理动作与「数据调整」同一套调整机制。</div>
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
    <span class="field-inline">销售筛选 <select id="odSales"><option value="">全部销售</option></select></span>
    <span class="field-inline">批量部门 <select id="odBatchDept"><option value="">选部门…</option></select></span>
    <button class="mini" type="button" onclick="odBatchSave()">对筛选结果批量归类</button>
    <span id="odInfo" class="muted grow"></span>
  </div>
  <div class="note info">智云下单源头没填「部门」→ 排名灰显「（未填）」。可按销售筛选后批量归类；也可逐条选部门保存，或让销售在智云补填。</div>
  <div class="tbl-box lg wrap" id="odWrap"><table id="odTbl"></table></div>
</div>

<script>

/* 主题：与驾驶舱共用 cockpit-theme；iframe 同源 localStorage 同步 */
(function(){
  var root=document.documentElement, btn=document.getElementById("themeBtn");
  function apply(l){
    root.classList.toggle("theme-light", !!l);
    document.body&&document.body.classList.toggle("theme-light", !!l);
    if(btn) btn.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';
    // 同步内嵌看板 iframe（同域）
    try{
      var f=document.getElementById("dashFrame");
      if(f&&f.contentWindow){
        f.contentWindow.postMessage({type:"cockpit-theme", theme:l?"light":"dark"}, location.origin);
        try{
          var d=f.contentDocument; if(d){
            d.documentElement.classList.toggle("theme-light", !!l);
            if(d.body) d.body.classList.toggle("theme-light", !!l);
            var b=d.getElementById("themeBtn");
            if(b) b.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';
          }
        }catch(e){}
      }
    }catch(e){}
  }
  function read(){try{return localStorage.getItem("cockpit-theme")==="light";}catch(e){return false;}}
  apply(read());
  if(btn) btn.addEventListener("click", function(){
    var l=!root.classList.contains("theme-light");
    try{localStorage.setItem("cockpit-theme", l?"light":"dark");}catch(e){}
    apply(l);
  });
  window.addEventListener("storage", function(e){
    if(e.key==="cockpit-theme") apply(e.newValue==="light");
  });
})();

/* 视图档案预览：陆总在控制台切「完整↔精简（姜总视角）」，只影响下方内嵌看板（postMessage，纯 CSS 显隐）。
   不改姜总实际所见（姜总账号登录恒 executive）；管理端本页缓存的 iframe 默认 full。 */
(function(){
  var btn=document.getElementById("profBtn"), exec=false;
  function apply(){
    if(btn) btn.innerHTML=exec?'👁 精简视图（姜总）':'👁 完整视图';
    try{
      var f=document.getElementById("dashFrame");
      if(f&&f.contentWindow) f.contentWindow.postMessage({type:"cockpit-profile", profile:exec?"executive":"full"}, location.origin);
      var d=f&&f.contentDocument; if(d) d.documentElement.setAttribute("data-profile", exec?"executive":"full");
    }catch(e){}
  }
  if(btn) btn.addEventListener("click", function(){ exec=!exec; apply(); });
  // iframe 载入完成后补发一次（重载/首帧时机）
  var fr=document.getElementById("dashFrame");
  if(fr) fr.addEventListener("load", apply);
})();

let ADJ_FIELDS={};  // R1：可调字段由服务端下发（schema 黑名单制推导），不再前端写死
async function loadAdjFields(){try{ADJ_FIELDS=await jget("/api/adjust_fields");}catch(e){}}
const STD={"收入明细":"std_收入明细","下单":"std_下单","回款":"std_回款","内部译员":"std_内部译员","费用明细":"std_费用明细"};
const MANUAL_ITEMS=__MANUAL_ITEMS__; /* 由 config.manual_items 服务端注入（迭代22修：曾硬编码致新增项不出现在填写页） */
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function msg(t){document.getElementById("msg").textContent=t||"";}
async function api(path,opts){const r=await fetch(path,Object.assign({credentials:"same-origin"},opts||{}));
  if(r.status===401){location.href="/admin";throw new Error("401");}return r;}
async function jget(p){const r=await api(p);return r.json();}
async function jpost(p,body){const r=await api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));return d;}
function showSec(id){document.querySelectorAll(".sec").forEach(e=>e.classList.toggle("on",e.id===id));}
// 未保存离开保护（人工填写 / 业绩目标批量编辑）
let _formDirty=0;
function confirmLeave(){if(!_formDirty)return true;return confirm("有 "+_formDirty+" 项未保存的修改，确定离开？未保存将丢失。");}
function setDirtyCount(n){_formDirty=n||0;const bar=document.getElementById("saveBar"),c=document.getElementById("dirtyCount");
  if(bar)bar.classList.toggle("on",_formDirty>0);if(c)c.textContent=String(_formDirty);}
function refreshDirtyUI(){let n=0;
  document.querySelectorAll("#mTbl input[data-orig],#bTbl input[data-orig],#aTbl input[data-orig],#dxTbl input[data-orig]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim();
    const orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    const dirty=cur!==orig;el.closest("tr")&&el.closest("tr").classList.toggle("dirty",dirty);if(dirty)n++;});
  setDirtyCount(n);}
window.addEventListener("beforeunload",e=>{if(_formDirty>0){e.preventDefault();e.returnValue="";}});
// 顶层四区：看 / 数据调整 / 异常处理 / 设置
function showGroup(g){
  if(!confirmLeave())return;
  document.querySelectorAll(".gtab").forEach(e=>e.classList.toggle("on",e.dataset.g===g));
  document.querySelectorAll(".subgrp").forEach(e=>e.style.display=e.dataset.g===g?"flex":"none");
  if(g==="see")showSec("dash");
  else if(g==="edit")pickTable(curTable);
  else if(g==="review")showReview("overview");
  else if(g==="cfg"){showSec("settings");loadVersion();loadSettings();loadBuCfg();loadAccts();setBindDirty();}}
function reloadDash(){try{document.getElementById("dashFrame").contentWindow.location.reload();}catch(e){}}
function showToast(t,isErr,onclick){const el=document.getElementById("toast");el.textContent=t||"";
  el.className=(isErr===true?"err":(isErr||""))+(onclick?" clickable":"");
  el.onclick=onclick?()=>{el.style.display="none";onclick();}:null;
  el.style.display="block";
  clearTimeout(window._toastT);window._toastT=setTimeout(()=>{el.style.display="none";},onclick?9000:4000);}
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
  if(document.getElementById("hDetail").style.display==="block")renderHealth(h);
  if(typeof buUpdateUnknownPcHint==="function")buUpdateUnknownPcHint();}catch(e){}}
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
// 更新完成后的诚实提示：管道 ok ≠ 全绿——抓数降级/数据体检问题都要报出来，点击跳体检明细
async function refreshResultToast(L){
  const secs=(L&&L.seconds)?("（"+L.seconds+"s）"):"";
  try{await loadHealth();}catch(e){}
  const h=window._health||{};
  const probs=[...(h.run_reasons||[]),...(h.warnings||[])];
  if(h.result==="绿"&&!probs.length){const t="更新成功"+secs;msg(t);showToast("✓ "+t);return;}
  const n=probs.length||1;
  const t="更新完成，但有 "+n+" 个问题"+secs+" · 点击查看";
  msg("更新有误："+(probs[0]||("体检 "+(h.result||"?"))));
  showToast("⚠ "+t,(h.result==="红")?"err":"warn",()=>{
    window.scrollTo({top:0,behavior:"smooth"});
    renderHealth(window._health||{});document.getElementById("hDetail").style.display="block";});}
// 更新数据：后台跑+轮询进度；完成后 toast
let refT0=0;
async function doRefresh(){const b=document.getElementById("btnRefresh");b.disabled=true;
  b.textContent="更新中…";refT0=Date.now();
  try{await jpost("/api/refresh",{});}catch(e){/* 409=已在更新 → 直接跟着轮询 */}
  msg("更新数据中…");pollRefresh();}
async function pollRefresh(){const b=document.getElementById("btnRefresh");
  try{const s=await jget("/api/refresh_status");
    if(s.running){const el=Math.round((Date.now()-refT0)/1000);
      msg("更新数据中… "+el+"s"+(s.zhiyun_auto_fetch?"（含智云在线抓数，约1~2分钟）":""));
      b.textContent="更新中…";setTimeout(pollRefresh,2000);return;}
    b.disabled=false;b.textContent="更新数据";const L=s.last;
    if(L&&L.status==="error"){msg("更新失败："+L.detail);showToast("更新失败："+(L.detail||""),true);}
    else{await refreshResultToast(L);}
    reloadDash();refreshUcBadge();
  }catch(e){b.disabled=false;b.textContent="更新数据";msg("查询更新状态失败:"+e.message);}}
// 设置页
const SRC_MAP=[["下单(智云)","智云在线抓（自动登录，每次更新）"],
  ["回款(智云)","智云在线抓（自动登录，每次更新）"],
  ["项目明细(智云)","智云在线抓（自动登录，每次更新）"],
  ["内部译员·IN-HOUSE(智云)","智云在线抓（当前账号权限不足时自动沿用现有文件·体检黄，待专用账号）"],
  ["收单台账","共享盘自动拉取（部署机内网；不可达沿用本地副本·体检黄）"],
  ["手填与调整","管理员端「数据调整→人工填写」维护，全程留痕"]];
function toggleZyReveal(){const u=document.getElementById("sZyUser"),p=document.getElementById("sZyPwd"),
  e=document.getElementById("sZyEye"),show=u.type==="password";
  u.type=p.type=show?"text":"password";e.textContent=show?"🙈 隐藏":"👁 显示";}
async function loadSettings(){try{const s=await jget("/api/settings");
  schedTimes=(s.schedule_times&&s.schedule_times.length)?s.schedule_times.slice():[s.schedule_time||"09:30"];
  renderSchedTimes();
  document.getElementById("sKeep").value=s.backup_keep_days||30;
  document.getElementById("sZyUser").value=s.zhiyun_username||"";
  document.getElementById("sZyPwd").value=s.zhiyun_password||"";
  const lp=document.getElementById("sLedgerPath");if(lp)lp.value=s.ledger_share_path||"";
  const zc=s.zhiyun_conn||{},zt=zc.tables||{};  // 服务器地址+四表ID（生效值=内置默认+本地覆盖）
  const zset=(id,v)=>{const el=document.getElementById(id);if(el)el.value=v||"";};
  zset("sZyUrl",zc.base_url);zset("sTblOrders",zt.orders);zset("sTblReceipts",zt.receipts);
  zset("sTblProject",zt.project_detail);zset("sTblInhouse",zt.inhouse);
  const b=s.backup_stats||{};
  document.getElementById("sBakInfo").textContent="当前备份："+(b.count||0)+" 份，共 "+(b.mb||0)+" MB";
  const rows={};(window._health&&window._health.sources||[]).forEach(x=>rows[x.name]=x.rows);
  document.getElementById("sSrcTbl").innerHTML="<tr><th>数据</th><th>从哪来</th><th>当前行数</th></tr>"+
    SRC_MAP.map(([n,src])=>"<tr><td>"+esc(n)+"</td><td>"+esc(src)+"</td><td>"+
      (rows[n]!=null?rows[n]:"—")+"</td></tr>").join("");
  }catch(e){msg("读取设置失败:"+e.message);}}
// 版本摘要 + 更新日志（日志在右侧抽屉，默认折叠）
function openVerDrawer(){const d=document.getElementById("verDrawer");if(!d)return;
  d.classList.add("open");d.setAttribute("aria-hidden","false");}
function closeVerDrawer(){const d=document.getElementById("verDrawer");if(!d)return;
  d.classList.remove("open");d.setAttribute("aria-hidden","true");}
document.addEventListener("keydown",function(e){if(e.key==="Escape")closeVerDrawer();});
async function loadVersion(){try{const v=await jget("/api/version");
  const num="v"+String(v.version||"?").split("-")[0],stage=v.stage||"";  // 去 -beta 预发布后缀只显主号
  const pill=document.getElementById("verPill");if(pill)pill.textContent=num+(stage?" · "+stage:"");
  const nEl=document.getElementById("verNum");if(nEl)nEl.textContent=num;
  const sEl=document.getElementById("verStage");if(sEl){sEl.textContent=stage;sEl.className="stage"+(stage==="正式版"?" live":"");}
  const nx=document.getElementById("verNext");if(nx)nx.textContent=stage==="试运行"?"· 正式上线后升 v1.0":(stage==="公测 Beta"?"· 公测通过后去掉 Beta 升 v1.0 正式版":"");
  const sub=document.getElementById("verSub");if(sub)sub.textContent="按时间倒序（最新在最上面），只讲这版能多干啥；内部开发号另计、不在此显示。";
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
    let html="<div class='vu-avail'><div class='vu-h'>🔔 发现新版本 · 落后 "+(d.behind||0)+" 个提交（"+esc(d.local||"")+" → "+esc(d.remote_rev||"")+"）"
      +(d.remote&&d.remote!=="origin"?" <span class='muted'>· 源:"+esc(d.remote)+"</span>":"")+"</div>";
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
  m.textContent="";schedTimes.push("12:00");renderSchedTimes();setMark("sched");}
function schedDel(i){if(schedTimes.length<=1)return;schedTimes.splice(i,1);renderSchedTimes();setMark("sched");}
// 设置页统一底部保存：卡片只标脏，保存/放弃都在底部一条（各 save 函数返回 true/false 供汇总）
const setDirty=new Set();
function setMark(k){setDirty.add(k);setBarRender();}
function setBarRender(){const bar=document.getElementById("setSaveBar");if(!bar)return;
  bar.classList.toggle("on",setDirty.size>0);
  const n=document.getElementById("setDirtyN");if(n)n.textContent=setDirty.size;}
function setBindDirty(){if(window._setBound)return;window._setBound=1;
  [["setCardSched","sched"],["setCardBackup","backup"],["setCardZy","zy"],
   ["setCardAcct","acct"],["setCardBu","bu"]].forEach(([id,k])=>{
    const el=document.getElementById(id);if(!el)return;
    ["input","change"].forEach(ev=>el.addEventListener(ev,e=>{
      const t=e.target;// 勾选批量指定/选目标 BU 不是数据改动，不标脏
      if(t&&(t.classList&&t.classList.contains("bu-cb")||t.id==="buPickTo"))return;
      setMark(k);}));});}
async function setSaveAll(){const btn=document.getElementById("btnSetSave");if(!btn)return;
  btn.disabled=true;btn.textContent="保存中…";
  const jobs=[["sched",saveSchedule],["backup",saveBackup],["zy",saveZhiyun],["acct",acctSave],["bu",buSave]];
  let fail=0;
  for(const [k,fn] of jobs){if(!setDirty.has(k))continue;
    let ok=false;try{ok=await fn();}catch(e){ok=false;}
    if(ok!==false)setDirty.delete(k);else fail++;}
  setBarRender();btn.disabled=false;btn.textContent="保存全部设置";
  if(fail)showToast("有 "+fail+" 处设置保存失败，见对应卡片红字",true);
  else showToast("✓ 设置已保存");}
function setDiscard(){setDirty.clear();setBarRender();
  loadSettings();loadAccts();loadBuCfg();showToast("已放弃未保存的设置更改");}
async function saveSchedule(){const m=document.getElementById("sTimeMsg");m.textContent="保存中…";
  const times=schedTimes.map(t=>String(t||"").trim()).filter(Boolean);
  if(!times.length){m.textContent="至少保留一个时间点";return false;}
  try{const d=await jpost("/api/settings",{schedule_times:times});
    if(d.schedule_times&&d.schedule_times.length){schedTimes=d.schedule_times.slice();renderSchedTimes();}
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
async function saveBackup(){const m=document.getElementById("sBakMsg");m.textContent="保存中…";
  try{const d=await jpost("/api/settings",{backup_keep_days:document.getElementById("sKeep").value});
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
async function saveZhiyun(){const m=document.getElementById("sZyMsg");m.textContent="保存中…";
  const p={ledger_share_path:document.getElementById("sLedgerPath").value};  // 台账路径总是提交（含清空）
  const u=document.getElementById("sZyUser").value,pw=document.getElementById("sZyPwd").value;
  if(u||pw){p.zhiyun_username=u;p.zhiyun_password=pw;}  // 智云账号两项都填才提交（后端校验不能为空）
  const gv=id=>{const el=document.getElementById(id);return el?el.value.trim():"";};
  if(gv("sZyUrl")){  // 连接配置整组提交（界面预填生效值，没改=后端判无变更不写）
    p.zhiyun_base_url=gv("sZyUrl");
    p.zhiyun_tables={orders:gv("sTblOrders"),receipts:gv("sTblReceipts"),
      project_detail:gv("sTblProject"),inhouse:gv("sTblInhouse")};}
  try{const d=await jpost("/api/settings",p);
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
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
function acctAdd(){acctList.push({账号:"",显示名:"",权限:"整体",密码:"8888",初始密码:true,最后登录:""});acctRender();setMark("acct");}
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
  if(!_adminCount()){m.textContent="保存失败：至少保留一个「管理员」权限账号";return false;}
  if(!acctList.some(a=>String(a.账号||"").trim()===ACCT_MASTER)){
    m.textContent="保存失败：总账号「"+ACCT_MASTER+"」不可删除";return false;}
  try{const d=await jpost("/api/accounts",{accounts:acctList});acctList=d.accounts||[];
    if(d.master_account)ACCT_MASTER=d.master_account;acctPwShow={};acctRender();
    m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个）";return true;}
  catch(e){m.textContent="保存失败："+e.message;return false;}}
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
function buRenderAlloc(){const hint=document.getElementById("buAllocLegacy");if(!hint)return;
  // 迭代20：比例改按月（人工填写页）；这里只提示遗留的旧全年比例已停用
  hint.style.display=buAllocEnabledFromList()?"":"none";}
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
  document.getElementById("buMsg").textContent="已把 "+names.length+" 人批量指定到「"+tgt+"」——点底部「保存全部设置」生效并重算";}
function buUpdateUnassignedHint(){const el=document.getElementById("buUnassignedHint");if(!el)return;
  const n=(buUnassigned&&buUnassigned.unassigned_count)||0;
  if(!n){el.style.display="none";return;}el.style.display="";
  el.innerHTML="⚠ 未归属销售 <b>"+n+"</b> 人，当年下单合计 <b>"+esc(buUnassigned.unassigned_orders_disp||"")+
    "</b> —— 这部分业务不进任何 BU 页（各 BU 合计小于全公司）。归属后点保存即计入。<span class='muted'>（金额=上次保存后快照，保存后刷新）</span>";}
// 迭代21：台账「利润归属中心」未知名（服务端 warnings 已算好显示串；前端 esc 后展示，零运算）
function buUpdateUnknownPcHint(){const el=document.getElementById("buUnknownPcHint");if(!el)return;
  const warns=((window._health&&window._health.warnings)||[]).filter(function(w){
    return typeof w==="string"&&w.indexOf("利润归属中心")>=0&&w.indexOf("不在 BU 名单")>=0;});
  if(!warns.length){el.style.display="none";el.innerHTML="";return;}
  el.style.display="";
  el.innerHTML="⚠ "+warns.map(function(w){return esc(w);}).join("<br>");}
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
function buMoveToPool(name){if(!name)return;buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});buRender();setMark("bu");}
function buMoveToBu(i,name){if(!name||i<0||i>=buList.length)return;
  buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});
  const cur=_salesArr(buList[i].销售);if(cur.indexOf(name)<0)cur.push(name);buList[i].销售=cur;buRender();setMark("bu");}
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
  buRenderBatch();buUpdateUnassignedHint();buUpdateUnknownPcHint();buRenderAlloc();
  if(acctList.length)acctRender();}
function buAdd(){buList.push({name:"",负责人:[],销售:[],分摊比例:null});buRender();setMark("bu");}
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
    buRender();m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个 BU）";reloadDash();return true;}
  catch(e){m.textContent="保存失败："+e.message;return false;}}

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
function pickTable(t){if(!confirmLeave())return;curTable=t;
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  document.getElementById("dTableName").textContent=t;showSec("detail");detail.reset();}
function showManual(){
  if(document.getElementById("manual")&&!document.getElementById("manual").classList.contains("on")&&!confirmLeave())return;
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on",
  b.dataset.t==="人工填写"||b.dataset.t==="数据调整"||b.dataset.t==="手填"));
  showSec("manual");mLoad();}
function mLoadSafe(){if(!confirmLeave())return;mLoad();}
// 千分位：输入过程中即显示 1,234,567；提交时 parseAmount 去逗号
function fmtThousands(v){if(v==null||v==="")return"";const n=String(v).replace(/,/g,"");
  if(n===""||isNaN(Number(n)))return String(v);const parts=n.split(".");
  parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,",");return parts.join(".");}
function parseAmount(v){const s=String(v==null?"":v).replace(/,/g,"").trim();
  if(s===""||isNaN(Number(s)))return NaN;return Number(s);}
function bindThousands(el){if(!el||el._thou)return;el._thou=true;
  // 输入即格式化：保留光标相对「数字位数」的位置，避免跳到末尾
  const reformat=()=>{
    const raw=el.value, caret=el.selectionStart||0;
    const digitsBefore=(raw.slice(0,caret).match(/\d/g)||[]).length;
    const n=parseAmount(raw);
    if(raw.trim()===""||isNaN(n))return;
    // 末尾正在输小数点时暂不格式化，避免 1000. 被吃掉
    if(/[.,]$/.test(raw.replace(/,/g,""))&&!/\.\d+$/.test(raw.replace(/,/g,"")))return;
    const next=fmtThousands(n);
    if(next===raw)return;
    el.value=next;
    let pos=0,seen=0;
    for(let i=0;i<next.length;i++){
      if(/\d/.test(next[i])){seen++;if(seen>=digitsBefore){pos=i+1;break;}}
      pos=i+1;
    }
    try{el.setSelectionRange(pos,pos);}catch(e){}
  };
  el.addEventListener("input",reformat);
  el.addEventListener("blur",()=>{const n=parseAmount(el.value);if(!isNaN(n))el.value=fmtThousands(n);});
}function dQuery(){detail.reset();hideEditDock();}
function hideEditDock(){const d=document.getElementById("editDock");if(d){d.style.display="none";d.innerHTML="";}}
function editRow(std,keyEnc,tkey){const key=decodeURIComponent(keyEnc);
  const fields=ADJ_FIELDS[tkey]||[];
  if(!fields.length){showToast("可调字段未加载，请刷新页面后重试",true);return;}
  // 金额类字段优先排前，方便改交付额/下单额
  const prefer=["交付额","下单预估额","到账金额","结算金额","含税金额","项目成本"];
  const sorted=[...fields].sort((a,b)=>(prefer.indexOf(a)<0?99:prefer.indexOf(a))-(prefer.indexOf(b)<0?99:prefer.indexOf(b)));
  const opts=sorted.map(f=>"<option value='"+esc(f)+"'>"+esc(f)+"</option>").join("");
  const id="ef_"+Math.random().toString(36).slice(2);
  const dock=document.getElementById("editDock");
  dock.style.display="block";
  dock.innerHTML="<b style='color:var(--accent,#a78bfa)'>改数</b> 定位键 <code>"+esc(key)+"</code> ｜ "
    +"字段 <select id='"+id+"_f'>"+opts+"</select> "
    +"新值 <input id='"+id+"_v' size='14' placeholder='数字或文本' autofocus> "
    +"原因 <input id='"+id+"_r' size='14' placeholder='可选'> "
    +"<button class='mini' id='"+id+"_s'>保存</button> "
    +"<button class='mini ghost' id='"+id+"_c'>取消</button>";
  dock.scrollIntoView({behavior:"smooth",block:"nearest"});
  document.getElementById(id+"_c").onclick=()=>hideEditDock();
  document.getElementById(id+"_s").onclick=async()=>{
    const f=document.getElementById(id+"_f").value,v=document.getElementById(id+"_v").value;
    if(v===""){showToast("请填写新值",true);return;}
    const btn=document.getElementById(id+"_s");btn.disabled=true;btn.textContent="保存中…";
    try{
      await jpost("/api/adjust",{目标表:std,定位键:key,字段:f,新值:v,
        原因:document.getElementById(id+"_r").value||"管理端改数",类型:"改值"});
      hideEditDock();showToast("✓ 已保存并重算");msg("已保存调整（秒级重算）");
      reloadDash();loadHealth();refreshUcBadge();dQuery();
    }catch(e){btn.disabled=false;btn.textContent="保存";showToast("保存失败："+e.message,true);alert("保存失败："+e.message);}
  };
  document.getElementById(id+"_v").onkeydown=e=>{if(e.key==="Enter")document.getElementById(id+"_s").click();};
}
async function removeRow(std,keyEnc){const key=decodeURIComponent(keyEnc);if(!confirm("剔除该行？（软删，可撤销）"))return;
  try{await jpost("/api/adjust",{目标表:std,定位键:key,字段:"",新值:"",原因:"剔除",类型:"剔除"});
    showToast("✓ 已剔除");msg("已剔除");reloadDash();loadHealth();refreshUcBadge();dQuery();}catch(e){alert("失败："+e.message);}}
async function exportDetail(){
  try{
    let u="/api/detail_export?table="+encodeURIComponent(curTable);
    const m=ymVal("dY","dM"),q=document.getElementById("dQ").value.trim();
    if(m)u+="&month="+encodeURIComponent(m);if(q)u+="&q="+encodeURIComponent(q);
    const r=await fetch(u);if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||("HTTP "+r.status));
    const blob=await r.blob();const a=document.createElement("a");
    const cd=r.headers.get("Content-Disposition")||"";
    const mfn=cd.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
    const fn=mfn?decodeURIComponent(mfn[1].replace(/"/g,"")):(curTable+"_"+new Date().toISOString().slice(0,10)+".xlsx");
    a.href=URL.createObjectURL(blob);a.download=fn;
    a.click();URL.revokeObjectURL(a.href);showToast("✓ 已导出 Excel（当前筛选，最多 5000 行）");
  }catch(e){showToast("导出失败："+e.message,true);}
}

// ---- 手填 + 业绩目标（批量编辑，底部一次保存）----
// 业绩目标金额：库内存「元」，界面按「万元」编辑（×10000）
function yuanToWan(y){if(y==null||y==="")return"";return Number(y)/10000;}
function wanToYuan(w){return Number(w)*10000;}
async function mFillScopes(){
  const sel=document.getElementById("mScope");if(!sel)return;
  let bus=[];try{const d=await jget("/api/bu_config");bus=(d.bus||[]).map(b=>b.name);}catch(e){}
  const cur=sel.value||"全公司";
  sel.innerHTML='<option value="全公司">全公司</option>'+bus.map(n=>'<option value="'+esc(n)+'">BU · '+esc(n)+'</option>').join("");
  sel.value=[...sel.options].some(o=>o.value===cur)?cur:"全公司";
  sel.onchange=async()=>{if(!confirmLeave()){await mFillScopes();return;}await mLoad();};
}
async function mLoad(){const m=ymVal("mY","mM");if(!m){return;}
  await mFillScopes();
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  const cur=await jget("/api/manual?month="+encodeURIComponent(m)+"&scope="+encodeURIComponent(scope));
  const map={};cur.forEach(x=>map[x["项目"]]=x["金额"]);
  let h="<tr><th>项目</th><th>当前金额(元)</th><th>新值(元)</th></tr>";
  MANUAL_ITEMS.forEach(it=>{const id="mi_"+MANUAL_ITEMS.indexOf(it);
    const disp=map[it]!=null?fmtThousands(map[it]):"";
    const orig=map[it]!=null?String(map[it]):"";
    h+="<tr><td>"+esc(it)+"</td><td>"+esc(map[it]!=null?fmtThousands(map[it]):"（空=0）")+"</td>"+
    "<td><input id='"+id+"' class='amt' data-kind='manual' data-item='"+esc(it)+"' data-orig='"+esc(orig)+"' size='16' value='"+esc(disp)+"' placeholder='如 1,000,000'></td></tr>";});
  document.getElementById("mTbl").innerHTML=h;
  document.querySelectorAll("#mTbl input.amt").forEach(el=>{bindThousands(el);el.addEventListener("input",refreshDirtyUI);el.addEventListener("blur",refreshDirtyUI);});
  await bLoad();await aLoad();await dLoad();refreshDirtyUI();}
// 公共费用分摊比例（按月·迭代20）：范围=全公司才显示；比例%纯前端加总（非金额运算），金额串后端下发
let ALLOC_DATA=null;
async function aLoad(){const blk=document.getElementById("allocBlock");if(!blk)return;
  const m=ymVal("mY","mM");
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  if(scope!=="全公司"||!m){blk.style.display="none";ALLOC_DATA=null;return;}
  try{ALLOC_DATA=await jget("/api/alloc_ratios?month="+encodeURIComponent(m));}
  catch(e){blk.style.display="none";ALLOC_DATA=null;return;}
  const d=ALLOC_DATA;
  if(!d.bus||!d.bus.length){blk.style.display="none";return;}
  blk.style.display="";
  document.getElementById("allocTotal").textContent=d.month_total_disp||"0.00";
  var inh=document.getElementById("allocInherit");
  if(inh)inh.textContent=d.inherited_from?("本月未单独填写，当前沿用 "+d.inherited_from+" 的比例（改动保存后从本月起生效）"):"";
  let h="<tr><th>BU</th><th>本月分摊比例(%)</th></tr>";
  d.bus.forEach((bn,i)=>{const v=(d.ratios&&d.ratios[bn]!=null)?String(d.ratios[bn]):"";
    h+="<tr><td>"+esc(bn)+"</td><td><input id='al_"+i+"' class='amt' data-kind='alloc' data-bu='"+esc(bn)+
      "' data-orig='"+esc(v)+"' size='8' value='"+esc(v)+"' placeholder='未填=沿用上次'></td></tr>";});
  document.getElementById("aTbl").innerHTML=h;
  document.querySelectorAll("#aTbl input.amt").forEach(el=>{
    el.addEventListener("input",()=>{refreshDirtyUI();aSum();});
    el.addEventListener("blur",()=>{refreshDirtyUI();aSum();});});
  aSum();}
function aSum(){const el=document.getElementById("allocSum");if(!el||!ALLOC_DATA)return;
  let sum=0,dirty=false,bad=false;
  document.querySelectorAll("#aTbl input[data-kind=alloc]").forEach(inp=>{
    const cur=String(inp.value).trim();
    if(cur!==String(inp.dataset.orig||"").trim())dirty=true;
    if(cur==="")return;
    const n=Number(cur);if(isNaN(n)||n<0||n>100){bad=true;return;}
    sum+=n;});
  sum=Math.round(sum*10)/10;
  if(bad){el.innerHTML='<span style="color:#fecaca">有比例不是 0~100 的数字</span>';return;}
  if(sum>100.05){el.innerHTML='<span style="color:#fecaca">本月合计 '+sum+'%，超过 100%——保存会被拒绝，请调整（可以小于 100%）</span>';return;}
  const remain=Math.round((100-sum)*10)/10;
  const amt=dirty?"（保存后更新金额）":("约 ¥"+(ALLOC_DATA.remain_amt_disp||"0.00")+" 未分摊");
  el.innerHTML="本月合计 <b>"+sum+"%</b> · 剩余 <b>"+remain+"%</b> 留公司层 "+amt+
    (ALLOC_DATA.orphans&&ALLOC_DATA.orphans.length?('　<span style="color:#fbbf24">另有历史比例含未知 BU：'+esc(ALLOC_DATA.orphans.join("、"))+'（未生效）</span>'):"");}
// 费用去税率（按类别·全局一套·陆总0714）：范围=全公司才显示；税率%纯录入，不做金额运算（铁律2）
let DETAX_DATA=null;
async function dLoad(){const blk=document.getElementById("detaxBlock");if(!blk)return;
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  if(scope!=="全公司"){blk.style.display="none";DETAX_DATA=null;return;}
  try{DETAX_DATA=await jget("/api/detax_rates");}
  catch(e){blk.style.display="none";DETAX_DATA=null;return;}
  const d=DETAX_DATA;
  if(!d.categories||!d.categories.length){blk.style.display="none";return;}
  blk.style.display="";
  let h="<tr><th>费用类别</th><th>全年含税金额</th><th>去税率(%)</th></tr>";
  d.categories.forEach((c,i)=>{const cat=c.category;
    const v=(d.rates&&d.rates[cat]!=null)?String(d.rates[cat]):"";
    h+="<tr><td>"+esc(cat)+"</td><td class='muted'>"+esc(c.amount_disp||"")+"</td>"+
      "<td><input id='dx_"+i+"' class='amt' data-kind='detax' data-cat='"+esc(cat)+
      "' data-orig='"+esc(v)+"' size='8' value='"+esc(v)+"' placeholder='留空=不去税'></td></tr>";});
  document.getElementById("dxTbl").innerHTML=h;
  document.querySelectorAll("#dxTbl input.amt").forEach(el=>{
    el.addEventListener("input",refreshDirtyUI);el.addEventListener("blur",refreshDirtyUI);});}
// 业绩目标（金额界面=万元 / 毛利率=百分数）
const BUDGET_METRICS=[
  {k:"下单年预算",tip:"万元 · 全年下单目标",thou:true,pct:false,wan:true},
  {k:"回款年预算",tip:"万元 · 全年回款目标",thou:true,pct:false,wan:true},
  {k:"毛利率年目标",tip:"百分数 · 如 35 表示 35%",thou:false,pct:true,wan:false},
  {k:"下单H1目标",tip:"万元 · 上半年下单",thou:true,pct:false,wan:true},
  {k:"回款H1目标",tip:"万元 · 上半年回款",thou:true,pct:false,wan:true},
  {k:"毛利率H1目标",tip:"百分数 · 上半年毛利率",thou:false,pct:true,wan:false},
];
async function bLoad(){
  // 业绩目标改跟顶部统一筛选（明昊 2026-07-14）：年份取顶部「月份」的年、范围取顶部「范围」，无独立下拉
  const y=(document.getElementById("mY")||{}).value;
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  if(!y){return;}
  const cur=await jget("/api/budget?year="+encodeURIComponent(y));
  const map={};cur.filter(x=>(x["范围"]||"全公司")===scope&&x["指标"]!=="费用年预算").forEach(x=>map[x["指标"]]=x["金额"]);
  let h="<tr><th>指标</th><th>说明</th><th>当前</th><th>新值</th></tr>";
  BUDGET_METRICS.forEach((it,ix)=>{const id="bi_"+ix;
    const old=map[it.k]!=null?map[it.k]:null;
    // 金额类：库内元 → 界面万
    let curDisp="（未填）",inpDisp="",orig="";
    if(old!=null){
      if(it.pct){curDisp=String(old)+"%";inpDisp=String(old);orig=String(old);}
      else if(it.wan){const w=yuanToWan(old);curDisp=fmtThousands(w)+" 万";inpDisp=fmtThousands(w);orig=String(w);}
      else{curDisp=fmtThousands(old);inpDisp=fmtThousands(old);orig=String(old);}
    }
    const suffix=it.pct?'<span class="pct-suffix">%</span>':(it.wan?'<span class="pct-suffix">万</span>':"");
    h+="<tr><td>"+esc(it.k)+"</td><td class='muted'>"+esc(it.tip)+"</td>"+
    "<td>"+esc(curDisp)+"</td>"+
    "<td><input id='"+id+"' class='"+(it.thou?"amt":"")+"' data-kind='budget' data-item='"+esc(it.k)+"' data-orig='"+esc(orig)+"' data-pct='"+(it.pct?1:0)+"' data-wan='"+(it.wan?1:0)+"' size='14' value='"+esc(inpDisp)+"' placeholder='"+(it.wan?"如 8,000":"如 35")+"'>"+suffix+"</td></tr>";});
  document.getElementById("bTbl").innerHTML=h;
  document.querySelectorAll("#bTbl input").forEach(el=>{
    if(el.classList.contains("amt"))bindThousands(el);
    el.addEventListener("input",refreshDirtyUI);el.addEventListener("blur",refreshDirtyUI);
  });
  refreshDirtyUI();}
function discardDirty(){if(!_formDirty)return;if(!confirm("放弃全部未保存修改？"))return;mLoad();}
async function batchSaveAll(){
  const m=ymVal("mY","mM");const y=(document.getElementById("mY")||{}).value;
  const mScope=(document.getElementById("mScope")||{}).value||"全公司";
  const scope=mScope;   // 业绩目标改跟顶部统一范围（明昊 2026-07-14）
  const manuals=[],budgets=[];
  document.querySelectorAll("#mTbl input[data-kind=manual]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim(),orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    if(cur===orig)return;
    if(cur==="")return;
    const n=parseAmount(el.value);if(isNaN(n)){alert("「"+el.dataset.item+"」金额无效");throw new Error("bad");}
    if(n<0){alert("「"+el.dataset.item+"」不能为负");throw new Error("bad");}
    manuals.push({项目:el.dataset.item,金额:n,范围:mScope});
  });
  document.querySelectorAll("#bTbl input[data-kind=budget]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim(),orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    if(cur===orig)return;
    if(cur==="")return;
    let n=parseAmount(el.value);if(isNaN(n)){alert("「"+el.dataset.item+"」数值无效");throw new Error("bad");}
    if(el.dataset.pct==="1"){if(n<0||n>100){alert("「"+el.dataset.item+"」请填 0~100 的百分数");throw new Error("bad");}}
    else if(n<0){alert("「"+el.dataset.item+"」不能为负");throw new Error("bad");}
    // 万元 → 元入库
    if(el.dataset.wan==="1"){
      if(n>0&&n<10){if(!confirm("「"+el.dataset.item+"」="+n+" 万，目标似乎过小（是否单位填错）？仍保存？"))throw new Error("bad");}
      n=wanToYuan(n);
    }
    budgets.push({指标:el.dataset.item,金额:n,范围:scope,年份:y});
  });
  const allocs={};let allocSum=0,allocChanged=0;
  document.querySelectorAll("#aTbl input[data-kind=alloc]").forEach(el=>{
    const cur=String(el.value).trim(),orig=String(el.dataset.orig||"").trim();
    if(cur!==""){const n=Number(cur);
      if(isNaN(n)||n<0||n>100){alert("BU「"+el.dataset.bu+"」比例须为 0~100 的数字");throw new Error("bad");}
      allocSum+=n;}
    if(cur===orig)return;
    allocs[el.dataset.bu]=cur===""?null:Number(cur);allocChanged++;});
  if(allocChanged&&allocSum>100.05){alert("本月各 BU 比例合计 "+Math.round(allocSum*10)/10+"% 超过 100%，请调整（可以小于 100%，剩余留公司层）");throw new Error("bad");}
  const detax={};let detaxChanged=0;
  document.querySelectorAll("#dxTbl input[data-kind=detax]").forEach(el=>{
    const cur=String(el.value).trim(),orig=String(el.dataset.orig||"").trim();
    if(cur!==""){const n=Number(cur);
      if(isNaN(n)||n<0||n>100){alert("费用类别「"+el.dataset.cat+"」去税率须为 0~100 的数字");throw new Error("bad");}}
    if(cur===orig)return;
    detax[el.dataset.cat]=cur===""?null:Number(cur);detaxChanged++;});
  if(!manuals.length&&!budgets.length&&!allocChanged&&!detaxChanged){showToast("没有需要保存的更改");return;}
  const btn=document.getElementById("btnBatchSave");btn.disabled=true;btn.textContent="保存中…";
  try{
    if(manuals.length)await jpost("/api/manual_batch",{归属月:m,范围:mScope,items:manuals});
    if(budgets.length)await jpost("/api/budget_batch",{items:budgets});
    if(allocChanged)await jpost("/api/alloc_ratios",{归属月:m,ratios:allocs});
    if(detaxChanged)await jpost("/api/detax_rates",{rates:detax});
    setDirtyCount(0);
    showToast("✓ 已保存 "+(manuals.length+budgets.length+allocChanged+detaxChanged)+" 项并重算");
    msg("批量保存完成（留痕·看板已重算）");
    reloadDash();loadHealth();await mLoad();
  }catch(e){if(e.message!=="bad")alert("保存失败："+e.message);}
  finally{btn.disabled=false;btn.textContent="保存全部更改";}
}

// ---- 异常处理（总览 / 调整台账 / 下单未填部门 / 费用未分类 / 历史快照）----
function showReview(which){if(!confirmLeave())return;
  document.querySelectorAll("#sub-review .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===which));
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

// 下单未填部门：清单 + 按销售筛选 + 批量归类 + 行内选部门
let OD_DEPTS=[],OD_ROWS=[];
function odUrl(p){return "/api/detail?table="+encodeURIComponent("下单")+"&unfilled_dept=1&page="+p+"&page_size=200";}
async function odLoad(){const tbl=document.getElementById("odTbl");tbl.innerHTML="";OD_ROWS=[];
  try{OD_DEPTS=await jget("/api/order_depts");}catch(e){}
  const dsel=document.getElementById("odBatchDept");
  if(dsel)dsel.innerHTML="<option value=''>选部门…</option>"+OD_DEPTS.map(x=>"<option>"+esc(x)+"</option>").join("");
  let page=1,pages=1,total=0;
  try{do{const d=await jget(odUrl(page));pages=d.pages;total=d.total;
    OD_ROWS=OD_ROWS.concat(d.rows||[]);page++;
  }while(page<=pages&&page<=50);}catch(e){msg("查询失败:"+e.message);}
  const sales=[...new Set(OD_ROWS.map(r=>(r["销售"]||"").trim()).filter(Boolean))].sort();
  const ssel=document.getElementById("odSales");
  const prev=ssel?ssel.value:"";
  if(ssel){ssel.innerHTML='<option value="">全部销售</option>'+sales.map(s=>'<option>'+esc(s)+'</option>').join("");
    ssel.value=sales.includes(prev)?prev:"";ssel.onchange=odRender;}
  document.getElementById("odInfo").textContent="待归类 "+total+" 笔";
  const b=document.getElementById("odBadge");b.textContent=total;b.className="badge"+(total?"":" zero");
  odRender();}
function odRender(){const tbl=document.getElementById("odTbl");
  const sf=(document.getElementById("odSales")||{}).value||"";
  const rows=sf?OD_ROWS.filter(r=>(r["销售"]||"").trim()===sf):OD_ROWS;
  const opts="<option value=''>选部门…</option>"+OD_DEPTS.map(x=>"<option>"+esc(x)+"</option>").join("");
  let h="<tr><th>下单日期</th><th>订单号</th><th>销售</th><th>金额</th><th>归到哪个部门</th><th></th></tr>";
  rows.forEach(r=>{const key=r["定位键"];
    h+="<tr data-key='"+esc(encodeURIComponent(key))+"'><td>"+esc(r["下单日期"])+"</td><td>"+esc(r["订单号"])+
      "</td><td>"+esc(r["销售"])+"</td><td>"+esc(r["下单预估额"])+
      "</td><td><select data-key='"+esc(encodeURIComponent(key))+"'>"+opts+"</select></td>"+
      "<td><button class='mini' onclick='odSave(this)'>保存</button></td></tr>";});
  tbl.innerHTML=h||"<tr><td class='muted'>无待归类</td></tr>";
  document.getElementById("odInfo").textContent="显示 "+rows.length+" / 共 "+OD_ROWS.length+" 笔"+(sf?"（销售="+sf+"）":"");
}
async function odSave(btn){const tr=btn.closest("tr"),sel=tr.querySelector("select");
  const dept=sel.value;if(!dept){alert("先选部门");return;}
  const key=decodeURIComponent(sel.dataset.key);btn.disabled=true;
  try{await jpost("/api/adjust",{目标表:"std_下单",定位键:key,字段:"部门",新值:dept,原因:"异常处理·归类部门",类型:"改值"});
    showToast("✓ 已归类");OD_ROWS=OD_ROWS.filter(r=>r["定位键"]!==key);
    msg("已归类（写入数据修正·秒级重算）");reloadDash();loadHealth();refreshUcBadge();odRender();
    const b=document.getElementById("odBadge");b.textContent=OD_ROWS.length;b.className="badge"+(OD_ROWS.length?"":" zero");
  }catch(e){btn.disabled=false;alert("保存失败："+e.message);}}
async function odBatchSave(){
  const dept=(document.getElementById("odBatchDept")||{}).value||"";
  if(!dept){alert("先选批量部门");return;}
  const sf=(document.getElementById("odSales")||{}).value||"";
  const rows=sf?OD_ROWS.filter(r=>(r["销售"]||"").trim()===sf):OD_ROWS;
  if(!rows.length){alert("没有可归类的行");return;}
  if(!confirm("将把 "+rows.length+" 笔"+(sf?"（销售="+sf+"）":"")+" 全部归到「"+dept+"」？"))return;
  let ok=0,fail=0;
  for(const r of rows){
    try{await jpost("/api/adjust",{目标表:"std_下单",定位键:r["定位键"],字段:"部门",新值:dept,
      原因:"异常处理·批量归类"+(sf?"·"+sf:""),类型:"改值"});ok++;}
    catch(e){fail++;}
  }
  showToast("✓ 批量完成：成功 "+ok+(fail?"，失败 "+fail:""));
  reloadDash();loadHealth();refreshUcBadge();odLoad();
}
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
</script>
<div id="verDrawer" class="ver-drawer" aria-hidden="true">
  <div class="ver-drawer-mask" onclick="closeVerDrawer()"></div>
  <aside class="ver-drawer-panel" role="dialog" aria-label="更新日志">
    <div class="ver-drawer-h"><span>更新日志</span>
      <button type="button" class="ver-drawer-x" onclick="closeVerDrawer()" aria-label="关闭">×</button></div>
    <div class="ver-drawer-body">
      <div class="ver-sub" id="verSub"></div>
      <div id="verLog"></div>
    </div>
  </aside>
</div>
</body></html>"""


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

    def _bu_view_html(name: str, my_names=None, hide_pw: bool = False,
                      profile: str = accounts.VIEW_FULL) -> str:
        """渲染某 BU 页 + 可选注入（管理员隐藏自改密码 / 多 BU 账号的切换条）。缺页返回空串。
        profile：视图档案，末尾注入根节点 data-profile（BU 账号看=executive 精简，管理员看=full）。"""
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
        return _apply_profile(html, profile)

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
                return HTMLResponse(_main_with_nav(profile=accounts.view_profile(acc))
                                    or "<h1>数据尚未生成，请稍候刷新</h1>")
            names = accounts.bu_names_of(acc)  # 多 BU：绑定名单（旧单 BU 账号=[该名]）
            if names:
                existing = [n for n in names if n in _state.get("bu_pages", {})]
                if not existing:
                    return HTMLResponse(_view_login_page(
                        "你绑定的 BU 已被管理员移除，请重新登录或联系管理员"))
                # 落在第一个绑定的 BU；绑定多个时顶部带「我的 BU」切换条
                return HTMLResponse(_bu_view_html(existing[0], names,
                                                  profile=accounts.view_profile(acc)))
            # 管理员账号误走查看 cookie：引导去 /admin
            if accounts.is_admin(acc):
                return RedirectResponse("/admin", status_code=303)
        return HTMLResponse(_view_login_page())

    def _main_with_nav(hide_pw: bool = False, profile: str = accounts.VIEW_FULL) -> str:
        """整体页 + BU 入口条（只有整体/管理员会话能拿到本页，无泄漏面）。
        看端不展示「未归属 BU」文案（管理端设置页「BU 数据归属」仍提示待配置）。
        hide_pw=True（管理员会话看）：隐藏右上「🔑密码」自改密码入口——管理员改密码走 /admin「设置→账号与权限」，
        避免在内嵌看板里误改（管理员本无查看会话，点了也只会 401，属确认无用的入口）。
        profile：视图档案（full=管理员完整 / executive=整体·姜总精简），末尾按档案注入根节点 data-profile。"""
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
                         '<span class="bu-nav-links">' + links + '</span></div>')
        if parts:
            html = html.replace('<div class="wrap">', "".join(parts) + '<div class="wrap">', 1)
        return _apply_profile(html, profile)

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
        vacc = _vacc_row(request)
        my = accounts.bu_names_of(vacc)
        return HTMLResponse(_bu_view_html(name, my, profile=accounts.view_profile(vacc)))

    # ---------- v1.4 JSON API（只序列化 summary，不算账）----------
    @app.get("/api/v1/session")
    def api_v1_session(request: Request):
        admin = _user(request)
        if admin:
            acc = accounts.find_account(cfg, root, admin)
            return api_v1.session_public(acc, is_admin_session=True)
        acc = _vacc_row(request)
        if not acc:
            raise HTTPException(status_code=401, detail="未登录")
        return api_v1.session_public(acc)

    @app.post("/api/v1/login")
    def api_v1_login(payload: dict = Body(default={})):
        account = str(payload.get("account") or "").strip()
        password = str(payload.get("password") or "")
        acc = accounts.authenticate(cfg, root, account, password)
        if not acc:
            raise HTTPException(status_code=401, detail="账号或密码不正确")
        accounts.mark_login(cfg, root, account)
        if accounts.is_admin(acc):
            sess = api_v1.session_public(acc, is_admin_session=True)
            resp = JSONResponse({"ok": True, "redirect": "/admin", "session": sess})
            return _set_acookie(resp, account)
        sess = api_v1.session_public(acc)
        redir = "/"
        if not accounts.is_main(acc):
            names = accounts.bu_names_of(acc)
            if names:
                redir = f"/bu/{names[0]}"
        resp = JSONResponse({"ok": True, "redirect": redir, "session": sess})
        return _set_vcookie(resp, account)

    @app.post("/api/v1/logout")
    def api_v1_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        resp.delete_cookie(VCOOKIE)
        return resp

    @app.get("/api/v1/cockpit")
    def api_v1_cockpit(request: Request):
        """整体驾驶舱 JSON（数字与 golden 全等；前端/飞书等复用）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无整体驾驶舱权限")
        summary = _state.get("summary")
        if not summary:
            raise HTTPException(status_code=503, detail="数据尚未生成")
        out = api_v1.cockpit_payload(summary, scope="整体")
        if _state.get("built_at"):
            out.setdefault("meta", {})["built_at"] = _state["built_at"]
        return out

    @app.get("/api/v1/cockpit/bu/{name}")
    def api_v1_cockpit_bu(name: str, request: Request):
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=403, detail="无权查看该 BU")
        page = (_state.get("bu_pages") or {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="BU 不存在或未配置")
        summary = page.get("summary")
        if not summary:
            # 基准版 bu_pages 仅有 html：现场重算会动 core——此处 503 提示需带 summary 的发布
            raise HTTPException(status_code=503, detail="该 BU 尚无 JSON 快照（请更新数据）")
        return api_v1.cockpit_payload(summary, scope="BU", bu_name=name)

    @app.get("/api/v1/cockpit/view", response_class=HTMLResponse)
    def api_v1_cockpit_view(request: Request):
        """像素级同源：返回与 / 完全同一套 render_dashboard HTML（只读缓存/现算展示层）。"""
        if not (_vacct(request) or _user(request)):
            raise HTTPException(status_code=401, detail="未登录")
        if not _can_view_main(request):
            raise HTTPException(status_code=403, detail="无整体驾驶舱权限")
        html = _state.get("user_html") or ""
        if not html:
            raise HTTPException(status_code=503, detail="数据尚未生成")
        # 与 / 整体页一致：注入 BU 条与 profile
        if _user(request):
            return HTMLResponse(_main_with_nav(hide_pw=True) or html)
        acc = _vacc_row(request)
        return HTMLResponse(_main_with_nav(profile=accounts.view_profile(acc)) or html)

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
            # 数据未生成（空机器首次部署）→ 引导页：填智云账号→立即更新→自动进完整管理端（F-02）
            return HTMLResponse(_state["admin_html"] or _bootstrap_page())
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

    @app.get("/api/detail_export")
    def api_detail_export(request: Request, table: str = Query("收入明细"),
                          month: str | None = None, q: str | None = None):
        """当前筛选结果导出 Excel（.xlsx · 管理员；上限 5000 行，避免拖垮）。
        表头+行与明细页一致；月份/搜索条件与页面筛选相同。"""
        _require(request)
        import io
        from urllib.parse import quote
        from fastapi.responses import Response
        import openpyxl
        conn = _conn()
        try:
            d = db.query_detail(conn, table, month, q, page=1, page_size=5000)
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        wb = openpyxl.Workbook()
        ws = wb.active
        # sheet 名最多 31 字，去掉 Excel 非法字符
        safe = "".join(c for c in str(table) if c not in r'[]:*?/\\')[:31] or "明细"
        ws.title = safe
        cols = d["columns"]
        ws.append(list(cols))
        for r in d["rows"]:
            ws.append([r.get(c, "") if r.get(c, "") is not None else "" for c in cols])
        # 首行粗体 + 简单列宽
        for cell in ws[1]:
            cell.font = openpyxl.styles.Font(bold=True)
        for i, col in enumerate(cols, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(max(len(str(col)) + 4, 10), 28)
        bio = io.BytesIO()
        wb.save(bio)
        raw = bio.getvalue()
        day = time.strftime("%Y%m%d")
        fname = f"{safe}_{day}.xlsx"
        # RFC 5987：中文文件名用 filename*
        cd = f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{quote(fname)}"
        return Response(
            content=raw,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": cd},
        )

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
        # 与全年预渲染一致：有销售→BU 映射则多算 orders_by_bu（看端时间段查询统一按 BU）
        sales_to_bu = None
        try:
            import bu as _bu
            bucfg = _bu.load_bu_config(cfg, root)
            if bucfg and bucfg.get("bus"):
                sales_to_bu = {}
                for b in bucfg["bus"]:
                    for sal in (b.get("销售") or []):
                        sales_to_bu.setdefault(str(sal).strip(), b["name"])
                if not sales_to_bu:
                    sales_to_bu = None
        except Exception:
            sales_to_bu = None
        d = _profit.compute_daily(orders, receipts, cfg["columns"], s, e, top=top,
                                  sales_to_bu=sales_to_bu)

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

        def _mg(it):
            # 陆总0714：改叫「系统成本率」；按销售的率先不显示（防"人力算不算"连锁追问）
            if dim == "sales":
                return ""
            cp = it.get("cost_pct")
            return f"系统成本率 {cp:.0f}%" if cp is not None else "系统成本率 —"

        items = [{"name": it["name"], "revenue_disp": _wan(it["revenue"]), "margin_disp": _mg(it)}
                 for it in rk["items"]]
        if rk.get("unfilled"):
            uf = rk["unfilled"]
            items.append({"name": "（未填）", "revenue_disp": _wan(uf["revenue"]),
                          "margin_disp": _mg(uf), "unfilled": True})
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

    @app.get("/bu/{name}/export.png")
    def api_bu_export_png(name: str, request: Request, blk: str = ""):
        """BU 页导出（迭代22·D5）：截该 BU 页整页 PNG。会话闸=能看该 BU 才能导（铁律12：
        截图源就是该 BU 已过滤页面，天然不含他 BU 数据）。"""
        page = _state.get("bu_pages", {}).get(name)
        if not page:
            raise HTTPException(status_code=404, detail="Not Found")
        if not _can_view_bu(request, name):
            raise HTTPException(status_code=401, detail="请先登录看板")
        keys = set(((_state.get("summary") or {}).get("periods") or {}).keys())
        if blk and keys and blk not in keys:
            raise HTTPException(status_code=400, detail="未知周期")
        if not _EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="正在生成另一张导出图，请稍候几秒再点")
        try:
            png = _screenshot_png(page["html"], blk)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503,
                                detail=f"截图失败（{type(e).__name__}: {e}）；部署机需先 playwright install chromium")
        finally:
            _EXPORT_LOCK.release()
        label = blk or ((_state.get("summary") or {}).get("meta") or {}).get("year_key", "")
        from urllib.parse import quote
        fn = quote(f"甲骨易智能经营罗盘_{name}_{label}_{time.strftime('%Y%m%d_%H%M')}.png")
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
        版本号=根目录 VERSION（现 1.0-beta 公测 Beta），与 git 开发号(v8.x)分开、不给普通用户看。"""
        _require(request)
        return product_version.version_info()

    @app.get("/api/update/check")
    def api_update_check(request: Request):
        """④ 检测远端有没有新版本（管理员会话）：git fetch + 比对 HEAD 与 <update_remote>/分支。
        对标的远端由 config `update_remote` 决定（默认 origin；部署机从 Gitee clone 则 origin 即 Gitee）。
        只读、带护栏（非仓库/分叉/脏工作区不给更新），返回是否有新版本与"要更新啥"。"""
        _require(request)
        return updater.check_update(loaders.ROOT, remote=cfg.get("update_remote") or "origin")

    @app.post("/api/update/apply")
    def api_update_apply(request: Request):
        """④ 一键更新（管理员会话）：复检护栏 → git pull --ff-only <update_remote> → 触发看门狗重启。
        拉取成功才重启（进程以退出码 42 退出，看门狗用新代码拉起）；失败原样返回不重启。"""
        user = _require(request)
        res = updater.apply_update(loaders.ROOT, remote=cfg.get("update_remote") or "origin")
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
        out["zhiyun_conn"] = read_zhiyun_conn(cfg, root)  # 服务器地址+四表ID（内置默认+本地覆盖的生效值）
        out["ledger_share_path"] = cfg.get("ledger_share_path", "")  # 收单台账共享盘路径（界面填·落本地覆盖）
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
        old_lsp = cfg.get("ledger_share_path")
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
        if "智云连接配置已更新" in (res.get("note") or ""):
            chg.append("智云连接配置已更改（服务器/表ID）")
        # 台账路径含内网服务器名（敏感）→ 只记「已更改」不落值（铁律16）
        if "ledger_share_path" in payload and str(payload.get("ledger_share_path") or "").strip() != str(old_lsp or "").strip():
            chg.append("收单台账共享盘路径已更改")
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
    def api_manual_get(request: Request, month: str | None = None, scope: str = "全公司"):
        _require(request)
        conn = _conn()
        try:
            return db.get_manual(conn, month, 范围=scope or "全公司")
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
        scope = str(payload.get("范围") or "全公司").strip() or "全公司"
        conn = _conn()
        try:
            db.set_manual(conn, payload.get("归属月", ""), item, 金额, user, 范围=scope)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.post("/api/manual_batch")
    def api_manual_batch(request: Request, payload: dict = Body(default={})):
        """批量手填：payload={归属月, 范围?, items:[{项目,金额,范围?}]}，只重算一遍。"""
        user = _require(request)
        month = payload.get("归属月", "")
        default_scope = str(payload.get("范围") or "全公司").strip() or "全公司"
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        names = {it["name"] for it in cfg["manual_items"]}
        conn = _conn()
        try:
            n = 0
            for it in items:
                item = (it or {}).get("项目", "")
                if item not in names:
                    raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
                try:
                    金额 = float((it or {}).get("金额"))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"金额须为数字：{item}")
                sc = str((it or {}).get("范围") or default_scope).strip() or "全公司"
                db.set_manual(conn, month, item, 金额, user, 范围=sc)
                n += 1
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "count": n, "built_at": _state["built_at"]}

    def _alloc_month_payload(conn, month: str) -> dict:
        """某月分摊面板数据：BU 名单（与设置页同源）+ 比例 + 本月公共费用总额/剩余（显示串后端下发·铁律2）。"""
        import datetime as _dt
        import columns as _columns
        try:
            y, m = int(month[:4]), int(month[5:7])
            assert 1 <= m <= 12 and month[4] == "-"
        except (ValueError, AssertionError, IndexError):
            raise HTTPException(status_code=400, detail="归属月格式须为 YYYY-MM")
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        bu_names = [b["name"] for b in bucfg["bus"]]
        # 陆总0714：该月没填 → 回显沿用的最近填写月比例（inherited_from 标来源；保存即固化到本月）
        ratios, src_month = db.effective_alloc_month(conn, month)
        inherited_from = src_month if (src_month and src_month != month) else None
        lh, lr = db.load_ledger(cfg, conn)
        month_total = 0.0
        if lh:
            lcols = _columns.resolve_ledger_columns(lh)
            public_rows = profit.filter_ledger_rows_by_pc(lh, lr, {"公共"})
            start = _dt.date(y, m, 1)
            end = _dt.date(y, m + 1, 1) - _dt.timedelta(days=1) if m < 12 else _dt.date(y, 12, 31)
            led, _ = profit.compute_ledger_expenses(public_rows, y, start, end, cfg, lcols)
            month_total = round(sum(float(v or 0) for v in led.values()), 2)
        known = {b: p for b, p in ratios.items() if b in set(bu_names)}
        sum_pct = round(sum(known.values()), 1)
        remain_pct = round(max(0.0, 100.0 - sum_pct), 1)
        remain_amt = round(month_total * remain_pct / 100.0, 2)
        orphans = sorted(set(ratios) - set(bu_names))
        return {"month": month, "bus": bu_names, "ratios": known,
                "inherited_from": inherited_from,
                "orphans": orphans,
                "month_total": month_total,
                "month_total_disp": f"{month_total:,.2f}",
                "sum_pct": sum_pct, "remain_pct": remain_pct,
                "remain_amt_disp": f"{remain_amt:,.2f}"}

    @app.get("/api/alloc_ratios")
    def api_alloc_get(request: Request, month: str = ""):
        _require(request)
        conn = _conn()
        try:
            return _alloc_month_payload(conn, month)
        finally:
            conn.close()

    @app.post("/api/alloc_ratios")
    def api_alloc_set(request: Request, payload: dict = Body(default={})):
        """写某月分摊比例（管理员）。payload={归属月, ratios:{BU:比例%|null}}。
        约束：BU 须在设置页 BU 名单内；单值 0~100；已知 BU 合计 ≤100（容差 0.05）。null=删行不分摊。"""
        user = _require(request)
        month = str(payload.get("归属月") or "").strip()
        ratios = payload.get("ratios")
        if not isinstance(ratios, dict) or not ratios:
            raise HTTPException(status_code=400, detail="ratios 不能为空")
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        known = {b["name"] for b in bucfg["bus"]}
        vals: dict[str, float | None] = {}
        for b, v in ratios.items():
            b = str(b).strip()
            if b not in known:
                raise HTTPException(status_code=400, detail=f"未知 BU：{b}（以设置页 BU 名单为准）")
            if v is None or v == "":
                vals[b] = None
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"比例须为数字：{b}")
            if not (0 <= fv <= 100):
                raise HTTPException(status_code=400, detail=f"比例须在 0~100：{b}")
            vals[b] = round(fv, 1)
        conn = _conn()
        try:
            # 合并基准=该月生效比例（含沿用值·陆总0714）；保存时把生效全集固化进本月，
            # 否则只改一个 BU 会让其余 BU 的沿用比例丢失（本月一旦有行，沿用即不再兜底）
            merged, _src = db.effective_alloc_month(conn, month)
            merged = {b: p for b, p in merged.items() if b in known}
            for b, v in vals.items():
                if v is None:
                    merged.pop(b, None)
                else:
                    merged[b] = v
            total = sum(p for b, p in merged.items() if b in known)
            if total > 100.05:
                raise HTTPException(status_code=400,
                                    detail=f"该月各 BU 比例合计 {total:g}% 超过 100%，请调整（可以小于 100%，剩余留公司层）")
            for b in known:
                db.set_alloc_ratio(conn, month, b, merged.get(b), user)
            out = _alloc_month_payload(conn, month)
        finally:
            conn.close()
        _audit(cfg, root, user, ("分摊", f"公共费用分摊：{month} 比例已更改（合计 {out['sum_pct']:g}%）"))
        recompute(cfg, root)
        out.update({"status": "ok", "built_at": _state["built_at"]})
        return out

    def _detax_payload(conn) -> dict:
        """费用去税率录入页数据：可去税类别（含全年金额参考·降序）+ 已填税率。"""
        import charts  # 局部导入避免循环依赖（与本模块其余 charts 用法一致）
        cats = db.list_detax_categories(conn, cfg)
        rates = db.load_detax_rates(conn)
        return {
            "categories": [{"category": c["category"],
                            "amount_disp": charts.fmt_wan(c["amount"]) + "万"} for c in cats],
            "rates": rates,
        }

    @app.get("/api/detax_rates")
    def api_detax_get(request: Request):
        _require(request)
        conn = _conn()
        try:
            return _detax_payload(conn)
        finally:
            conn.close()

    @app.post("/api/detax_rates")
    def api_detax_set(request: Request, payload: dict = Body(default={})):
        """写费用去税率（管理员·全局一套·陆总0714）。payload={rates:{费用类别:税率%|null}}。
        税率 0~100；null/空/0 → 删行=该类别不去税（等价默认，页面数字回归红线中性）。"""
        user = _require(request)
        rates = payload.get("rates")
        if not isinstance(rates, dict) or not rates:
            raise HTTPException(status_code=400, detail="rates 不能为空")
        vals: dict[str, float | None] = {}
        for cat, v in rates.items():
            cat = str(cat).strip()
            if not cat:
                raise HTTPException(status_code=400, detail="费用类别不能为空")
            if v is None or v == "":
                vals[cat] = None
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"去税率须为数字：{cat}")
            if not (0 <= fv <= 100):
                raise HTTPException(status_code=400, detail=f"去税率须在 0~100：{cat}")
            vals[cat] = round(fv, 2)
        conn = _conn()
        try:
            for cat, v in vals.items():
                db.set_detax_rate(conn, cat, v, user)
            out = _detax_payload(conn)
        finally:
            conn.close()
        changed = "、".join(f"{c}={v if v is not None else '清除'}" for c, v in vals.items())
        _audit(cfg, root, user, ("去税", f"费用去税率已更改：{changed}"))
        recompute(cfg, root)
        out.update({"status": "ok", "built_at": _state["built_at"]})
        return out

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
        # 业务目标允许 全公司 或 BU 名；费用年预算允许部门名
        conn = _conn()
        try:
            db.set_budget(conn, year, metric, 金额, user, 范围=scope)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.post("/api/budget_batch")
    def api_budget_batch(request: Request, payload: dict = Body(default={})):
        """批量业绩目标：payload={items:[{年份,指标,金额,范围?}]}，一次重算。"""
        user = _require(request)
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        conn = _conn()
        try:
            n = 0
            for it in items:
                it = it or {}
                metric = it.get("指标", "")
                if metric not in db.BUDGET_METRICS:
                    raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
                year = str(it.get("年份", "")).strip()
                if not (year.isdigit() and len(year) == 4):
                    raise HTTPException(status_code=400, detail="年份须为4位数字")
                try:
                    金额 = float(it.get("金额"))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"金额须为数字：{metric}")
                scope = str(it.get("范围", "全公司")).strip() or "全公司"
                if metric == "费用年预算" and scope == "全公司":
                    raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
                if "毛利率" in metric and (金额 < 0 or 金额 > 100):
                    raise HTTPException(status_code=400, detail=f"毛利率须为 0~100：{metric}")
                db.set_budget(conn, year, metric, 金额, user, 范围=scope)
                n += 1
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "count": n, "built_at": _state["built_at"]}

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

    # 看门狗回滚配套：正常起服务 N 秒后清掉「更新回滚点」标记 = 确认这版没崩、无需回滚。
    # （若这版更新后启动即崩，进程活不到清标记，看门狗见标记仍在→自动回滚上一版本。）
    def _confirm_update_good():
        time.sleep(20)
        try:
            import updater
            updater.clear_rollback_marker(loaders.ROOT)
        except Exception:
            pass
    threading.Thread(target=_confirm_update_good, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
