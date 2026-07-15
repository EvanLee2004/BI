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

import json
import os
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import loaders
import accounts
import db
import tpl
import auth_session
import refresh_pipeline
from app_state import (  # noqa: F401  # 测试/外部可读 server._state
    COOKIE,
    VCOOKIE,
    SESSION_TTL,
    STATIC_DIR,
    _state,
    _LOCK,
    _EXPORT_LOCK,
)

# B-P5：已登录整体/BU 页固定 static shell + fragments（无 SERVE_SHELL 化石开关）。
# 测试断言 HTML 内容请用 _state["user_html"] / page["html"] / fragments 组装，勿依赖 / 直出 SSR。

# 会话态文档页禁止浏览器缓存：未登录时同一 URL 是登录页，登录后是 shell/控制台；
# 若缺 no-store，登录成功 location.replace 同 URL 会直接吃缓存登录页（P0·2026-07-16）。
# 真正静态 css/js/图走 /static 不受影响；/admin/app.js 已有同类先例。
_NO_STORE = {"Cache-Control": "no-store"}


def _html_doc(content: str, status_code: int = 200) -> HTMLResponse:
    """HTML 文档响应：带 no-store，防会话态页面被缓存。"""
    return HTMLResponse(content, status_code=status_code, headers=_NO_STORE)


def _file_html_doc(path: Path) -> FileResponse:
    """HTML 文件文档响应：带 no-store。"""
    return FileResponse(path, media_type="text/html; charset=utf-8", headers=_NO_STORE)


# 管理员会话看内嵌看板时隐藏「🔑密码」自改入口（管理员改密走 /admin 设置页，避免误改）
# 模板缓存于模块载入（tpl.load 一次）；内容与迁前逐字节一致
_HIDE_PW_STYLE = tpl.load("partials/hide_pw_style.html")
_WRAP_OPEN = tpl.load("partials/wrap_open.html")
_EMPTY_DATA_HTML = tpl.load("partials/empty_data.html")
_BU_NAV_TPL = tpl.load("partials/bu_nav.html")
_BU_NAV_LINK_TPL = tpl.load("partials/bu_nav_link.html")
# 兼容旧测试/文档引用（v8.0 起管理员口令在 看板账号.json，不再走密钥哈希）
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", accounts.DEFAULT_ADMIN_PW)
DEFAULT_VIEW_PW = accounts.DEFAULT_VIEW_PW
DEFAULT_ADMIN_ACCOUNT = "lushasha"

# ---------------- 会话（auth_session）兼容别名 ----------------
_secret_path = auth_session.secret_path
_load_or_init_secret = auth_session.load_or_init_secret
_save_secret = auth_session.save_secret
_make_token = auth_session.make_token
_check_token_raw = auth_session.check_token_raw
_check_token = auth_session.check_token
_check_vsubject = auth_session.check_vsubject

# ---------------- 刷新管道（refresh_pipeline）兼容别名 ----------------
# 注意：_do_full / start_refresh_async 必须挂在 server 模块上，
# 以便 tests 打桩 server._do_full（见 test_admin_edit 刷新异步）。
_publish = refresh_pipeline.publish
_do_full = refresh_pipeline.do_full
_do_recompute = refresh_pipeline.do_recompute
recompute = refresh_pipeline.recompute


def refresh(cfg, root=None, trigger="manual") -> dict:
    """完整更新；持锁调用本模块 _do_full（可被测试替换）。"""
    with _LOCK:
        return _do_full(cfg, root, trigger)


