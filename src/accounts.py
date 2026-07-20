#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板账号表（迭代 15 / v8.0 · 任务书63·H-05 哈希存储）：读/写/校验 数据/看板账号.json。

设计（明昊 2026-07-11 拍板 · 2026-07-12 v8.6 扩多 BU · 2026-07-20 任务书63 恢复哈希）：
- 账号与 BU 解耦：账号绑定「能看什么」= 权限 ∈ {管理员, 整体, BU, 某 BU 名(旧)}；
  **v8.6 多 BU**：权限=BU 时可绑一组 BU（见 `可见BU` 列表）；整体=全部 BU + 全公司页；
  旧账号权限=单个 BU 名仍兼容（等价于绑定该一个 BU）。取用一律走 `bu_names_of`/`can_see_bu`。
- 一个 BU 可挂多个账号；账号名唯一；
- **密码哈希为真相源**（PBKDF2-HMAC-SHA256；管理端只可重置、不可查看明文）；
- **密码版本**保留：改密自增 → 旧会话 cookie 失效（改密踢会话）；
- **初始密码**布尔字段：seed/默认口令为 true，改密/重置后 false（管理端黄标）；
- 存 JSON 不开库（凭据不是业务数据，且 看板.db 每日备份会副本扩散）；
- 缺文件 → 自动 seed 默认表（部署零配置）；git 里只有 docs/看板账号样例.json（合成名）。
- 读到旧版明文「密码」字段 → 当场哈希写回（备份 `看板账号.json.bak-明文迁移-<日期>`）。

铁律：真实人名只进 数据/ 本地文件；代码默认 seed / 测试 / 样例一律合成名。
口令比较：哈希用 hmac.compare_digest；明文兜底比对一律 bytes（铁律 13）。
选型见 docs/madr/0019_password_hashing_pbkdf2.md。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
import time
from pathlib import Path

import loaders

CONFIG_NAME = "看板账号.json"

PERM_ADMIN = "管理员"
PERM_MAIN = "整体"  # 与 bu.MAIN_ACCOUNT 同字面——整体页权限保留字

PERM_BU = "BU"  # v8.6 多 BU 绑定：权限=BU 时，可见范围看 可见BU 列表（旧账号权限=单个 BU 名仍兼容）

# PBKDF2 参数（NIST SP 800-132 认可；迭代 ≥60 万）
_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERS = 600_000
_SALT_BYTES = 16


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


def hash_password(plain: str, *, iterations: int = _PBKDF2_ITERS) -> str:
    """明文 → 存储串 pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", (plain or "").encode("utf-8"), salt, int(iterations))
    return (
        f"{_PBKDF2_PREFIX}${int(iterations)}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(dk).decode('ascii')}"
    )


def verify_password_hash(stored_hash: str | None, plain: str) -> bool:
    """校验 PBKDF2 存储串与明文。格式非法 → False。"""
    s = str(stored_hash or "").strip()
    if not s.startswith(f"{_PBKDF2_PREFIX}$"):
        return False
    parts = s.split("$")
    if len(parts) != 4:
        return False
    _pref, iters_s, salt_b64, hash_b64 = parts
    try:
        iters = int(iters_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expect = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False
    if iters < 1 or not salt or not expect:
        return False
    got = hashlib.pbkdf2_hmac("sha256", (plain or "").encode("utf-8"), salt, iters)
    return hmac.compare_digest(got, expect)


def is_initial_password(pw: str | None) -> bool:
    """明文是否属于默认初始口令集合（8888 / kanban2026）→ 迁移时写 初始密码=true。"""
    return (pw or "") in INITIAL_PASSWORDS


def is_master_account(acct: str | None) -> bool:
    """是否总账号（登录名固定为 MASTER_ACCOUNT，与显示名/当前权限无关）。"""
    return str(acct or "").strip() == MASTER_ACCOUNT


def password_version_of(acc: dict | None) -> int:
    """会话踢出因子：改密 / logout 自增（任务书52·F-3 与改密共用同一版本位）。缺省 0。"""
    try:
        return int((acc or {}).get("密码版本") or 0)
    except (TypeError, ValueError):
        return 0


def generate_random_password(length: int = 10) -> str:
    """管理员重置用：字母+数字，长度默认 10。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(4, int(length))))


