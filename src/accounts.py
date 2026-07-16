#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板账号表（迭代 15 / v8.0）：读/写/校验 数据/看板账号.json。

设计（明昊 2026-07-11 拍板 · 2026-07-12 v8.6 扩多 BU）：
- 账号与 BU 解耦：账号绑定「能看什么」= 权限 ∈ {管理员, 整体, BU, 某 BU 名(旧)}；
  **v8.6 多 BU**：权限=BU 时可绑一组 BU（见 `可见BU` 列表）；整体=全部 BU + 全公司页；
  旧账号权限=单个 BU 名仍兼容（等价于绑定该一个 BU）。取用一律走 `bu_names_of`/`can_see_bu`。
- 一个 BU 可挂多个账号；账号名唯一；
- 任务书46·1：密码以 Argon2 哈希存「密码哈希」；兼容旧明文「密码」字段（登录成功即透明迁移）；
- 存 JSON 不开库（凭据不是业务数据，且 看板.db 每日备份会副本扩散）；
- 缺文件 → 自动 seed 默认表（部署零配置）；git 里只有 docs/看板账号样例.json（合成名）。

铁律：真实人名只进 数据/ 本地文件；代码默认 seed / 测试 / 样例一律合成名。
口令比较：哈希走 passlib；明文迁移路径一律 bytes（铁律 13）。
"""

from __future__ import annotations

import hmac
import json
import secrets
import string
import time
from pathlib import Path

import loaders

try:
    from passlib.hash import argon2 as _argon2
except ImportError:  # pragma: no cover
    _argon2 = None  # type: ignore

CONFIG_NAME = "看板账号.json"

PERM_ADMIN = "管理员"
PERM_MAIN = "整体"  # 与 bu.MAIN_ACCOUNT 同字面——整体页权限保留字

PERM_BU = "BU"  # v8.6 多 BU 绑定：权限=BU 时，可见范围看 可见BU 列表（旧账号权限=单个 BU 名仍兼容）


def _clean_bu_list(v) -> list[str]:
    """可见BU 名单清洗：列表/顿号·逗号分隔串 → 去空白、去「整体」保留字、去重（保序）。"""
    if isinstance(v, str):
        import re

        v = re.split(r"[、，,;；\n]", v)
    if not isinstance(v, (list, tuple)):
        return []
    out, seen = [], set()
    for x in v:
        s = str(x).strip()
        if s and s != PERM_MAIN and s not in seen:
            seen.add(s)
            out.append(s)
    return out


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


def _hash_password(plain: str) -> str:
    """明文 → Argon2 哈希串。"""
    if _argon2 is None:
        raise RuntimeError("passlib[argon2] 未安装，无法哈希密码")
    return _argon2.hash(plain or "")


def _verify_hash(pw_hash: str, plain: str) -> bool:
    if not pw_hash or _argon2 is None:
        return False
    try:
        return bool(_argon2.verify(plain or "", pw_hash))
    except (ValueError, TypeError):
        return False


def password_version_of(acc: dict | None) -> int:
    """会话踢出因子：改密自增。缺省 0。"""
    try:
        return int((acc or {}).get("密码版本") or 0)
    except (TypeError, ValueError):
        return 0


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
    # 哈希优先；否则保留明文（迁移期）
    pw_hash = str(raw.get("密码哈希") or "").strip()
    if "密码" in raw and raw["密码"] is not None:
        pw = str(raw["密码"])
    elif pw_hash:
        pw = ""
    else:
        pw = DEFAULT_VIEW_PW
    last = str(raw.get("最后登录") or "").strip() or None
    try:
        pw_ver = int(raw.get("密码版本") or 0)
    except (TypeError, ValueError):
        pw_ver = 0
    out = {
        "账号": acct,
        "显示名": display,
        "权限": perm,
        "密码": pw,
        "密码哈希": pw_hash,
        "密码版本": pw_ver,
    }
    if raw.get("初始密码") is True or (not pw_hash and is_initial_password(pw)):
        out["初始密码"] = True
    if perm == PERM_BU:  # 多 BU：权限=BU 时随附可见 BU 列表（旧账号权限=单个 BU 名不带此字段）
        out["可见BU"] = _clean_bu_list(raw.get("可见BU"))
    if last:
        out["最后登录"] = last
    return out


def _write(path: Path, accounts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 落盘：有哈希则不写明文；保留密码版本
    rows = []
    for a in accounts:
        row = {
            "账号": a["账号"],
            "显示名": a["显示名"],
            "权限": a["权限"],
            "密码版本": int(a.get("密码版本") or 0),
        }
        h = str(a.get("密码哈希") or "").strip()
        if h:
            row["密码哈希"] = h
            row["密码"] = ""  # 迁移后清空明文
        else:
            row["密码"] = a.get("密码") or DEFAULT_VIEW_PW
        if a.get("初始密码"):
            row["初始密码"] = True
        if a.get("权限") == PERM_BU:
            row["可见BU"] = _clean_bu_list(a.get("可见BU"))
        if a.get("最后登录"):
            row["最后登录"] = a["最后登录"]
        rows.append(row)
    path.write_text(json.dumps({"accounts": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    - 密码：条目带非空「密码」→ 只存哈希并自增密码版本；不带/空 → 沿用已存哈希或明文；
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
        old = existing.get(acct, {})
        # 总账号：登录名固定且权限强制管理员（界面不提供下拉）
        if is_master_account(acct):
            perm = PERM_ADMIN
        row = {
            "账号": acct,
            "显示名": display,
            "权限": perm,
            "密码": "",
            "密码哈希": str(old.get("密码哈希") or ""),
            "密码版本": password_version_of(old),
        }
        new_plain = None
        if "密码" in raw and raw["密码"] is not None and str(raw["密码"]) != "":
            # 仅当管理员明确写入新明文时才轮换（前端重置会先调 reset 再保存可带空）
            cand = str(raw["密码"])
            # 若与占位「********」或空哈希占位相同则忽略
            if cand not in ("********", "••••••••") and not cand.startswith("$argon2"):
                new_plain = cand
        if new_plain is not None:
            row["密码哈希"] = _hash_password(new_plain)
            row["密码"] = ""
            row["密码版本"] = password_version_of(old) + 1
            row["初始密码"] = is_initial_password(new_plain)
        else:
            # 沿用：优先哈希，否则旧明文（迁移前）
            if not row["密码哈希"] and old.get("密码"):
                row["密码"] = str(old.get("密码") or DEFAULT_VIEW_PW)
            if old.get("初始密码"):
                row["初始密码"] = True
            elif not row["密码哈希"] and is_initial_password(row.get("密码")):
                row["初始密码"] = True
            # 全新账号无旧记录
            if acct not in existing and not row["密码哈希"] and not row.get("密码"):
                row["密码哈希"] = _hash_password(DEFAULT_VIEW_PW)
                row["密码"] = ""
                row["初始密码"] = True
        if perm == PERM_BU:  # 多 BU：随权限=BU 存可见 BU 列表
            row["可见BU"] = _clean_bu_list(raw.get("可见BU"))
        last = old.get("最后登录")
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
    """明文口令比对；一律 bytes（铁律 13：中文密码不 500）。仅迁移路径使用。"""
    return hmac.compare_digest((stored or "").encode(), (pw or "").encode())


def verify_account_password(acc: dict | None, password: str) -> bool:
    """校验顺序：有哈希验哈希 → 无哈希验明文。"""
    if not acc:
        return False
    h = str(acc.get("密码哈希") or "").strip()
    if h:
        return _verify_hash(h, password)
    return verify_password(acc.get("密码"), password)


def _migrate_to_hash_inplace(rows: list[dict], account: str, plain: str) -> list[dict]:
    """登录成功后：写哈希、清空明文（透明迁移）。"""
    for a in rows:
        if a["账号"] == account:
            a["密码哈希"] = _hash_password(plain)
            a["密码"] = ""
            if is_initial_password(plain):
                a["初始密码"] = True
            else:
                a.pop("初始密码", None)
            break
    return rows


def authenticate(cfg: dict, root: Path | None, account: str, password: str) -> dict | None:
    """账号+密码校验；成功返回账号条目，失败 None。账号不存在与密码错同一返回（不泄存在性）。
    明文验证成功 → 立即写入哈希并清空明文（透明迁移）。"""
    acc = find_account(cfg, root, account)
    if not acc:
        # 仍做一次假比较，耗时近似（防时序侧信道）
        if _argon2 is not None:
            try:
                _verify_hash(_hash_password(DEFAULT_VIEW_PW), password)
            except Exception:
                verify_password(DEFAULT_VIEW_PW, password)
        else:
            verify_password(DEFAULT_VIEW_PW, password)
        return None
    if not verify_account_password(acc, password):
        return None
    # 透明迁移：仅明文路径
    if not str(acc.get("密码哈希") or "").strip() and acc.get("密码") is not None:
        rows = load_accounts(cfg, root, create=False)
        _migrate_to_hash_inplace(rows, account, password)
        _write(config_path(cfg, root), rows)
        acc = find_account(cfg, root, account) or acc
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


def change_password(cfg: dict, root: Path | None, account: str, old_pw: str, new_pw: str) -> str | None:
    """自改密码：验旧设新（只存哈希，密码版本+1）。成功返回 None；失败返回错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    acc = find_account(cfg, root, account)
    if not acc:
        return "账号不存在"
    if not verify_account_password(acc, old_pw):
        return "旧密码不正确"
    rows = load_accounts(cfg, root, create=False)
    for a in rows:
        if a["账号"] == account:
            a["密码哈希"] = _hash_password(new_pw)
            a["密码"] = ""
            a["密码版本"] = password_version_of(a) + 1
            a.pop("初始密码", None)
            if is_initial_password(new_pw):
                a["初始密码"] = True
            break
    _write(config_path(cfg, root), rows)
    return None


