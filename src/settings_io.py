#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设置/智云/计划任务 IO（54.13 从 server 纯搬家）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import loaders
import subprocess

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

EDITABLE_SETTINGS = (
    "schedule_time",
    "backup_keep_days",
    "zhiyun_auto_fetch",
    "overall_see_salary",
    "run_log_keep_days",
    "disk_free_min_ratio",
)

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

CRON_BEGIN = "# BEGIN kanban-schedule"

CRON_END = "# END kanban-schedule"

def _cron_block_for_times(times: list[str], root=None) -> str:
    """生成 crontab 哨兵段正文（含 BEGIN/END）。

    任务书60：刷新已迁入服务进程 ScheduleLoop，本段**不再**注册 run.py --scheduled。
    保留哨兵 + 注释，便于 register_schedule.sh / sync_schedule 清掉旧机器上的刷新 cron 行。
    times 参数保留签名兼容（管理端仍传时间点列表），仅写入注释展示。
    """
    times_s = "、".join(times) if times else "—"
    lines = [
        CRON_BEGIN,
        "# managed by 看板正式程序 _linux_sync_schedule / register_schedule.sh",
        "# 任务书60：每日刷新已迁入服务进程 ScheduleLoop（serve 内 daemon），",
        f"# 本段故意无命令；当前配置时间点仅作备忘：{times_s}",
        "# 勿再添加 run.py --scheduled（独立进程不写 serve 内存 _state）。",
        CRON_END,
    ]
    return "\n".join(lines) + "\n"

def _strip_cron_sentinel(text: str) -> str:
    """去掉旧 kanban-schedule 哨兵段，保留用户其它 cron 行。"""
    out, skip = [], False
    for line in (text or "").splitlines():
        if line.strip() == CRON_BEGIN:
            skip = True
            continue
        if line.strip() == CRON_END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip("\n")

def _linux_sync_schedule(times: list[str], root=None) -> str:
    """Linux：重写 crontab 哨兵段（清旧 --scheduled；段内无刷新命令）。
    best-effort：失败不打断保存，提示重跑 deploy/linux/register_schedule.sh。"""

    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15)
        old = r.stdout if r.returncode == 0 else ""
        stripped = _strip_cron_sentinel(old)
        block = _cron_block_for_times(times, root)
        new_text = (stripped + "\n" if stripped else "") + block
        w = subprocess.run(["crontab", "-"], input=new_text, capture_output=True, text=True, timeout=15)
        if w.returncode != 0:
            err = (w.stderr or w.stdout or "").strip()[:120]
            return f"；⚠cron 同步失败（{err or '未知'}）——请重跑 bash deploy/linux/register_schedule.sh"
    except Exception as e:
        return f"；⚠cron 同步出错（{e}）——请重跑 bash deploy/linux/register_schedule.sh"
    return (
        f"；cron 哨兵已同步（刷新改进程内 ScheduleLoop；配置时间点 "
        f"{'、'.join(times) if times else '—'} 仅备忘）"
    )

def sync_schedule(times: list[str], root=None) -> str:
    """任务书54·D / 60：Linux 重写哨兵（清旧刷新 cron）；其它平台 no-op 提示。
    生产每日刷新 = 服务内 ScheduleLoop；cron 哨兵仅作迁移清场，无 --scheduled 命令。"""
    import sys

    if sys.platform.startswith("linux"):
        return _linux_sync_schedule(times, root)
    times_s = "、".join(times) if times else "—"
    return (
        f"（本机非 Linux 部署平台：{len(times)} 个时间点（{times_s}）由服务内 ScheduleLoop 生效；"
        "上 Ubuntu 后请跑 deploy/linux/register_schedule.sh 清旧 cron 刷新行）"
    )

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
    from secure_io import write_private_text

    write_private_text(p, json.dumps(d, ensure_ascii=False, indent=2))
    return True

def read_zhiyun_conn(cfg, root=None) -> dict:
    """读智云连接配置的**生效值**（内置默认 ZHIYUN_DEFAULTS + 本地覆盖合并后）：服务器地址 + 四表ID。"""
    from ingest import fetch_zhiyun

    zy = fetch_zhiyun._load_zhiyun_cfg(cfg, root)
    tables = {s: str(((zy.get("tables") or {}).get(s) or {}).get("worksheetId", "")) for s in fetch_zhiyun.SOURCES}
    return {"base_url": zy.get("base_url", ""), "tables": tables}

def _apply_zhiyun_table_overrides(over: dict, tables: dict, defaults: dict, sources) -> dict:
    """按四表ID写覆盖层；与默认相同则删覆盖。"""
    for s in sources:
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
    return over


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
    over = _apply_zhiyun_table_overrides(d.get("tables") or {}, tables, defaults, fetch_zhiyun.SOURCES)
    if over:
        d["tables"] = over
    else:
        d.pop("tables", None)
    if base_url != before["base_url"]:
        d["md_pss_id"] = ""  # 换服务器旧 token 必失效，强制重登
    from secure_io import write_private_text

    write_private_text(p, json.dumps(d, ensure_ascii=False, indent=2))
    after = read_zhiyun_conn(cfg, root)
    return after != before