def bump_session_version(cfg: dict, root: Path | None, account: str) -> bool:
    """任务书52·F-3：logout 作废会话——账号「密码版本」+1（token 内 pw_ver 比对失败 → 401）。

    与 change_password / set_password 同一字段，重启后已退出会话仍不可复活（版本已写盘）。
    返回是否找到并更新了账号。
    """
    acct = str(account or "").strip()
    if not acct:
        return False
    rows = load_accounts(cfg, root, create=False)
    found = False
    for a in rows:
        if a.get("账号") == acct:
            a["密码版本"] = password_version_of(a) + 1
            found = True
            break
    if found:
        _write(config_path(cfg, root), rows)
    return found


def _disk_row(a: dict) -> dict:
    """落盘行：只写哈希 + 初始密码，不写明文。"""
    row = {
        "账号": a["账号"],
        "显示名": a["显示名"],
        "权限": a["权限"],
        "密码哈希": a.get("密码哈希") or hash_password(DEFAULT_VIEW_PW),
        "初始密码": bool(a.get("初始密码", False)),
        "密码版本": int(a.get("密码版本") or 0),
    }
    if a.get("权限") == PERM_BU:
        row["可见BU"] = _clean_bu_list(a.get("可见BU"))
    if a.get("最后登录"):
        row["最后登录"] = a["最后登录"]
    return row


