#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网双端服务（FastAPI + uvicorn）：用户端只读 + 管理员控制台（明细编辑/手填/年度预算/调整台账）。

- 用户端 `/`：无密码，只含汇总（利润驾驶舱 HTML）；**明细数据不进用户端页面、也无明细接口可达**。
- 管理员端 `/admin`：无有效会话 → 密码页；登录后看同一驾驶舱（刀4 加编辑/明细/台账）。
- `/admin/login`：密码（pbkdf2 哈希，存 config 外的本地文件）+ 选身份(明昊/陆总) → 会话 cookie(24h)。
- `/api/detail`：明细数据，**仅会话内可用**（服务端挡，未登录 401；非前端藏）。
- `/api/health`：最近一次运行日志（体检状态条数据源）。

安全实现用标准库（不引 bcrypt/itsdangerous）：口令 pbkdf2_hmac、会话 HMAC 签名 token。
密码/密钥存 数据/管理员密钥.json（绝不进 git）；首次起服务自动生成，默认口令见 README（可用
环境变量 KANBAN_ADMIN_PW 覆盖）。
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import loaders
import db
import core
import ingest
import render
import assets

COOKIE = "kanban_session"
SESSION_TTL = 24 * 3600
PBKDF2_ITERS = 200_000
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", "kanban2026")
IDENTITIES = ("明昊", "陆总")

# 服务内存态：当前汇总 + 渲染好的两端页面 + 上次规范化的原始记录（供秒级重算）
# refreshing/last_refresh：后台「立即更新」的进行中标记与最近一次结果（/api/refresh_status 用）
_state: dict = {"summary": None, "user_html": "", "admin_html": "", "built_at": None, "records": None,
                "refreshing": None, "last_refresh": None}
_LOCK = threading.Lock()  # 写库/重算全局互斥（03：写库一把锁，运行中排队）