def start_refresh_async(cfg, root=None, trigger="manual") -> bool:
    """后台完整更新。调用本模块 _do_full，便于测试打桩。"""
    if not _LOCK.acquire(blocking=False):
        return False
    _state["refreshing"] = {"started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger}

    def _job():
        t0 = time.time()
        try:
            ing = _do_full(cfg, root, trigger)
            _state["last_refresh"] = {
                "status": "ok",
                "result": ing.get("result"),
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            _state["last_refresh"] = {
                "status": "error",
                "detail": f"{type(e).__name__}: {e}",
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
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
            r = subprocess.run(["schtasks", "/Change", "/TN", name, "/ST", t], capture_output=True, timeout=15)
            if r.returncode == 0:
                changed += 1
                continue
            rc = subprocess.run(
                ["schtasks", "/Create", "/TN", name, "/SC", "DAILY", "/ST", t, "/TR", tr, "/F"],
                capture_output=True,
                timeout=15,
            )
            if rc.returncode == 0:
                created += 1
            else:
                failed += 1
        for i in range(len(times) + 1, MAX_SCHEDULE_TIMES + 2):  # 删多余编号任务
            subprocess.run(["schtasks", "/Delete", "/TN", f"{SCHTASK_NAME}_{i}", "/F"], capture_output=True, timeout=15)
    except Exception:
        return "；⚠计划任务同步出错——请以管理员身份重跑 注册每日更新.bat"
    if failed:
        return f"；⚠有 {failed} 个时间点没同步成（多半需管理员权限）——请以管理员身份重跑 注册每日更新.bat"
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
    d["md_pss_id"] = ""  # 旧会话作废，强制新账号重登
    d["account_id"] = ""  # 登录时从页面全局变量自动取新账号的 GUID
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def read_zhiyun_conn(cfg, root=None) -> dict:
    """读智云连接配置的**生效值**（内置默认 ZHIYUN_DEFAULTS + 本地覆盖合并后）：服务器地址 + 四表ID。"""
    from ingest import fetch_zhiyun

    zy = fetch_zhiyun._load_zhiyun_cfg(cfg, root)
    tables = {s: str(((zy.get("tables") or {}).get(s) or {}).get("worksheetId", "")) for s in fetch_zhiyun.SOURCES}
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
    auto = (
        bool(payload.get("zhiyun_auto_fetch", cfg.get("zhiyun_auto_fetch", False)))
        if "zhiyun_auto_fetch" in payload
        else bool(cfg.get("zhiyun_auto_fetch", False))
    )

    cfg["schedule_time"], cfg["backup_keep_days"], cfg["zhiyun_auto_fetch"] = st, keep, auto
    cfg["schedule_times"] = times
    # 落到机器本地覆盖文件（数据/本地配置.json），**绝不写 config.json** → git 工作区干净 → 一键更新可用。
    updates = {"schedule_time": st, "schedule_times": times, "backup_keep_days": keep, "zhiyun_auto_fetch": auto}
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
    return {
        "schedule_time": st,
        "schedule_times": times,
        "backup_keep_days": keep,
        "zhiyun_auto_fetch": auto,
        "ledger_share_path": cfg.get("ledger_share_path", ""),
        "note": note,
    }


# recompute 已由 refresh_pipeline 提供（秒级重算：缓存记录→重放→重算→重渲染）


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


def _diff_bu_config(old_bus: list, new_bus: list, old_alloc: bool = False, new_alloc: bool = False) -> list:
    """销售归属/BU 结构/分摊比例变化 → [(类别,摘要)]（old/new 均规范化 bus 列表）。"""

    def sale_map(bus):
        m = {}
        for b in bus:
            for s in b.get("销售") or []:
                m[str(s).strip()] = b["name"]
        return m

    om, nm = sale_map(old_bus), sale_map(new_bus)
    moves = [
        f"{s} {om.get(s) or '未归属'}→{nm.get(s) or '未归属'}"
        for s in sorted(set(om) | set(nm))
        if om.get(s) != nm.get(s)
    ]
    onames = {b["name"] for b in old_bus}
    nnames = {b["name"] for b in new_bus}
    oown = {b["name"]: "、".join(b.get("负责人") or []) for b in old_bus}
    nown = {b["name"]: "、".join(b.get("负责人") or []) for b in new_bus}
    struct = (
        [f"新增 BU {x}" for x in sorted(nnames - onames)]
        + [f"删除 BU {x}" for x in sorted(onames - nnames)]
        + [
            f"{x} 负责人改为「{nown.get(x) or '（空）'}」"
            for x in sorted(nnames & onames)
            if oown.get(x) != nown.get(x)
        ]
    )
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


def _manual_items_json(cfg: dict | None = None) -> str:
    """手填项目名列表 JSON（注入管理端 JS；与 config.manual_items 同步）。"""
    import json as _json

    items = [it["name"] for it in (cfg or {}).get("manual_items") or []] or [
        "营销人力成本",
        "管理人力成本",
        "研发人力成本",
        "财务费用补充",
        "PM人力成本",
        "VM人力成本",
        "实际内部译员成本",
        "税费损失",
        "技术流量成本",
        "其他（生产成本）",
        "其他损益",
    ]
    return _json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def _admin_page(dash_html: str, summary: dict, cfg: dict | None = None) -> str:  # noqa: ARG001
    """管道跑通后标记「管理端可进完整台」（truthy 写入 _state['admin_html']）。
    页面本体只在 static/admin/，此处不再生成整页 HTML。"""
    return "ready"


# refresh_pipeline.publish 拼 admin_html 时调用（避免 pipeline↔server 环依赖）
refresh_pipeline.set_admin_page_builder(_admin_page)


def _admin_static_html() -> str:
    """管理端完整台骨架：static/admin/admin.html（CSS/JS 外链；手填清单由 /admin/app.js 注入）。"""
    p = STATIC_DIR / "admin" / "admin.html"
    if not p.is_file():
        raise FileNotFoundError(f"缺少管理端静态页：{p}")
    return p.read_text(encoding="utf-8")


def _bootstrap_page() -> str:
    """首次部署引导页（F-02）：仅 static/admin/bootstrap.html。"""
    p = STATIC_DIR / "admin" / "bootstrap.html"
    if not p.is_file():
        raise FileNotFoundError(f"缺少引导页：{p}")
    return p.read_text(encoding="utf-8")


def admin_ui_source() -> str:
    """供测试搜锚点：admin.html + admin.js + admin.css 拼接（非运行路径）。"""
    parts = []
    for name in ("admin.html", "admin.js", "admin.css", "bootstrap.html"):
        p = STATIC_DIR / "admin" / name
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _run_reasons(report: dict) -> list[str]:
    """从最近一次管道运行日志（体检JSON=report）推导"为啥黄/红"。
    与 ingest._log_run 判定口径一致：fetch 走本地副本/无源、过期调整、定位键重复、库检查、备份。
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
        reasons.append(
            f"{adj['missing']} 条调整定位键失配未套用（源头行删了/改了金额，剔除或改值没生效）→ 去『异常处理·数据修正』人工复核"
        )
    dups = report.get("duplicate_locators") or {}
    n_dup_keys = sum(len(v) for v in dups.values()) if isinstance(dups, dict) else 0
    if n_dup_keys:
        reasons.append(
            f"{n_dup_keys} 组定位键重复（内容完全相同行）→ 写调整拒、重放标过期疑似；请在源表区分"
        )
    dbc = report.get("db_check") or {}
    if dbc and not dbc.get("ok", True):
        reasons.append(f"数据库 quick_check 异常：{dbc.get('detail') or 'unknown'} → 判红")
    bak = report.get("backup") or {}
    if bak.get("status") == "error" or bak.get("ok") is False:
        reasons.append(f"每日备份失败：{bak.get('detail') or bak.get('status')}")
    # 备份成功不写 run_reasons（避免绿时顶栏堆字）；状态在体检 JSON backup 字段，管理端可查
    return reasons


def _view_login_file():
    """看板登录：纯 static（B-P4 增补；错误由前端按 API 渲染）。会话态文档 → no-store。"""
    p = STATIC_DIR / "view_login.html"
    return _file_html_doc(p)


def _admin_login_file():
    """管理端登录：纯 static。会话态文档 → no-store。"""
    p = STATIC_DIR / "admin_login.html"
    return _file_html_doc(p)


# ---------------- FastAPI 应用 ----------------
def create_app(cfg, root=None) -> FastAPI:
    """组装 FastAPI：会话/中间件依赖 + 路由注册（路由体见 routes/）。"""
    app = FastAPI(title="甲骨易智能经营罗盘", docs_url=None, redoc_url=None, openapi_url=None)
    sec = _load_or_init_secret(cfg, root)
    # 确保账号文件存在（部署零配置）
    accounts.load_accounts(cfg, root, create=True)
    # 静态 CSS/JS（展示层外置；内容来自 theme/render 原样抽取）
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
            _BU_NAV_LINK_TPL.format(
                href=quote(n),
                current_attrs=(' aria-current="page" style="border-color:var(--blue)"' if n == current else ""),
                name=esc(n),
            )
            for n in existing
        )
        return _BU_NAV_TPL.format(aria_label="我的 BU 分页", label="我的 BU", links=links)

    def _set_vcookie(resp, account: str):
        resp.set_cookie(VCOOKIE, _make_token(sec, account), max_age=SESSION_TTL, httponly=True, samesite="lax")
        return resp

    def _set_acookie(resp, account: str):
        resp.set_cookie(COOKIE, _make_token(sec, account), max_age=SESSION_TTL, httponly=True, samesite="lax")
        return resp

    def _main_shell():
        """整体页固定 shell → fragments（B-P5 无 SSR 回退开关）。会话态文档 → no-store。"""
        p = STATIC_DIR / "shell.html"
        if not p.is_file():
            return _html_doc(_EMPTY_DATA_HTML, status_code=503)
        return _file_html_doc(p)

    def _bu_shell():
        p = STATIC_DIR / "shell-bu.html"
        if not p.is_file():
            return _html_doc(_EMPTY_DATA_HTML, status_code=503)
        return _file_html_doc(p)

    # 批次3：路由纯搬家到 routes.register_all（行为零变化）
    from types import SimpleNamespace
    from routes import register_all
    import export_png as _export_png

    register_all(
        app,
        SimpleNamespace(
            cfg=cfg,
            root=root,
            user=_user,
            vacct=_vacct,
            vacc_row=_vacc_row,
            can_view_main=_can_view_main,
            can_view_bu=_can_view_bu,
            bu_switcher_html=_bu_switcher_html,
            set_vcookie=_set_vcookie,
            set_acookie=_set_acookie,
            main_shell=_main_shell,
            bu_shell=_bu_shell,
            view_login_file=_view_login_file,
            admin_login_file=_admin_login_file,
            admin_static_html=_admin_static_html,
            bootstrap_page=_bootstrap_page,
            manual_items_json=_manual_items_json,
            html_doc=_html_doc,
            file_html_doc=_file_html_doc,
            audit=_audit,
            diff_accounts=_diff_accounts,
            diff_bu_config=_diff_bu_config,
            run_reasons=_run_reasons,
            start_refresh_async=start_refresh_async,
            recompute=recompute,
            get_schedule_times=get_schedule_times,
            normalize_schedule_times=normalize_schedule_times,
            save_settings=save_settings,
            read_zhiyun_creds=read_zhiyun_creds,
            save_zhiyun_creds=save_zhiyun_creds,
            read_zhiyun_conn=read_zhiyun_conn,
            save_zhiyun_conn=save_zhiyun_conn,
            screenshot_png=_export_png.screenshot_png,
            HIDE_PW_STYLE=_HIDE_PW_STYLE,
            WRAP_OPEN=_WRAP_OPEN,
            DEFAULT_PW=DEFAULT_PW,
            BU_NAV_TPL=_BU_NAV_TPL,
            BU_NAV_LINK_TPL=_BU_NAV_LINK_TPL,
            EDITABLE_SETTINGS=EDITABLE_SETTINGS,
        ),
    )
    return app


import export_png as _export_png

_screenshot_png = _export_png.screenshot_png


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
        except Exception as e:
            # 看门狗标记清理失败不挡服务；下次更新仍可重试。记一行便于排障。
            print(f"[server] clear_rollback_marker 跳过：{type(e).__name__}: {e}")

    threading.Thread(target=_confirm_update_good, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
