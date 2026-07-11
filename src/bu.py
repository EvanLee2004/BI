#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BU 配置（迭代 14 按 BU 分页）：读/写/校验 数据/BU配置.json + token 生成。

设计（陆总 2026-07-12 拍板，台账第十节）：
- 拆分主键 = 销售人员 → BU 映射（弃业务线；智云"部门"字段≠BU，映射以人为准）；
- BU 清单/人员映射/负责人全部配置化可增改；每 BU 一条独立只读链接 /bu/{token}；
- 「分摊比例」只是预留配置位（null=公共费用暂不分摊），本批不做任何分摊计算（等周一细则）。

零配置兼容：配置文件缺失/为空/解析失败 → load_bu_config 返回 None = 功能不启用，
主看板一切照旧。配置含真实人名，存 数据/BU配置.json（.gitignore 已挡 数据/*.json，绝不进 git）；
git 内只有占位符样例 docs/BU配置样例.json。
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

import loaders

CONFIG_NAME = "BU配置.json"
TOKEN_MIN_LEN = 32  # 独立链接 token 最短长度（服务端生成 32 位 hex，不可猜）


def config_path(cfg: dict, root: Path | None = None) -> Path:
    return loaders.data_dir(cfg, root) / CONFIG_NAME


def new_token() -> str:
    return secrets.token_hex(16)  # 32 位 hex


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
    """校验并规范化一条 BU 配置；不合格（无名/token 太短）→ None（跳过，不让脏配置放倒服务）。"""
    if not isinstance(b, dict):
        return None
    name = str(b.get("name") or "").strip()
    token = str(b.get("token") or "").strip()
    if not name or len(token) < TOKEN_MIN_LEN:
        return None
    ratio = b.get("分摊比例")
    if ratio is not None:
        try:
            ratio = float(ratio)
        except (TypeError, ValueError):
            ratio = None
    return {"name": name, "负责人": _clean_names(b.get("负责人")),
            "销售": _clean_names(b.get("销售")), "token": token, "分摊比例": ratio}


def load_bu_config(cfg: dict, root: Path | None = None) -> dict | None:
    """读 BU 配置。返回 {"bus": [规范化条目…]}；缺文件/空/坏 JSON/无有效条目 → None（功能不启用）。
    token 重复视为配置错误：后一条被跳过（链接必须一一对应）。"""
    p = config_path(cfg, root)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bus, seen_tokens, seen_names = [], set(), set()
    for b in (raw.get("bus") or []) if isinstance(raw, dict) else []:
        v = _valid_bu(b)
        if not v or v["token"] in seen_tokens or v["name"] in seen_names:
            continue
        seen_tokens.add(v["token"])
        seen_names.add(v["name"])
        bus.append(v)
    return {"bus": bus} if bus else None


def save_bu_config(cfg: dict, root: Path | None, bus: list[dict]) -> dict:
    """管理端保存：逐条校验规范化后落盘。token 只认服务端已有值——客户端传来的 token
    不在现有配置里（或为空）一律服务端重新生成，防弱 token/自造 token。
    返回落盘后的 {"bus": [...]}；空列表=写空配置（=功能关闭）。"""
    existing = load_bu_config(cfg, root) or {"bus": []}
    known = {b["token"] for b in existing["bus"]}
    out = []
    for b in bus if isinstance(bus, list) else []:
        if not isinstance(b, dict):
            continue
        name = str(b.get("name") or "").strip()
        if not name:
            continue
        token = str(b.get("token") or "").strip()
        if token not in known:
            token = new_token()
        out.append({"name": name, "负责人": _clean_names(b.get("负责人")),
                    "销售": _clean_names(b.get("销售")), "token": token,
                    "分摊比例": None})  # 分摊比例本批固定 null=暂不分摊（配置位已留，周一细则后开放）
    # 名/链重复兜底去重（同名保留第一条）
    seen_n, seen_t, dedup = set(), set(), []
    for b in out:
        if b["name"] in seen_n or b["token"] in seen_t:
            continue
        seen_n.add(b["name"])
        seen_t.add(b["token"])
        dedup.append(b)
    data = {"bus": dedup}
    p = config_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def token_map(bucfg: dict | None) -> dict[str, dict]:
    """{token: BU条目}，供 /bu/{token} 查找。"""
    return {b["token"]: b for b in (bucfg or {}).get("bus", [])}