def _write(path: Path, accounts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_disk_row(a) for a in accounts]
    path.write_text(json.dumps({"accounts": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backup_plain_migration(path: Path) -> Path | None:
    """明文迁移前备份；成功返回备份路径。"""
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d")
    bak = path.with_name(f"{path.name}.bak-明文迁移-{stamp}")
    n = 0
    while bak.exists():
        n += 1
        bak = path.with_name(f"{path.name}.bak-明文迁移-{stamp}-{n}")
    bak.write_bytes(path.read_bytes())
    return bak


def _norm_one(raw: dict) -> dict | None:  # noqa: C901  # 字段分支：明文迁移 / 哈希 / 默认口令
    """校验并规范化一条账号（内存态：含 密码哈希 / 初始密码）。不合格 → None。"""
    if not isinstance(raw, dict):
        return None
    acct = str(raw.get("账号") or "").strip()
    if not acct:
        return None
    perm = str(raw.get("权限") or "").strip()
    if not perm:
        return None
    display = str(raw.get("显示名") or acct).strip() or acct
    try:
        pw_ver = int(raw.get("密码版本") or 0)
    except (TypeError, ValueError):
        pw_ver = 0
    last = str(raw.get("最后登录") or "").strip() or None

    stored_hash = str(raw.get("密码哈希") or "").strip()
    plain = None
    if "密码" in raw and raw["密码"] is not None and str(raw["密码"]).strip() != "":
        plain = str(raw["密码"])
    initial_flag = raw.get("初始密码")
    needs_migrate = False
    if stored_hash.startswith(f"{_PBKDF2_PREFIX}$"):
        pw_hash = stored_hash
        if initial_flag is None:
            # 仅有哈希无初始标志：保守 false（除非调用方后续设置）
            initial = False
        else:
            initial = bool(initial_flag)
    elif plain is not None:
        pw_hash = hash_password(plain)
        initial = bool(initial_flag) if initial_flag is not None else is_initial_password(plain)
        needs_migrate = True
    else:
        # 无哈希无明文：seed 默认看端口令
        plain = DEFAULT_VIEW_PW
        pw_hash = hash_password(plain)
        initial = True
        needs_migrate = True

    out = {
        "账号": acct,
        "显示名": display,
        "权限": perm,
        "密码哈希": pw_hash,
        "初始密码": initial,
        "密码版本": pw_ver,
        "_needs_migrate": needs_migrate,
    }
    if perm == PERM_BU:
        out["可见BU"] = _clean_bu_list(raw.get("可见BU"))
    if last:
        out["最后登录"] = last
    return out


def seed_defaults(cfg: dict, root: Path | None = None) -> list[dict]:
    """写默认账号表并返回规范化列表（哈希 + 初始密码=true）。"""
    rows = []
    for a in DEFAULT_ACCOUNTS:
        plain = str(a.get("密码") or DEFAULT_VIEW_PW)
        rows.append(
            {
                "账号": a["账号"],
                "显示名": a["显示名"],
                "权限": a["权限"],
                "密码哈希": hash_password(plain),
                "初始密码": True,
                "密码版本": 0,
            }
        )
    _write(config_path(cfg, root), rows)
    return rows


def load_accounts(cfg: dict, root: Path | None = None, *, create: bool = True) -> list[dict]:
    """读账号表。缺文件且 create=True → seed 默认表；坏 JSON / 无有效条目且 create → seed。

    任务书63·H-05：读到旧明文「密码」→ 哈希写回并备份 bak-明文迁移-日期。
    """
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
    need_rewrite = False
    for it in items:
        v = _norm_one(it)
        if not v or v["账号"] in seen:
            continue
        if v.pop("_needs_migrate", False):
            need_rewrite = True
        # 盘上仍有明文「密码」键 → 必须重写去掉
        if isinstance(it, dict) and "密码" in it and str(it.get("密码") or "").strip():
            need_rewrite = True
        seen.add(v["账号"])
        out.append(v)
    if not out and create:
        return seed_defaults(cfg, root)
    if need_rewrite and out:
        _backup_plain_migration(p)
        _write(p, out)
    return out


def _normalize_account_row(raw: dict, existing: dict) -> dict | None:  # noqa: C901  # 保存路径：改密/沿用/新号
    """管理端保存单条规范化；无效返回 None。

    - 带非空「密码」→ 哈希化并 初始密码= is_initial_password(plain)（除非显式传 初始密码）
    - 不带密码 → 沿用已存哈希与初始标志；新账号无旧值 → 默认 8888 哈希 + 初始 true
    """
    acct = str(raw.get("账号") or "").strip()
    if not acct:
        return None
    perm = str(raw.get("权限") or "").strip()
    if not perm:
        return None
    display = str(raw.get("显示名") or acct).strip() or acct
    old = existing.get(acct, {})
    if is_master_account(acct):
        perm = PERM_ADMIN
    pw_ver = password_version_of(old)
    pw_changed = False
    if "密码" in raw and raw["密码"] is not None and str(raw["密码"]).strip() != "":
        plain = str(raw["密码"])
        pw_hash = hash_password(plain)
        # 新口令是否属默认初始集合，决定黄标（忽略客户端残留 初始密码=true）
        initial = is_initial_password(plain)
        if acct in existing:
            if not verify_password_hash(old.get("密码哈希"), plain):
                pw_changed = True
        else:
            pw_changed = False  # 新账号不 + 版本
    else:
        if old.get("密码哈希"):
            pw_hash = old["密码哈希"]
            initial = bool(old.get("初始密码", False))
        else:
            plain = DEFAULT_VIEW_PW
            pw_hash = hash_password(plain)
            initial = True
        # 未改口令时：客户端可显式改 初始密码 标志（罕见）；否则沿用已存
        if "初始密码" in raw and raw.get("初始密码") is not None:
            initial = bool(raw.get("初始密码"))
    if pw_changed:
        pw_ver = pw_ver + 1
    row = {
        "账号": acct,
        "显示名": display,
        "权限": perm,
        "密码哈希": pw_hash,
        "初始密码": initial,
        "密码版本": pw_ver,
    }
    if perm == PERM_BU:
        row["可见BU"] = _clean_bu_list(raw.get("可见BU"))
    last = old.get("最后登录")
    if last:
        row["最后登录"] = last
    return row


def save_accounts(cfg: dict, root: Path | None, accounts: list) -> list[dict]:
    """管理端保存：校验 → 规范化 → 落盘（只写哈希）。
    - 账号名必填且唯一；权限必填；
    - 密码：条目带非空「密码」则以之为新口令并哈希；不带则沿用已存哈希；
    - 密码变更时「密码版本」+1（改密踢会话）；
    - 最后登录：客户端传来的忽略，沿用已存（只由 mark_login 写）；
    - 总账号 MASTER_ACCOUNT：若库中已有则不可删、不可改登录名；至少保留一个「管理员」。
    返回落盘后的列表；校验失败抛 ValueError。"""
    existing = {a["账号"]: a for a in load_accounts(cfg, root, create=False)}
    out, seen = [], set()
    for raw in accounts if isinstance(accounts, list) else []:
        if not isinstance(raw, dict):
            continue
        row = _normalize_account_row(raw, existing)
        if not row or row["账号"] in seen:
            continue
        seen.add(row["账号"])
        out.append(row)
    if not any(a["权限"] == PERM_ADMIN for a in out):
        raise ValueError("至少保留一个「管理员」权限账号")
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
    """兼容入口：若 stored 像 PBKDF2 串则走哈希比对；否则明文 bytes 比对（仅测试/过渡）。"""
    s = str(stored or "")
    if s.startswith(f"{_PBKDF2_PREFIX}$"):
        return verify_password_hash(s, pw)
    return hmac.compare_digest(s.encode(), (pw or "").encode())


# 登录失败路径用固定盐短迭代，避免「账号不存在」零耗时（非生产强度，仅时序占位）
_DUMMY_HASH = (
    f"{_PBKDF2_PREFIX}$1$"
    f"{base64.urlsafe_b64encode(b'kanban-dummy-salt').decode('ascii')}$"
    f"{base64.urlsafe_b64encode(hashlib.pbkdf2_hmac('sha256', b'x', b'kanban-dummy-salt', 1)).decode('ascii')}"
)


def authenticate(cfg: dict, root: Path | None, account: str, password: str) -> dict | None:
    """账号+密码校验；成功返回账号条目，失败 None。账号不存在与密码错同一返回（不泄存在性）。"""
    acc = find_account(cfg, root, account)
    if not acc:
        verify_password_hash(_DUMMY_HASH, password)
        return None
    stored = acc.get("密码哈希") or ""
    if not stored or not verify_password_hash(stored, password):
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


def change_password(cfg: dict, root: Path | None, account: str, old_pw: str, new_pw: str) -> str | None:
    """自改密码：验旧设新，密码版本+1（旧会话失效）。成功返回 None；失败返回错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    acc = find_account(cfg, root, account)
    if not acc:
        return "账号不存在"
    if not verify_password_hash(acc.get("密码哈希"), old_pw):
        return "旧密码不正确"
    rows = load_accounts(cfg, root, create=False)
    for a in rows:
        if a["账号"] == account:
            a["密码哈希"] = hash_password(new_pw)
            a["初始密码"] = is_initial_password(new_pw)
            a["密码版本"] = password_version_of(a) + 1
            break
    _write(config_path(cfg, root), rows)
    return None


def set_password(cfg: dict, root: Path | None, account: str, new_pw: str) -> str | None:
    """管理员直接设某账号密码（不验旧，版本+1）。成功 None；失败错误文案。"""
    if len(new_pw or "") < 4:
        return "新密码至少 4 位"
    rows = load_accounts(cfg, root, create=False)
    found = False
    for a in rows:
        if a["账号"] == account:
            a["密码哈希"] = hash_password(new_pw)
            a["初始密码"] = is_initial_password(new_pw)
            a["密码版本"] = password_version_of(a) + 1
            found = True
            break
    if not found:
        return "账号不存在"
    _write(config_path(cfg, root), rows)
    return None


def reset_password(
    cfg: dict, root: Path | None, account: str, new_pw: str | None = None
) -> tuple[str | None, str | None]:
    """管理员重置：new 有则用之，无则随机 10 位。返回 (明文一次, 错误文案)。成功错误=None。"""
    plain = str(new_pw).strip() if new_pw is not None and str(new_pw).strip() else generate_random_password(10)
    if len(plain) < 4:
        return None, "新密码至少 4 位"
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


def public_row(acc: dict, **_kwargs) -> dict:
    """接口下发用：永不含密码/密码哈希（任务书63·H-05）。kwargs 吞掉旧 with_password。"""
    return {
        "账号": acc["账号"],
        "显示名": acc.get("显示名") or acc["账号"],
        "权限": acc["权限"],
        "可见BU": bu_names_of(acc),
        "最后登录": acc.get("最后登录") or "",
        "初始密码": bool(acc.get("初始密码", False)),
        "密码版本": password_version_of(acc),
    }