def set_password(cfg: dict, root: Path | None, account: str, new_pw: str) -> str | None:
    """管理员直接设某账号密码（不验旧；只存哈希，版本+1）。成功 None；失败错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    rows = load_accounts(cfg, root, create=False)
    found = False
    for a in rows:
        if a["账号"] == account:
            a["密码哈希"] = _hash_password(new_pw)
            a["密码"] = ""
            a["密码版本"] = password_version_of(a) + 1
            a.pop("初始密码", None)
            if is_initial_password(new_pw):
                a["初始密码"] = True
            found = True
            break
    if not found:
        return "账号不存在"
    _write(config_path(cfg, root), rows)
    return None


def generate_temp_password(length: int = 12) -> str:
    """一次性随机密码（管理员重置用，只显示一次）。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(8, length)))


def reset_password(cfg: dict, root: Path | None, account: str) -> tuple[str | None, str | None]:
    """管理员重置：生成随机密码写入哈希，返回 (plain_once, err)。"""
    plain = generate_temp_password()
    err = set_password(cfg, root, account, plain)
    if err:
        return None, err
    return plain, None


def role_of(acc: dict | None) -> str | None:
    """返回权限字段；无账号 → None。"""
    return (acc or {}).get("权限")


def is_admin(acc: dict | None) -> bool:
    return role_of(acc) == PERM_ADMIN