def _parse_schedule_times_payload(cfg, payload: dict) -> tuple[list[str], str, bool]:
    """解析 schedule_times/schedule_time；返回 (times, st, changed_times)。"""
    changed_times = ("schedule_times" in payload) or ("schedule_time" in payload)
    if "schedule_times" in payload:
        times = normalize_schedule_times(payload["schedule_times"])
    elif "schedule_time" in payload:
        times = normalize_schedule_times(payload["schedule_time"])
    else:
        times = get_schedule_times(cfg)
    return times, times[0], changed_times


def _parse_backup_keep_days(cfg, payload: dict) -> int:
    if "backup_keep_days" in payload:
        try:
            keep = int(payload.get("backup_keep_days"))
        except (TypeError, ValueError):
            raise ValueError("备份保留天数须为整数") from None
    else:
        keep = int(cfg.get("backup_keep_days", 30))
    if not (1 <= keep <= 365):
        raise ValueError("备份保留天数须在 1~365 之间")
    return keep


def _apply_ledger_share_from_payload(cfg, payload: dict, updates: dict) -> None:
    """3.7.15：结构化 smb 优先；否则旧 ledger_share_path。"""
    import ledger_cifs as _lc

    structured = _lc.merge_structured(cfg, payload)
    if structured:
        for k, v in structured.items():
            cfg[k] = v
            updates[k] = v
        return
    if "ledger_share_path" in payload:
        lsp = str(payload.get("ledger_share_path") or "").strip()
        cfg["ledger_share_path"] = lsp
        updates["ledger_share_path"] = lsp


def _apply_optional_local_settings(cfg, payload: dict, updates: dict) -> None:
    """收单路径 / 日志保留 / 磁盘阈值 → cfg + updates（就地改）。"""
    _apply_ledger_share_from_payload(cfg, payload, updates)
    # 54.12 R-01：工资全端隐藏，不再接受 overall_see_salary 开关
    # 飞书 webhook 功能已删除：payload 中 feishu_webhook_url 一律忽略（不写 updates）
    cfg.pop("feishu_webhook_url", None)
    if "run_log_keep_days" in payload:
        try:
            rkd = int(payload.get("run_log_keep_days"))
        except (TypeError, ValueError):
            raise ValueError("运行日志保留天数须为整数") from None
        if not (30 <= rkd <= 3650):
            raise ValueError("运行日志保留天数须在 30~3650 之间")
        cfg["run_log_keep_days"] = rkd
        updates["run_log_keep_days"] = rkd
    if "disk_free_min_ratio" in payload:
        try:
            dfr = float(payload.get("disk_free_min_ratio"))
        except (TypeError, ValueError):
            raise ValueError("磁盘告警阈值须为 0~1 小数") from None
        if not (0.01 <= dfr <= 0.5):
            raise ValueError("磁盘告警阈值须在 1%~50% 之间")
        cfg["disk_free_min_ratio"] = dfr
        updates["disk_free_min_ratio"] = dfr


def _resolve_zhiyun_creds_update(cfg, root, zu_in, zp_in) -> str:
    """解析智云账号/密码更新意图；返回 cred_note 或抛 ValueError。"""
    cur = read_zhiyun_creds(cfg, root)
    new_user = str(zu_in).strip() if zu_in is not None else str(cur.get("username") or "")
    # 留空不改：None 或 "" → 保留已存密码
    new_pw = str(cur.get("password") or "") if zp_in is None or str(zp_in) == "" else str(zp_in)
    if not new_user and not new_pw:
        raise ValueError("智云账号和密码不能都为空")
    if not new_pw:
        raise ValueError("请先设置智云密码（留空表示不改；当前尚未设置）")
    if not new_user:
        raise ValueError("智云账号不能为空")
    if save_zhiyun_creds(cfg, root, new_user, new_pw):
        return "；智云账号已更新（下次更新自动用新账号登录）"
    return ""


def _resolve_zhiyun_conn_update(cfg, root, payload: dict) -> str:
    """智云连接（base_url/表 ID）更新；返回 conn_note。"""
    if "zhiyun_base_url" not in payload and "zhiyun_tables" not in payload:
        return ""
    cur = read_zhiyun_conn(cfg, root)
    bu = payload.get("zhiyun_base_url", cur["base_url"])
    tb = dict(cur["tables"])
    for k, v in (payload.get("zhiyun_tables") or {}).items():
        if k in tb:
            tb[k] = v
    if save_zhiyun_conn(cfg, root, bu, tb):
        return "；智云连接配置已更新（下次更新生效）"
    return ""


