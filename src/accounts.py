#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板账号表（迭代 15 / v8.0）：读/写/校验 数据/看板账号.json。

设计（明昊 2026-07-11 拍板）：
- 账号与 BU 解耦：账号绑定「能看什么」= 权限 ∈ {管理员, 整体, 某 BU 名}；
- 一个 BU 可挂多个账号；账号名唯一；密码明文（管理员端可见可改，看的人可自改）；
- 存 JSON 不开库（凭据不是业务数据，且 看板.db 每日备份会副本扩散）；
- 缺文件 → 自动 seed 默认表（部署零配置）；git 里只有 docs/看板账号样例.json（合成名）。

铁律：真实人名只进 数据/ 本地文件；代码默认 seed / 测试 / 样例一律合成名。
口令比较一律 bytes（铁律 13）。
"""
from __future__ import annotations

import hmac
import json
import time
from pathlib import Path

import loaders

CONFIG_NAME = "看板账号.json"

PERM_ADMIN = "管理员"
PERM_MAIN = "整体"  # 与 bu.MAIN_ACCOUNT 同字面——整体页权限保留字

# 总账号（主管理员登录名）：不可删除、不可改登录名；改权限也不影响「总账号」身份。
# 部署机缺 看板账号.json 时 seed 会建这个号，否则无人能进 /admin。
MASTER_ACCOUNT = "lushasha"

# 初始密码（未改过的行黄标提醒）
DEFAULT_ADMIN_PW = "kanban2026"
DEFAULT_VIEW_PW = "8888"
INITIAL_PASSWORDS = frozenset({DEFAULT_ADMIN_PW, DEFAULT_VIEW_PW})

# 部署零配置默认表（合成显示名；真实名单只写 数据/ 本地文件）
# 账号 id 用产品约定的拼音/角色名（lushasha=管理员端登录号，明昊拍板）
DEFAULT_ACCOUNTS = [
    {"账号": MASTER_ACCOUNT, "显示名": "管理员", "权限": PERM_ADMIN, "密码": DEFAULT_ADMIN_PW},
    {"账号": "overall", "显示名": "整体账号", "权限": PERM_MAIN, "密码": DEFAULT_VIEW_PW},
    {"账号": "bu_alpha", "显示名": "甲BU账号", "权限": "数据", "密码": DEFAULT_VIEW_PW},
    {"账号": "bu_beta", "显示名": "乙BU账号", "权限": "游戏", "密码": DEFAULT_VIEW_PW},
    {"账号": "bu_gamma1", "显示名": "丙BU账号甲", "权限": "营销", "密码": DEFAULT_VIEW_PW},
    {"账号": "bu_gamma2", "显示名": "丙BU账号乙", "权限": "营销", "密码": DEFAULT_VIEW_PW},
]


def config_path(cfg: dict, root: Path | None = None) -> Path:
    return loaders.data_dir(cfg, root) / CONFIG_NAME


def is_initial_password(pw: str | None) -> bool:
    """密码仍是初始值（8888 / kanban2026）→ 管理端黄标。"""
    return (pw or "") in INITIAL_PASSWORDS


def is_master_account(acct: str | None) -> bool:
    """是否总账号（登录名固定为 MASTER_ACCOUNT，与显示名/当前权限无关）。"""
    return str(acct or "").strip() == MASTER_ACCOUNT


def _norm_one(raw: dict) -> dict | None:
    """校验并规范化一条账号；不合格 → None。"""
    if not isinstance(raw, dict):
        return None
    acct = str(raw.get("账号") or "").strip()
    if not acct:
        return None
    perm = str(raw.get("权限") or "").strip()
    if not perm:
        return None
    # 权限=管理员/整体/任意非空 BU 名（BU 是否存在由登录时再查；允许先建账号后配 BU）
    display = str(raw.get("显示名") or acct).strip() or acct
    pw = str(raw.get("密码") if raw.get("密码") is not None else DEFAULT_VIEW_PW)
    last = str(raw.get("最后登录") or "").strip() or None
    out = {"账号": acct, "显示名": display, "权限": perm, "密码": pw}
    if last:
        out["最后登录"] = last
    return out


def _write(path: Path, accounts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 落盘只保留规范字段
    rows = []
    for a in accounts:
        row = {"账号": a["账号"], "显示名": a["显示名"], "权限": a["权限"], "密码": a["密码"]}
        if a.get("最后登录"):
            row["最后登录"] = a["最后登录"]
        rows.append(row)
    path.write_text(json.dumps({"accounts": rows}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def seed_defaults(cfg: dict, root: Path | None = None) -> list[dict]:
    """写默认账号表并返回规范化列表。"""
    rows = [_norm_one(a) for a in DEFAULT_ACCOUNTS]
    rows = [r for r in rows if r]
    _write(config_path(cfg, root), rows)
    return rows


def load_accounts(cfg: dict, root: Path | None = None, *, create: bool = True) -> list[dict]:
    """读账号表。缺文件且 create=True → seed 默认表；坏 JSON / 无有效条目且 create → seed。"""
    p = config_path(cfg, root)
    if not p.exists():
        return seed_defaults(cfg, root) if create else []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return seed_defaults(cfg, root) if create else []
    items = raw.get("accounts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return seed_defaults(cfg, root) if create else []
    out, seen = [], set()
    for it in items:
        v = _norm_one(it)
        if not v or v["账号"] in seen:
            continue
        seen.add(v["账号"])
        out.append(v)
    if not out and create:
        return seed_defaults(cfg, root)
    return out


def save_accounts(cfg: dict, root: Path | None, accounts: list) -> list[dict]:
    """管理端保存：校验 → 规范化 → 落盘。
    - 账号名必填且唯一；权限必填；
    - 密码：条目带「密码」字段（含空串）则以之为准；不带则沿用已存（新账号无旧值→初始 8888）；
    - 最后登录：客户端传来的忽略，沿用已存（只由 mark_login 写）；
    - 总账号 MASTER_ACCOUNT：若库中已有则不可删、不可改登录名；至少保留一个「管理员」。
    返回落盘后的列表；校验失败抛 ValueError。"""
    existing = {a["账号"]: a for a in load_accounts(cfg, root, create=False)}
    out, seen = [], set()
    for raw in accounts if isinstance(accounts, list) else []:
        if not isinstance(raw, dict):
            continue
        acct = str(raw.get("账号") or "").strip()
        if not acct or acct in seen:
            continue
        perm = str(raw.get("权限") or "").strip()
        if not perm:
            continue
        seen.add(acct)
        display = str(raw.get("显示名") or acct).strip() or acct
        if "密码" in raw and raw["密码"] is not None:
            pw = str(raw["密码"])
        else:
            pw = existing.get(acct, {}).get("密码", DEFAULT_VIEW_PW)
        if not pw:
            pw = DEFAULT_VIEW_PW
        # 总账号：登录名固定且权限强制管理员（界面不提供下拉）
        if is_master_account(acct):
            perm = PERM_ADMIN
        row = {"账号": acct, "显示名": display, "权限": perm, "密码": pw}
        last = existing.get(acct, {}).get("最后登录")
        if last:
            row["最后登录"] = last
        out.append(row)
    if not any(a["权限"] == PERM_ADMIN for a in out):
        raise ValueError("至少保留一个「管理员」权限账号")
    # 总账号：曾存在则必须仍在表中（可改显示名/密码，不可删、不可改登录名）
    if MASTER_ACCOUNT in existing and MASTER_ACCOUNT not in {a["账号"] for a in out}:
        raise ValueError(f"总账号「{MASTER_ACCOUNT}」不可删除（否则部署后可能无人能进管理端）")
    _write(config_path(cfg, root), out)
    return out


def find_account(cfg: dict, root: Path | None, account: str) -> dict | None:
    account = (account or "").strip()
    if not account:
        return None
    for a in load_accounts(cfg, root):
        if a["账号"] == account:
            return a
    return None


def verify_password(stored: str | None, pw: str) -> bool:
    """明文口令比对；一律 bytes（铁律 13：中文密码不 500）。"""
    return hmac.compare_digest((stored or "").encode(), (pw or "").encode())


def authenticate(cfg: dict, root: Path | None, account: str, password: str) -> dict | None:
    """账号+密码校验；成功返回账号条目，失败 None。账号不存在与密码错同一返回（不泄存在性）。"""
    acc = find_account(cfg, root, account)
    if not acc:
        # 仍做一次假比较，耗时近似（防时序侧信道；明文场景意义有限但保持习惯）
        verify_password(DEFAULT_VIEW_PW, password)
        return None
    if not verify_password(acc.get("密码"), password):
        return None
    return acc


def mark_login(cfg: dict, root: Path | None, account: str) -> None:
    """登录成功写最后登录时间。"""
    rows = load_accounts(cfg, root, create=False)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    changed = False
    for a in rows:
        if a["账号"] == account:
            a["最后登录"] = stamp
            changed = True
            break
    if changed:
        _write(config_path(cfg, root), rows)


def change_password(cfg: dict, root: Path | None, account: str,
                    old_pw: str, new_pw: str) -> str | None:
    """自改密码：验旧设新。成功返回 None；失败返回错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    acc = find_account(cfg, root, account)
    if not acc:
        return "账号不存在"
    if not verify_password(acc.get("密码"), old_pw):
        return "旧密码不正确"
    rows = load_accounts(cfg, root, create=False)
    for a in rows:
        if a["账号"] == account:
            a["密码"] = new_pw
            break
    _write(config_path(cfg, root), rows)
    return None


