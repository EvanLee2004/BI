#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看板账号表（迭代 15 / v8.0 · 任务书64·P 明文为真相源）：读/写/校验 数据/看板账号.json。

设计（明昊 2026-07-11 拍板 · 2026-07-12 v8.6 扩多 BU · 2026-07-17 任务书50 回退明文 ·
2026-07-20 任务书63 曾改 PBKDF2 · **2026-07-20 晚 明昊再拍板回退明文**——管理员必须可查看所有账号密码）：
- 账号与 BU 解耦：账号绑定「能看什么」= 权限 ∈ {管理员, 整体, BU, 某 BU 名(旧)}；
  **v8.6 多 BU**：权限=BU 时可绑一组 BU（见 `可见BU` 列表）；整体=全部 BU + 全公司页；
  旧账号权限=单个 BU 名仍兼容（等价于绑定该一个 BU）。取用一律走 `bu_names_of`/`can_see_bu`。
- 一个 BU 可挂多个账号；账号名唯一；
- **密码明文为真相源**（管理端 👁 可见可改，看的人可自改）；产品硬需求，接受明文存储风险；
- **密码版本**保留：改密自增 → 旧会话 cookie 失效（改密踢会话）；
- **初始密码**由明文是否属默认口令集推导（管理端黄标）；
- 存 JSON 不开库（凭据不是业务数据，且 看板.db 每日备份会副本扩散）；
- 缺文件 → 自动 seed 默认表（部署零配置）；git 里只有 docs/看板账号样例.json（合成名）；
- 写盘统一 chmod 0o600（见 secure_io）；不进 git + 纯内网 + 防爆破 + 12h 会话。

铁律：真实人名只进 数据/ 本地文件；代码默认 seed / 测试 / 样例一律合成名。
口令比较一律 bytes + hmac.compare_digest（铁律 13）。
选型见 docs/madr/0020_password_plaintext_by_product_decision.md（0019 已 Superseded）。
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import string
import time
from pathlib import Path

import loaders
from secure_io import write_private_text

log = logging.getLogger("kanban.accounts")

CONFIG_NAME = "看板账号.json"
# 隔离坏文件后留下此旗标，防止「改名后路径不存在 → 误 seed 出厂口令」
NEEDS_RESTORE_SUFFIX = ".needs_restore"

# 2.6.3·A1：账号表损坏态（进程内；供 /api/v1/health 抬红 + 告警一次）
_ACCOUNTS_CORRUPT: dict | None = None  # {"path": str, "reason": str, "quarantine": str}

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


def _norm_one(raw: dict) -> dict | None:
    """校验并规范化一条账号；不合格 → None。忽略遗留「密码哈希」字段（不校验、不写回）。"""
    if not isinstance(raw, dict):
        return None
    acct = str(raw.get("账号") or "").strip()
    if not acct:
        return None
    perm = str(raw.get("权限") or "").strip()
    if not perm:
        return None
    display = str(raw.get("显示名") or acct).strip() or acct
    # 明文为真相源；仅有哈希、无明文的存量行 → 密码空，登录失败直至管理员写入明文
    # 2.6.7 D-3：空密码不得静默变出厂口令——保持空，登录失败直至管理员写入明文
    if "密码" in raw and raw["密码"] is not None and str(raw["密码"]).strip() != "":
        pw = str(raw["密码"])
    else:
        pw = str(raw.get("密码") or "").strip()
    try:
        pw_ver = int(raw.get("密码版本") or 0)
    except (TypeError, ValueError):
        pw_ver = 0
    last = str(raw.get("最后登录") or "").strip() or None
    out = {
        "账号": acct,
        "显示名": display,
        "权限": perm,
        "密码": pw,
        "密码版本": pw_ver,
    }
    if perm == PERM_BU:
        out["可见BU"] = _clean_bu_list(raw.get("可见BU"))
    if last:
        out["最后登录"] = last
    # 3.7.8：能力矩阵（可选 object）
    caps = raw.get("能力")
    if isinstance(caps, dict) and caps:
        out["能力"] = dict(caps)
    return out