def _apply_zhiyun_payload(cfg, root, payload: dict) -> tuple[str, str]:
    """智云账号+连接配置；返回 (cred_note, conn_note)。

    3.7.5：密码留空=不改已存值；仅当用户明确填入新密码时才更新。
    """
    zu_in, zp_in = payload.get("zhiyun_username"), payload.get("zhiyun_password")
    cred_note = ""
    if zu_in is not None or zp_in is not None:
        cred_note = _resolve_zhiyun_creds_update(cfg, root, zu_in, zp_in)
    return cred_note, _resolve_zhiyun_conn_update(cfg, root, payload)


def _apply_cifs_creds_if_needed(cfg, root, payload: dict, updates: dict) -> str:
    """3.7.15：仅密码变更 / username 真变更 / 显式 apply 时调脚本；写 password_set 标志。"""
    import ledger_cifs as _lc

    if not _lc.should_apply_credentials(payload, cfg):
        return ""
    user = str(
        payload.get(_lc.KEY_USERNAME) if _lc.KEY_USERNAME in payload else cfg.get(_lc.KEY_USERNAME) or ""
    ).strip()
    if not user:
        user = str(cfg.get(_lc.KEY_USERNAME) or "").strip()
    if not user:
        raise ValueError("更新共享盘凭据须填写账号")
    pw = payload.get("ledger_smb_password")
    pw_s = None if pw is None or str(pw) == "" else str(pw)
    server = str(cfg.get(_lc.KEY_SERVER) or "")
    share = str(cfg.get(_lc.KEY_SHARE) or "")
    mount_root = str(cfg.get(_lc.KEY_MOUNT_ROOT) or _lc.DEFAULT_MOUNT_ROOT)
    try:
        _lc.run_cifs_apply(
            username=user,
            password=pw_s,
            server=server,
            share=share,
            mount_root=mount_root,
        )
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    # 成功：本地配置记 password_set（GET 不读 root 0600 正文）
    if pw_s is not None:
        cfg[_lc.KEY_PASSWORD_SET] = True
        updates[_lc.KEY_PASSWORD_SET] = True
    return "；台账共享凭据已更新（本机 cred，未写入配置库）"


def save_settings(cfg, root, payload: dict) -> dict:
    """校验并落盘设置（支持各卡就近保存：只传要改的字段即可）。
    改运行中 cfg + 重写 config.json。Windows 上改更新时间会顺手同步计划任务（多时间点=多任务）。"""
    times, st, changed_times = _parse_schedule_times_payload(cfg, payload)
    keep = _parse_backup_keep_days(cfg, payload)
    auto = (
        bool(payload.get("zhiyun_auto_fetch", cfg.get("zhiyun_auto_fetch", False)))
        if "zhiyun_auto_fetch" in payload
        else bool(cfg.get("zhiyun_auto_fetch", False))
    )

    cfg["schedule_time"], cfg["backup_keep_days"], cfg["zhiyun_auto_fetch"] = st, keep, auto
    cfg["schedule_times"] = times
    # 落到机器本地覆盖文件（数据/本地配置.json），**绝不写 config.json** → git 工作区干净 → 一键更新可用。
    updates = {"schedule_time": st, "schedule_times": times, "backup_keep_days": keep, "zhiyun_auto_fetch": auto}
    _apply_optional_local_settings(cfg, payload, updates)
    # 先 apply（可能写 password_set），再落盘；密码正文绝不写本地配置
    cred_note, conn_note = _apply_zhiyun_payload(cfg, root, payload)
    cifs_note = _apply_cifs_creds_if_needed(cfg, root, payload, updates)
    loaders.write_local_config(cfg, root, updates)
    note = "已保存" + cred_note + conn_note + cifs_note
    # 仅当本次真的提交了更新时间时才动计划任务/cron（各卡就近保存；平台分支见 sync_schedule）
    if changed_times:
        note += sync_schedule(times, root)
    import ledger_cifs as _lc

    return {
        "schedule_time": st,
        "schedule_times": times,
        "backup_keep_days": keep,
        "zhiyun_auto_fetch": auto,
        "ledger_share_path": cfg.get("ledger_share_path", ""),
        _lc.KEY_SERVER: cfg.get(_lc.KEY_SERVER, ""),
        _lc.KEY_SHARE: cfg.get(_lc.KEY_SHARE, ""),
        _lc.KEY_RELPATH: cfg.get(_lc.KEY_RELPATH, ""),
        _lc.KEY_USERNAME: cfg.get(_lc.KEY_USERNAME, ""),
        _lc.KEY_MOUNT_ROOT: cfg.get(_lc.KEY_MOUNT_ROOT, _lc.DEFAULT_MOUNT_ROOT),
        "overall_see_salary": False,  # 54.12 R-01 已废止开关，固定 False 兼容旧前端
        "run_log_keep_days": int(cfg.get("run_log_keep_days", 365) or 365),
        "disk_free_min_ratio": float(cfg.get("disk_free_min_ratio", 0.10) or 0.10),
        "note": note,
    }

