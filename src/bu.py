#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BU 配置（迭代 14 按 BU 分页·v7.9 账号制）：读/写/校验 数据/BU配置.json + 口令哈希。

设计（陆总 2026-07-12 拍板口径 + 明昊 2026-07-11 账号制拍板）：
- 拆分主键 = 销售人员 → BU 映射（「销售」名单决定哪些数据算进该 BU，弃业务线；映射以人为准）；
- **看的人一个入口 `/`，账号+密码登录**：账号「整体」=姜征/陆总看全部；账号=BU 名=该负责人只看本 BU；
- 账号密码**只由管理员集中管理**（设置页 BU 配置卡逐行设/重置；看的人不能自己改）；
- 「分摊比例」只是预留配置位（null=公共费用暂不分摊，周一细则后开放）。

零配置兼容：配置文件缺失/为空/解析失败 → load_bu_config 返回 None = 功能不启用。
配置含真实人名与口令哈希，存 数据/BU配置.json（.gitignore 已挡，绝不进 git）；
git 内只有占位符样例 docs/BU配置样例.json。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

import loaders

CONFIG_NAME = "BU配置.json"
MAIN_ACCOUNT = "整体"     # 整体页账号名（姜征/陆总用；各 BU 账号名=BU 名）
DEFAULT_PW = "8888"       # 初始密码（明昊定：先用简单密码，正式发链接前管理员改掉）
_PW_ITERS = 100_000


def hash_pw(pw: str) -> str:
    """pbkdf2 口令哈希，格式 salt_hex$hash_hex。"""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _PW_ITERS)
    return f"{salt.hex()}${h.hex()}"


def verify_pw(stored: str | None, pw: str) -> bool:
    """校验口令；stored 为空 = 还没设过 → 用初始密码 DEFAULT_PW 比对。
    一律 bytes 比较——compare_digest 不吃非 ASCII str（铁律13：中文密码不 500）。"""
    if not stored:
        return hmac.compare_digest(pw.encode(), DEFAULT_PW.encode())
    try:
        salt_hex, h_hex = stored.split("$", 1)
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), _PW_ITERS).hex()
        return hmac.compare_digest(calc, h_hex)
    except (ValueError, TypeError):
        return False


def config_path(cfg: dict, root: Path | None = None) -> Path:
    return loaders.data_dir(cfg, root) / CONFIG_NAME


def _clean_names(v) -> list[str]:
    """名单字段清洗：列表/顿号·逗号分隔字符串 → 去空白去重（保序）。"""
    if isinstance(v, str):
        import re
        v = re.split(r"[、，,;；\n]", v)
    if not isinstance(v, list):
        return []
    out, seen = [], set()
    for x in v:
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _valid_bu(b: dict) -> dict | None:
    """校验并规范化一条 BU 配置；不合格（无名/与整体账号重名）→ None。"""
    if not isinstance(b, dict):
        return None
    name = str(b.get("name") or "").strip()
    if not name or name == MAIN_ACCOUNT:
        return None
    ratio = b.get("分摊比例")
    if ratio is not None:
        try:
            ratio = float(ratio)
        except (TypeError, ValueError):
            ratio = None
    pwh = b.get("密码hash")
    return {"name": name, "负责人": _clean_names(b.get("负责人")),
            "销售": _clean_names(b.get("销售")), "分摊比例": ratio,
            "密码hash": str(pwh) if pwh else None}


def load_bu_config(cfg: dict, root: Path | None = None) -> dict | None:
    """读 BU 配置。返回 {"bus": [规范化条目…]}；缺文件/空/坏 JSON/无有效条目 → None（功能不启用）。
    同名条目保留第一条（账号=BU 名，必须唯一）。"""
    p = config_path(cfg, root)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bus, seen = [], set()
    for b in (raw.get("bus") or []) if isinstance(raw, dict) else []:
        v = _valid_bu(b)
        if not v or v["name"] in seen:
            continue
        seen.add(v["name"])
        bus.append(v)
    return {"bus": bus} if bus else None


def _write(cfg, root, data: dict) -> None:
    p = config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_bu_config(cfg: dict, root: Path | None, bus: list[dict]) -> dict:
    """管理端保存：逐条校验规范化后落盘。
    - 密码：条目可带明文「新密码」（管理员在界面里填）→ 立即换成哈希存；不带 → 按 BU 名沿用已存哈希
      （None=还没设过=初始密码）。客户端传来的 密码hash 一律忽略（前端拿不到、也不许自造）。
    - 返回落盘后的 {"bus": [...]}；空列表=写空配置（=功能关闭）。"""
    existing = load_bu_config(cfg, root) or {"bus": []}
    known = {b["name"]: b for b in existing["bus"]}
    out, seen = [], set()
    for b in bus if isinstance(bus, list) else []:
        if not isinstance(b, dict):
            continue
        name = str(b.get("name") or "").strip()
        if not name or name == MAIN_ACCOUNT or name in seen:
            continue
        seen.add(name)
        new_pw = str(b.get("新密码") or "").strip()
        pwh = hash_pw(new_pw) if new_pw else known.get(name, {}).get("密码hash")
        out.append({"name": name, "负责人": _clean_names(b.get("负责人")),
                    "销售": _clean_names(b.get("销售")),
                    "分摊比例": None,  # 本批固定 null=暂不分摊（配置位已留，周一细则后开放）
                    "密码hash": pwh})
    data = {"bus": out}
    _write(cfg, root, data)
    return data


def by_name(bucfg: dict | None) -> dict[str, dict]:
    """{BU名: 条目}，供登录校验与 /bu/{name} 查找。"""
    return {b["name"]: b for b in (bucfg or {}).get("bus", [])}