def _write(path: Path, accounts: list[dict]) -> None:
    """落盘：明文密码 + 密码版本 + 能力；chmod 0o600。不写密码哈希。

    2.6.12：空密码禁止静默回落 DEFAULT_VIEW_PW（8888）；seed_defaults 须显式写默认串。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for a in accounts:
        pw = a.get("密码")
        if pw is None or not str(pw).strip():
            raise ValueError(
                f"账号「{a.get('账号') or '?'}」密码不能为空（禁止静默写入默认口令）"
            )
        row = {
            "账号": a["账号"],
            "显示名": a["显示名"],
            "权限": a["权限"],
            "密码": str(pw),
            "密码版本": int(a.get("密码版本") or 0),
        }
        if a.get("权限") == PERM_BU:
            row["可见BU"] = _clean_bu_list(a.get("可见BU"))
        if a.get("最后登录"):
            row["最后登录"] = a["最后登录"]
        caps = a.get("能力")
        if isinstance(caps, dict) and caps:
            # 只保留已知 key；布尔化
            import authz as _authz

            cleaned = _authz.normalize_caps_field(caps)
            if cleaned:
                row["能力"] = cleaned
        rows.append(row)
    write_private_text(path, json.dumps({"accounts": rows}, ensure_ascii=False, indent=2) + "\n")


def _needs_restore_path(p: Path) -> Path:
    return p.with_name(p.name + NEEDS_RESTORE_SUFFIX)


def seed_defaults(cfg: dict, root: Path | None = None) -> list[dict]:
    """写默认账号表并返回规范化列表。"""
    global _ACCOUNTS_CORRUPT
    p = config_path(cfg, root)
    rows = [_norm_one(a) for a in DEFAULT_ACCOUNTS]
    rows = [r for r in rows if r]
    _write(p, rows)
    _ACCOUNTS_CORRUPT = None
    try:
        _needs_restore_path(p).unlink(missing_ok=True)
    except OSError:
        pass
    return rows


def accounts_corrupt_status() -> dict | None:
    """2.6.3·A1：最近一次账号表损坏信息（无则 None）。"""
    return dict(_ACCOUNTS_CORRUPT) if _ACCOUNTS_CORRUPT else None


def clear_accounts_corrupt_status() -> None:
    """测试/恢复后清掉损坏旗标。"""
    global _ACCOUNTS_CORRUPT
    _ACCOUNTS_CORRUPT = None


def _quarantine_corrupt(p: Path, reason: str) -> Path | None:
    """坏文件改名 看板账号.json.corrupt-<时间戳>，保留原内容；写 needs_restore 旗标防误 seed。"""
    global _ACCOUNTS_CORRUPT
    ts = time.strftime("%Y%m%d%H%M%S")
    dest = p.with_name(f"{p.name}.corrupt-{ts}")
    n = 0
    while dest.exists():
        n += 1
        dest = p.with_name(f"{p.name}.corrupt-{ts}-{n}")
    try:
        p.rename(dest)
        qpath = str(dest)
    except OSError as e:
        log.error("账号表隔离失败 %s → %s: %s", p, dest, e)
        qpath = ""
        dest = None
    flag = _needs_restore_path(p)
    try:
        flag.write_text(
            json.dumps({"reason": reason, "quarantine": qpath, "ts": ts}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        log.error("写 needs_restore 旗标失败: %s", e)
    _ACCOUNTS_CORRUPT = {"path": str(p), "reason": reason, "quarantine": qpath}
    log.error("账号表损坏已隔离: %s (%s) → %s", p, reason, qpath or "(隔离失败)")
    try:
        import notify

        try:
            cfg0 = loaders.load_config(strict=False)
        except Exception:
            cfg0 = {}
        notify.maybe_alert_text(
            cfg0,
            f"【经营看板告警】账号表损坏：{reason}；已保留 {qpath or p.name}；"
            f"未重置为出厂口令。请从 .corrupt 备份恢复后删 {flag.name}。",
        )
    except Exception:
        pass
    return dest


def load_accounts(cfg: dict, root: Path | None = None, *, create: bool = True) -> list[dict]:
    """读账号表。

    2.6.3·A1：**只有文件真不存在且无 needs_restore 旗标**且 create=True 才 seed。
    坏 JSON / 缺 accounts 键 → 改名 quarantine 保留 + 体检红 + 告警，**绝不覆盖写回出厂表**。
    文件存在但无有效账号行 → 返回 []（不 seed）。
    """
    global _ACCOUNTS_CORRUPT
    p = config_path(cfg, root)
    flag = _needs_restore_path(p)
    if not p.exists():
        # 损坏隔离后留下旗标：禁止 seed，直到管理员恢复并清除旗标
        if flag.exists():
            try:
                meta = json.loads(flag.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            _ACCOUNTS_CORRUPT = {
                "path": str(p),
                "reason": (meta or {}).get("reason") or "账号表待恢复（needs_restore）",
                "quarantine": (meta or {}).get("quarantine") or "",
            }
            return []
        return seed_defaults(cfg, root) if create else []
    try:
        text = p.read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, ValueError) as e:
        _quarantine_corrupt(p, f"JSON 无效/读失败: {type(e).__name__}")
        return []
    items = raw.get("accounts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        _quarantine_corrupt(p, "缺 accounts 键或类型不是列表")
        return []
    out, seen = [], set()
    for it in items:
        v = _norm_one(it)
        if not v or v["账号"] in seen:
            continue
        seen.add(v["账号"])
        out.append(v)
    # 文件存在且结构合法 → 即使 out 为空也不 seed
    if out:
        _ACCOUNTS_CORRUPT = None
        try:
            flag.unlink(missing_ok=True)
        except OSError:
            pass
    return out


def _resolve_password_for_save(raw: dict, old: dict, acct: str, *, is_existing: bool) -> str:
    """密码留空不改；新账号须显式非空。"""
    old_pw = str(old.get("密码") or "")
    explicit = "密码" in raw and raw["密码"] is not None and str(raw["密码"]).strip() != ""
    if explicit:
        return str(raw["密码"])
    if is_existing and old_pw:
        return old_pw
    raise ValueError(f"账号「{acct}」须设置密码（留空表示不改，新账号不可留空）")


def _attach_caps_for_save(row: dict, raw: dict, old: dict) -> None:
    """3.7.8：能力字段覆盖 / 沿用 / 物化角色默认。"""
    import authz as _authz

    if "能力" in raw and isinstance(raw.get("能力"), dict):
        cleaned = _authz.normalize_caps_field(raw.get("能力"))
        if cleaned is not None:
            row["能力"] = cleaned
            return
    if isinstance(old.get("能力"), dict):
        row["能力"] = dict(old["能力"])
        return
    row["能力"] = _authz.materialize_caps(row)


def _normalize_account_row(raw: dict, existing: dict) -> dict | None:
    """单条账号规范化；无效返回 None。

    3.7.5：密码「留空不改」；新账号须明确非空密码。
    3.7.8：附带能力矩阵（覆盖/沿用/物化）。
    """
    acct = str(raw.get("账号") or "").strip()
    if not acct:
        return None
    perm = str(raw.get("权限") or "").strip()
    if not perm:
        return None
    display = str(raw.get("显示名") or acct).strip() or acct
    is_existing = acct in existing
    old = existing.get(acct, {}) if is_existing else {}
    pw = _resolve_password_for_save(raw, old, acct, is_existing=is_existing)
    if is_master_account(acct):
        perm = PERM_ADMIN
    pw_ver = password_version_of(old)
    if is_existing and pw != str(old.get("密码") or ""):
        pw_ver = pw_ver + 1
    row = {
        "账号": acct,
        "显示名": display,
        "权限": perm,
        "密码": pw,
        "密码版本": pw_ver,
    }
    if perm == PERM_BU:
        row["可见BU"] = _clean_bu_list(raw.get("可见BU"))
    if old.get("最后登录"):
        row["最后登录"] = old["最后登录"]
    _attach_caps_for_save(row, raw, old)
    return row


def save_accounts(cfg: dict, root: Path | None, accounts: list) -> list[dict]:
    """管理端保存：校验 → 规范化 → 落盘。
    - 账号名必填且唯一；权限必填；
    - 密码：明确非空则以之为准；缺省/空串=留空不改（沿用已存）；
      新账号无已存值须显式设密（禁止静默 8888）；
    - 密码变更时「密码版本」+1（改密踢会话）；
    - 最后登录：客户端传来的忽略，沿用已存（只由 mark_login 写）；
    - 总账号 MASTER_ACCOUNT：若库中已有则不可删、不可改登录名；至少保留一个「管理员」。
    - 3.7.8：至少一账号 admin_access+manage_accounts；总账号不可无管理能力。
    返回落盘后的列表；校验失败抛 ValueError。"""
    global _ACCOUNTS_CORRUPT
    import authz as _authz

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
    _authz.validate_accounts_caps(out)
    p = config_path(cfg, root)
    _write(p, out)
    _ACCOUNTS_CORRUPT = None
    try:
        _needs_restore_path(p).unlink(missing_ok=True)
    except OSError:
        pass
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
    """口令比对：3.6.0 起支持 PBKDF2 哈希；遗留明文仍可验（迁移前）。常量时间。"""
    try:
        from password_kdf import verify_password as _v

        return _v(stored, pw)
    except Exception:
        return hmac.compare_digest((stored or "").encode(), (pw or "").encode())


def authenticate(cfg: dict, root: Path | None, account: str, password: str) -> dict | None:
    """账号+密码校验；成功返回账号条目，失败 None。账号不存在与密码错同一返回（不泄存在性）。"""
    acc = find_account(cfg, root, account)
    if not acc:
        verify_password(DEFAULT_VIEW_PW, password)
        return None
    stored = acc.get("密码") or ""
    if not stored:
        # 仅哈希无明文的行：不可登录
        verify_password(DEFAULT_VIEW_PW, password)
        return None
    if not verify_password(stored, password):
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
    """自改密码：验旧设新，密码版本+1（旧会话失效）。成功返回 None；失败返回错误文案。

    2.6.12 明昊拍板：密码非空即可，不强制长度/字符类型。
    3.6.0 小修：落盘明文（产品 SSOT：管理员可查看可改）；verify 仍可读遗留 PBKDF2 行。
    """
    if not str(new_pw or "").strip():
        return "新密码不能为空"
    acc = find_account(cfg, root, account)
    if not acc:
        return "账号不存在"
    if not verify_password(acc.get("密码"), old_pw):
        return "旧密码不正确"
    rows = load_accounts(cfg, root, create=False)
    stored = str(new_pw)
    for a in rows:
        if a["账号"] == account:
            a["密码"] = stored
            a["密码版本"] = password_version_of(a) + 1
            a["must_change_password"] = False
            break
    _write(config_path(cfg, root), rows)
    return None


def set_password(cfg: dict, root: Path | None, account: str, new_pw: str) -> str | None:  # noqa: C901
    """管理员直接设某账号密码（不验旧，版本+1）。成功 None；失败错误文案。

    2.6.12 明昊拍板：密码非空即可，不强制长度/字符类型。
    3.6.0 小修：落盘明文（与文件头 / MADR-0020 一致；禁止写路径再产 PBKDF2）。
    """
    if not str(new_pw or "").strip():
        return "新密码不能为空"
    rows = load_accounts(cfg, root, create=False)
    stored = str(new_pw)
    found = False
    for a in rows:
        if a["账号"] == account:
            a["密码"] = stored
            a["密码版本"] = password_version_of(a) + 1
            a["must_change_password"] = is_initial_password(str(new_pw))
            found = True
            break
    if not found:
        return "账号不存在"
    _write(config_path(cfg, root), rows)
    return None


def reset_password(
    cfg: dict, root: Path | None, account: str, new_pw: str | None = None
) -> tuple[str | None, str | None]:
    """管理员显式设新密码。3.7.5：new 必填非空；禁止随机生成后由 API 回显。

    返回 (明文占位或 None, 错误文案)。成功时明文恒为 None（调用方不得回显）。
    """
    plain = str(new_pw).strip() if new_pw is not None else ""
    if not plain:
        return None, "请输入新密码（禁止随机生成后回显）"
    err = set_password(cfg, root, account, plain)
    if err:
        return None, err
    return None, None


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
    """接口下发用。

    3.7.8：管理端 with_password=True 回显看板账号明文（MADR-0020）；
    默认 with_password=False 不下发明文。遗留 PBKDF2 行：password_hashed=True。
    始终下发 materialize 后的 caps（能力矩阵）。
    """
    import authz as _authz

    pw = acc.get("密码") or ""
    try:
        from password_kdf import is_hashed

        hashed = is_hashed(str(pw))
    except Exception:
        hashed = str(pw).startswith("pbkdf2_sha256$")
    initial = bool(acc.get("must_change_password")) or (
        (not hashed) and bool(pw) and is_initial_password(str(pw))
    )
    caps = _authz.materialize_caps(acc)
    row = {
        "账号": acc["账号"],
        "显示名": acc.get("显示名") or acc["账号"],
        "权限": acc["权限"],
        "可见BU": bu_names_of(acc),
        "最后登录": acc.get("最后登录") or "",
        "初始密码": initial,
        "密码版本": password_version_of(acc),
        "must_change_password": initial,
        "password_set": bool(str(pw).strip()),
        "能力": caps,
        "caps": caps,
    }
    if hashed:
        row["password_hashed"] = True
    if with_password:
        # 3.7.8：管理员会话可见看板明文；哈希行不回显密文
        row["密码"] = "" if hashed else str(pw)
    return row