def is_main(acc: dict | None) -> bool:
    return role_of(acc) == PERM_MAIN


def bu_names_of(acc: dict | None) -> list[str]:
    """账号能看的 BU 名单（v8.6 多 BU）：
    管理员/整体 → []（见全部，另行处理）；权限=BU → `可见BU` 列表；
    权限=单个 BU 名（旧账号）→ [该名]。"""
    perm = role_of(acc)
    if not perm or perm in (PERM_ADMIN, PERM_MAIN):
        return []
    if perm == PERM_BU:
        return _clean_bu_list((acc or {}).get("可见BU"))
    return [perm]  # 旧账号：权限字段本身=单个 BU 名


def can_see_bu(acc: dict | None, name: str) -> bool:
    """账号是否可看指定 BU（多 BU：在其绑定名单内即可）。管理员/整体另行判 True。"""
    return name in bu_names_of(acc)


def bu_name_of(acc: dict | None) -> str | None:
    """兼容旧调用：返回账号绑定的第一个 BU 名（多 BU 取第一个）；管理员/整体/无 → None。"""
    names = bu_names_of(acc)
    return names[0] if names else None


def public_row(acc: dict, *, with_password: bool = False) -> dict:
    """接口下发用：默认不含密码。
    with_password（管理员会话）：不再下发明文；下发 has_hash + 占位，重置走 reset_password。"""
    has_hash = bool(str(acc.get("密码哈希") or "").strip())
    init = bool(acc.get("初始密码")) or (not has_hash and is_initial_password(acc.get("密码")))
    out = {
        "账号": acc["账号"],
        "显示名": acc.get("显示名") or acc["账号"],
        "权限": acc["权限"],
        "可见BU": bu_names_of(acc),  # 多 BU：绑定名单（管理员/整体为空）；旧单 BU 账号=[该名]
        "最后登录": acc.get("最后登录") or "",
        "初始密码": init,
        "密码版本": password_version_of(acc),
        "has_hash": has_hash,
    }
    if with_password:
        # 兼容旧前端字段名：不再给真实明文
        out["密码"] = "********" if has_hash else (acc.get("密码") or "")
    return out