# ---------------- 密钥文件（口令哈希 + 会话签名密钥） ----------------
def _secret_path(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / "管理员密钥.json"


def _load_or_init_secret(cfg, root=None) -> dict:
    p = _secret_path(cfg, root)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    salt = os.urandom(16)
    sec = {
        "salt": salt.hex(),
        "iters": PBKDF2_ITERS,
        "pw_hash": hashlib.pbkdf2_hmac("sha256", DEFAULT_PW.encode(), salt, PBKDF2_ITERS).hex(),
        "cookie_key": os.urandom(32).hex(),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[server] 已生成管理员密钥文件：{p}（默认口令：{DEFAULT_PW}，可删文件+设 KANBAN_ADMIN_PW 重置）")
    return sec


def _verify_pw(sec: dict, pw: str) -> bool:
    salt = bytes.fromhex(sec["salt"])
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, int(sec["iters"])).hex()
    return hmac.compare_digest(calc, sec["pw_hash"])


# ---------------- 会话 token（HMAC 签名，含过期） ----------------
def _make_token(sec: dict, user: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = f"{user}|{int(now + SESSION_TTL)}".encode()
    b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(bytes.fromhex(sec["cookie_key"]), b64, hashlib.sha256).hexdigest()
    return b64.decode() + "." + sig


def _check_token(sec: dict, token: str, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expect = hmac.new(bytes.fromhex(sec["cookie_key"]), b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        user, exp = base64.urlsafe_b64decode(b64.encode()).decode().split("|")
    except (ValueError, TypeError):
        return None
    if float(exp) < now:
        return None
    return user if user in IDENTITIES else None


# ---------------- 渲染缓存 ----------------
def _publish(cfg, summary, html):
    _state["summary"] = summary
    _state["user_html"] = html
    _state["admin_html"] = _admin_page(html, summary)
    _state["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    summary, html, ing = core.generate(cfg, today, trigger=trigger)
    _state["records"] = ing.get("records")  # 缓存原始记录供秒级重算
    _publish(cfg, summary, html)
    return ing


def _do_recompute(cfg, root) -> None:
    if not _state.get("records"):
        _do_full(cfg, root, "manual")
        return
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, root)
    try:
        ingest.reapply(cfg, conn, _state["records"], today)
        summary = core.summary_from_conn(cfg, conn, today)
    finally:
        conn.close()
    html = render.render_dashboard(summary, cfg, assets.load_logo_base64(cfg))
    _publish(cfg, summary, html)


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
    """校验并落盘设置：改运行中 cfg（即时生效）+ 重写 config.json（重启不丢）。
    Windows 上改 schedule_time 会顺手 schtasks /Change 已注册的计划任务（没注册过则提示跑 bat）。"""
    st = str(payload.get("schedule_time", cfg.get("schedule_time", "09:30"))).strip()
    if not _TIME_RE.match(st):
        raise ValueError("自动更新时间格式须为 HH:MM（24小时制），如 09:30")
    try:
        keep = int(payload.get("backup_keep_days", cfg.get("backup_keep_days", 30)))
    except (TypeError, ValueError):
        raise ValueError("备份保留天数须为整数")
    if not (1 <= keep <= 365):
        raise ValueError("备份保留天数须在 1~365 之间")
    auto = bool(payload.get("zhiyun_auto_fetch", cfg.get("zhiyun_auto_fetch", False)))

    cfg["schedule_time"], cfg["backup_keep_days"], cfg["zhiyun_auto_fetch"] = st, keep, auto
    p = _config_file(root)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["schedule_time"], raw["backup_keep_days"], raw["zhiyun_auto_fetch"] = st, keep, auto
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 智云账号（可选字段；两者都给才处理，改了才写+清旧会话）
    zu, zp = payload.get("zhiyun_username"), payload.get("zhiyun_password")
    cred_note = ""
    if zu is not None and zp is not None:
        zu, zp = str(zu).strip(), str(zp)
        if not zu or not zp:
            raise ValueError("智云账号和密码都不能为空")
        if save_zhiyun_creds(cfg, root, zu, zp):
            cred_note = "；智云账号已更新（下次更新自动用新账号登录）"

    note = "已保存" + cred_note
    import sys
    if sys.platform == "win32":
        import subprocess
        try:
            r = subprocess.run(["schtasks", "/Change", "/TN", SCHTASK_NAME, "/ST", st],
                               capture_output=True, timeout=15)
            note += "；计划任务时间已改" if r.returncode == 0 else \
                "；⚠计划任务未改成（可能还没注册）——请以管理员身份跑一次 注册每日更新.bat"
        except Exception:
            note += "；⚠改计划任务出错——请以管理员身份跑一次 注册每日更新.bat"
    else:
        note += "（本机非 Windows：计划任务时间在部署机上生效）"
    return {"schedule_time": st, "backup_keep_days": keep, "zhiyun_auto_fetch": auto, "note": note}


def recompute(cfg, root=None) -> None:
    """**秒级重算**（保存调整/手填后）：缓存记录重置标准表→重放→重算→重渲染，不读 xlsx。"""
    with _LOCK:
        _do_recompute(cfg, root)


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
        reasons.append(f"{adj['expired']} 条调整「过期疑似」（源头已改、调整未套用）→ 去『复核·调整台账』看")
    return reasons


_LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理员登录 · 经营驾驶舱</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#1e293b;padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px #0006}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:#94a3b8}}
input,select{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid #334155;background:#0f172a;color:#e2e8f0;font-size:14px}}
button{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:#f87171;font-size:13px;margin-bottom:10px}}</style></head>
<body><form class="card" method="post" action="/admin/login">
<h1>管理员端登录</h1>{err}
<label>身份</label><select name="identity">{opts}</select>
<label>密码</label><input type="password" name="password" autofocus>
<button type="submit">进入</button></form></body></html>"""


def _login_page(err: str = "") -> str:
    opts = "".join(f'<option value="{i}">{i}</option>' for i in IDENTITIES)
    err_html = f'<div class="err">{err}</div>' if err else ""
    return _LOGIN_HTML.format(err=err_html, opts=opts)


_ADMIN_CONSOLE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理员控制台 · 经营驾驶舱</title>
<style>
:root{--bg:#0f172a;--panel:#1e293b;--line:#334155;--fg:#e2e8f0;--mut:#94a3b8;--vio:#8b5cf6}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:var(--bg);color:var(--fg)}
#bar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
#bar b{font-size:15px}.pill{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;user-select:none}
.g{background:#14532d;color:#86efac}.y{background:#713f12;color:#fde68a}.r{background:#7f1d1d;color:#fca5a5}
button{background:var(--vio);color:#fff;border:0;border-radius:7px;padding:6px 12px;font-size:13px;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
button.mini{padding:3px 8px;font-size:12px}button:disabled{opacity:.5;cursor:wait}
a{color:var(--vio)}
/* 顶层三区 */
#groups{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px 0;background:#172033}
.gtab{padding:8px 18px;border-radius:8px 8px 0 0;cursor:pointer;font-size:14px;font-weight:600;color:var(--mut);border:1px solid transparent;border-bottom:none}
.gtab.on{background:var(--bg);color:var(--fg);border-color:var(--line)}
/* 二级分段（改数据6项 / 复核3项） */
#subnav{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 14px;background:#172033;border-bottom:1px solid var(--line);min-height:0}
.subgrp{display:none;gap:6px;align-items:center;flex-wrap:wrap}
.stab{background:transparent;border:1px solid var(--line);color:var(--mut);padding:6px 13px;border-radius:20px;font-size:13px;cursor:pointer}
.stab.on{background:var(--vio);color:#fff;border-color:var(--vio)}
.subsep{width:1px;height:18px;background:var(--line);margin:0 4px}
.subgrp .badge{background:#7f1d1d;color:#fca5a5;border-radius:20px;padding:0 6px;font-size:11px;margin-left:5px}
.subgrp .badge.zero{background:#14532d;color:#86efac}
.sec{display:none;padding:14px}.sec.on{display:block}
input,select{background:var(--bg);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:6px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}
th,td{border:1px solid var(--line);padding:5px 7px;text-align:left;white-space:nowrap}
th{background:#172033;position:sticky;top:0}tr.exp{background:#3b1d1d}
.wrap{overflow:auto;max-height:70vh}.row-form{margin:6px 0;padding:8px;background:#172033;border-radius:7px}
.muted{color:var(--mut);font-size:12px}iframe{width:100%;height:78vh;border:1px solid var(--line);border-radius:8px;background:#fff}
.note{color:var(--mut);font-size:12px;margin:6px 0}
#hDetail{display:none;position:absolute;top:46px;left:14px;z-index:30;max-width:560px;background:var(--panel);
border:1px solid var(--line);border-radius:9px;padding:12px 14px;font-size:12px;line-height:1.6;box-shadow:0 10px 30px #0009}
#hDetail h4{margin:0 0 4px;font-size:13px}#hDetail .grp{margin-top:10px}
#hDetail .k{color:var(--mut);font-weight:600;margin-bottom:2px}
#hDetail ul{margin:3px 0 0;padding-left:18px}#hDetail .ok{color:#86efac}
</style></head><body>
<div id="bar">
  <b>管理员控制台</b>
  <span id="health" class="pill y" onclick="toggleHealth()" title="点开看体检明细">体检…</span>
  <button id="btnRefresh" onclick="doRefresh()">立即更新</button>
  <span id="msg" class="muted"></span>
  <span style="margin-left:auto"></span>
  <a href="/admin/logout">退出</a>
</div>
<div id="hDetail"></div>
<div id="groups">
  <div class="gtab on" data-g="see" onclick="showGroup('see')">看</div>
  <div class="gtab" data-g="edit" onclick="showGroup('edit')">改数据</div>
  <div class="gtab" data-g="review" onclick="showGroup('review')">复核</div>
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
    <button class="stab on" data-t="ledger" onclick="showReview('ledger')">调整台账</button>
    <button class="stab" data-t="unclassified" onclick="showReview('unclassified')">未填分类<span id="ucBadge" class="badge zero">0</span></button>
    <button class="stab" data-t="history" onclick="showReview('history')">历史快照</button>
  </span>
</div>

<div id="dash" class="sec on"><iframe id="dashFrame" src="/"></iframe>
  <div class="note">改数后此驾驶舱会自动刷新（秒级重算）。</div></div>

<div id="detail" class="sec">
  <div>当前表：<b id="dTableName">收入明细</b> &nbsp;
    月份<select id="dY"></select><select id="dM"></select>
    搜索<input id="dQ" placeholder="订单号/客户…" size="12">
    <button onclick="dQuery()">查询</button>
    <span id="dInfo" class="muted"></span>
  </div>
  <div class="note">改数=写一条调整记录（重抓不丢）；剔除=软删（可在调整台账撤销）。滚动到底自动加载更多。</div>
  <div class="wrap" id="dWrap"><table id="dTbl"></table></div>
</div>

<div id="manual" class="sec">
  月份<select id="mY"></select><select id="mM"></select><button onclick="mLoad()">查询</button>
  <span class="muted">改手填即留痕（manual_历史），当月覆盖。</span>
  <div class="wrap"><table id="mTbl"></table></div>
  <div class="note" style="margin-top:18px">年度预算（经营目标·全公司口径）：下单/回款两个年度数，年初定、年中改留痕；填了老板端回款图即出预算线与完成率。</div>
  年份<select id="bY"></select>
  <div class="wrap"><table id="bTbl"></table></div>
  <div class="note" style="margin-top:14px">部门费用年预算：按收单台账「预算归属部门」逐部门填；填了老板端即出「部门费用预算执行」卡（已用=白名单内含税年累计）。改已有值需确认、全程留痕。</div>
  <div class="wrap"><table id="bdTbl"></table></div>
</div>

<div id="ledger" class="sec">
  <button onclick="lLoad()">刷新台账</button><span id="lInfo" class="muted"></span>
  <div class="note">过期疑似（红）= 源头已改、调整未套用，请复核。</div>
  <div class="wrap"><table id="lTbl"></table></div>
</div>

<div id="history" class="sec">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    看哪天 <select id="hisSel"></select>
    <span id="hisInfo" class="muted"></span>
  </div>
  <div class="note">每天更新完自动存一份当天页面（同天多次更新=留最后一次），保留天数在「设置」里改；月末那天的随月末快照永久保留。</div>
  <iframe id="hisFrame" style="margin-top:8px"></iframe>
</div>

<div id="settings" class="sec">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;max-width:1100px">

    <div class="row-form" style="margin:0;padding:16px 18px">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px">⏰ 自动更新</div>
      <div class="muted" style="margin-bottom:14px">每天自动跑一次完整更新（抓数→重算→出页面）</div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span>每日更新时间</span><input id="sTime" type="time" style="font-size:15px;padding:8px 10px">
      </div>
      <div class="muted">Windows 部署机计划任务的运行时间；保存后自动改已注册的计划任务（首次注册跑一次 注册每日更新.bat）。平时也可随时点顶栏「立即更新」。</div>
    </div>

    <div class="row-form" style="margin:0;padding:16px 18px">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px">🗄 备份清理</div>
      <div class="muted" style="margin-bottom:14px">每次更新自动把算好的 看板.db 备份到 数据/备份/（每天一份）</div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span>备份保留</span><input id="sKeep" type="number" min="1" max="365" style="width:80px;font-size:15px;padding:8px 10px"><span>天</span>
      </div>
      <div class="muted">超过天数自动删最旧的，防止磁盘一直涨；月末快照存档（快照存档/）是财务时点档案，不受影响、永久保留。</div>
      <div id="sBakInfo" class="muted" style="margin-top:8px"></div>
    </div>

    <div class="row-form" style="margin:0;padding:16px 18px;grid-column:1/-1">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px">🔑 智云账号（在线抓数用）</div>
      <div class="muted" style="margin-bottom:14px">每次更新用这个账号自动登录智云抓数。换账号（如启用专用只读账号）只需改这两项并保存——账号内部ID登录时自动获取，下次「立即更新」即用新账号；账号密码错了会抓不到数（体检黄），改对即恢复。</div>
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <span>账号 <input id="sZyUser" type="password" autocomplete="off" style="width:180px;font-size:14px;padding:8px 10px"></span>
        <span>密码 <input id="sZyPwd" type="password" autocomplete="off" style="width:180px;font-size:14px;padding:8px 10px"></span>
        <button class="ghost mini" type="button" onclick="toggleZyReveal()" id="sZyEye">👁 显示</button>
      </div>
    </div>

    <div class="row-form" style="margin:0;padding:16px 18px;grid-column:1/-1">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px">🔌 数据从哪来（固定流程·无需配置）</div>
      <div class="muted" style="margin-bottom:10px">每次更新固定做两路抓数：① 自动登录智云在线抓四张表；② 从共享盘拉最新收单台账。哪个源抓不到（不在内网/账号权限不足/服务器没开）就自动沿用 数据/ 里现有文件继续算，并在顶栏体检里标黄——不中断、不用管。</div>
      <div class="wrap"><table id="sSrcTbl"></table></div>
    </div>

  </div>
  <div style="margin-top:14px">
    <button onclick="saveSettings()">保存设置</button>
    <span id="sMsg" class="muted"></span>
  </div>
</div>

<div id="unclassified" class="sec">
  <button onclick="ucLoad()">刷新未填分类</button><span id="ucInfo" class="muted"></span>
  <div class="note">这些费用明细还没填「对应报表大类」→ 暂未计入费用（利润会略偏高）。请在源头收单台账补填，下次更新自动计入。</div>
  <div class="wrap" id="ucWrap"><table id="ucTbl"></table></div>
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
// 顶层三区：看 / 改数据 / 复核
function showGroup(g){document.querySelectorAll(".gtab").forEach(e=>e.classList.toggle("on",e.dataset.g===g));
  document.querySelectorAll(".subgrp").forEach(e=>e.style.display=e.dataset.g===g?"flex":"none");
  if(g==="see")showSec("dash");
  else if(g==="edit")pickTable(curTable);
  else if(g==="review")showReview("ledger");
  else if(g==="cfg"){showSec("settings");loadSettings();}}
function reloadDash(){try{document.getElementById("dashFrame").contentWindow.location.reload();}catch(e){}}
async function loadHealth(){try{const h=await jget("/api/health");window._health=h;const el=document.getElementById("health");
  const c=h.result==="绿"?"g":h.result==="红"?"r":"y";el.className="pill "+c;
  const nWarn=(h.warnings&&h.warnings.length)||0;
  el.textContent="体检 "+(h.result||"?")+(nWarn?(" · "+nWarn+"警"):"")+" ▾";
  if(document.getElementById("hDetail").style.display==="block")renderHealth(h);}catch(e){}}
function toggleHealth(){const d=document.getElementById("hDetail");
  if(d.style.display==="block"){d.style.display="none";return;}renderHealth(window._health||{});d.style.display="block";}
function renderHealth(h){h=h||{};const reasons=h.run_reasons||[],warns=h.warnings||[];
  // 两套信号分开讲：①「黄/红」=管道运行（fetch/过期调整）②「警」=数据体检（未填分类等）
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
// 立即更新：后台跑+轮询进度（在线抓开着约80秒，同步等会像卡死）
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
    if(L&&L.status==="error")msg("更新失败："+L.detail);
    else msg("已更新"+(L&&L.seconds?("（"+L.seconds+"s）"):""));
    reloadDash();loadHealth();refreshUcBadge();
  }catch(e){b.disabled=false;msg("查询更新状态失败:"+e.message);}}
// 设置页
// 数据来源标注（固定流程，只展示不可配）：各表从哪来 + 抓不到时的兜底
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
  document.getElementById("sTime").value=s.schedule_time||"09:30";
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
async function saveSettings(){const m=document.getElementById("sMsg");m.textContent="保存中…";
  try{const d=await jpost("/api/settings",{schedule_time:document.getElementById("sTime").value,
    backup_keep_days:parseInt(document.getElementById("sKeep").value,10),
    zhiyun_username:document.getElementById("sZyUser").value,
    zhiyun_password:document.getElementById("sZyPwd").value});
    m.textContent=d.note||"已保存";}catch(e){m.textContent="保存失败："+e.message;}}

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
    msg("已保存年度预算（留痕·驾驶舱已重算）");reloadDash();bLoad();}catch(e){alert("保存失败："+e.message);}}
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

// ---- 复核（调整台账 / 未填分类）----
function showReview(which){document.querySelectorAll("#sub-review .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===which));
  showSec(which);if(which==="ledger")lLoad();if(which==="unclassified")ucLoad();if(which==="history")hisLoad();}
// 历史快照：按天回看（每天最后一次更新的页面原样）
async function hisLoad(){const sel=document.getElementById("hisSel"),info=document.getElementById("hisInfo");
  try{const d=await jget("/api/history");
    if(!d.length){info.textContent="还没有历史快照（每次更新后自动生成，明天起就有了）";
      document.getElementById("hisFrame").src="about:blank";sel.innerHTML="";return;}
    sel.innerHTML=d.map(x=>'<option value="'+x.day+'">'+x.label+"（存于 "+esc(x.saved_at)+"）</option>").join("");
    info.textContent="共 "+d.length+" 天";hisShow(d[0].day);
    sel.onchange=()=>hisShow(sel.value);
  }catch(e){info.textContent="加载失败:"+e.message;}}
function hisShow(day){document.getElementById("hisFrame").src="/api/history/"+day;}
async function lLoad(){const d=await jget("/api/adjustments");document.getElementById("lInfo").textContent="共 "+d.length+" 条";
  let h="<tr><th>id</th><th>时间</th><th>经手人</th><th>目标表</th><th>字段</th><th>原值→新值</th><th>类型</th><th>状态</th><th></th></tr>";
  d.forEach(a=>{const exp=a["状态"]==="过期疑似";h+="<tr class='"+(exp?"exp":"")+"'><td>"+a.id+"</td><td>"+esc(a["创建时间"])+"</td><td>"+esc(a["经手人"])+
    "</td><td>"+esc(a["目标表"])+"</td><td>"+esc(a["字段"])+"</td><td>"+esc(a["原值"])+" → "+esc(a["新值"])+"</td><td>"+esc(a["类型"])+
    "</td><td>"+esc(a["状态"])+"</td><td>"+(a["状态"]==="已撤销"?"":"<button class='mini ghost' onclick='lRevoke("+a.id+")'>撤销</button>")+"</td></tr>";});
  document.getElementById("lTbl").innerHTML=h;}
async function lRevoke(id){if(!confirm("撤销该调整？"))return;try{await jpost("/api/adjust/"+id+"/revoke",{});
  msg("已撤销");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}

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
  document.getElementById("ucInfo").textContent="未填分类 "+ucTotal+" 笔";setUcBadge(ucTotal);}
function setUcBadge(n){const b=document.getElementById("ucBadge");b.textContent=n;b.className="badge"+(n?"":" zero");}
async function refreshUcBadge(){try{const d=await jget(ucUrl(1).replace("page_size=200","page_size=1"));setUcBadge(d.total);}catch(e){}}

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
loadHealth();refreshUcBadge();loadAdjFields();setInterval(loadHealth,30000);
// 打开页面时若更新已在跑（别处/定时触发），按钮跟着进入进度态
jget("/api/refresh_status").then(s=>{if(s.running){document.getElementById("btnRefresh").disabled=true;refT0=Date.now();pollRefresh();}}).catch(()=>{});
</script></body></html>"""


# ---------------- FastAPI 应用 ----------------
def create_app(cfg, root=None) -> FastAPI:
    app = FastAPI(title="经营驾驶舱", docs_url=None, redoc_url=None, openapi_url=None)
    sec = _load_or_init_secret(cfg, root)

    def _user(request: Request) -> str | None:
        return _check_token(sec, request.cookies.get(COOKIE, ""))

    @app.get("/", response_class=HTMLResponse)
    def user_page():
        return HTMLResponse(_state["user_html"] or "<h1>数据尚未生成，请稍候刷新</h1>")

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        if _user(request):
            return HTMLResponse(_state["admin_html"] or "<h1>数据尚未生成</h1>")
        return HTMLResponse(_login_page())

    @app.post("/admin/login")
    def admin_login(identity: str = Form(""), password: str = Form("")):
        if identity not in IDENTITIES or not _verify_pw(sec, password):
            return HTMLResponse(_login_page("身份或密码不正确"), status_code=401)
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(COOKIE, _make_token(sec, identity), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        return resp

    @app.get("/admin/logout")
    def admin_logout():
        resp = RedirectResponse("/admin", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/api/detail")
    def api_detail(request: Request, table: str = Query("收入明细"), month: str | None = None,
                   q: str | None = None, page: int = 1, page_size: int = 50,
                   unclassified: bool = False):
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        conn = db.connect(cfg, root)
        try:
            try:
                return JSONResponse(db.query_detail(conn, table, month, q, page, page_size, unclassified))
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e))
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
        return {
            "result": (run_log or {}).get("结果"),          # 黄/红/绿：管道运行日志
            "run_time": (run_log or {}).get("时间"),
            "built_at": _state.get("built_at"),
            "sources": health.get("sources", []),
            "warnings": health.get("warnings", []),          # 「警」：数据体检（未填分类等）
            "run_reasons": _run_reasons((run_log or {}).get("体检", {})),  # 「黄/红」：为啥（fetch/过期调整）
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

    @app.get("/api/settings")
    def api_settings_get(request: Request):
        _require(request)
        out = {k: cfg.get(k) for k in EDITABLE_SETTINGS}
        creds = read_zhiyun_creds(cfg, root)
        out["zhiyun_username"], out["zhiyun_password"] = creds["username"], creds["password"]
        bdir = loaders.data_dir(cfg, root) / "备份"
        baks = (sorted(bdir.glob("看板_*.db")) + sorted(bdir.glob("页面_*.html"))) if bdir.exists() else []
        out["backup_stats"] = {"count": len(baks),
                               "mb": round(sum(p.stat().st_size for p in baks) / 1048576, 1)}
        return out

    @app.post("/api/settings")
    def api_settings_post(request: Request, payload: dict = Body(default={})):
        _require(request)
        try:
            return save_settings(cfg, root, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