def set_password(cfg: dict, root: Path | None, account: str, new_pw: str) -> str | None:
    """管理员直接设某账号密码（不验旧）。成功 None；失败错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    rows = load_accounts(cfg, root, create=False)
    found = False
    for a in rows:
        if a["账号"] == account:
            a["密码"] = new_pw
            found = True
            break
    if not found:
        return "账号不存在"
    _write(config_path(cfg, root), rows)
    return None


def role_of(acc: dict | None) -> str | None:
    """返回权限字段；无账号 → None。"""
    return (acc or {}).get("权限")


def is_admin(acc: dict | None) -> bool:
    return role_of(acc) == PERM_ADMIN


def is_main(acc: dict | None) -> bool:
    return role_of(acc) == PERM_MAIN


def bu_name_of(acc: dict | None) -> str | None:
    """权限是某 BU 名时返回该名；管理员/整体/无 → None。"""
    r = role_of(acc)
    if not r or r in (PERM_ADMIN, PERM_MAIN):
        return None
    return r


def public_row(acc: dict, *, with_password: bool = False) -> dict:
    """接口下发用：默认不含密码；with_password 仅管理员会话。"""
    out = {
        "账号": acc["账号"],
        "显示名": acc.get("显示名") or acc["账号"],
        "权限": acc["权限"],
        "最后登录": acc.get("最后登录") or "",
        "初始密码": is_initial_password(acc.get("密码")),
    }
    if with_password:
        out["密码"] = acc.get("密码") or ""
    return out
