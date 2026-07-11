#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BU 配置（迭代 14 按 BU 分页 · v8.0 账号解耦）：读/写/校验 数据/BU配置.json。

设计（陆总 2026-07-12 拍板口径 + 明昊 2026-07-11 v8.0 拍板）：
- 拆分主键 = 销售人员 → BU 映射（「销售」名单决定哪些数据算进该 BU，弃业务线；映射以人为准）；
- **账号与 BU 解耦**（v8.0）：登录账号/密码改由 数据/看板账号.json 管；本文件只剩「数据归属」
  （BU 名 + 负责人备注 + 销售名单 + 分摊比例预留位）；
- 「分摊比例」只是预留配置位（null=公共费用暂不分摊，周一细则后开放）。

零配置兼容：配置文件缺失/为空/解析失败 → load_bu_config 返回 None = 功能不启用。
配置含真实人名，存 数据/BU配置.json（.gitignore 已挡，绝不进 git）；
git 内只有占位符样例 docs/BU配置样例.json。
"""
from __future__ import annotations

import json
from pathlib import Path

import loaders

CONFIG_NAME = "BU配置.json"
MAIN_ACCOUNT = "整体"     # 整体页权限保留字（账号权限字段同字面；BU 名不能叫这个）


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
    """校验并规范化一条 BU 配置；不合格（无名/与整体保留字重名）→ None。
    旧字段「密码hash」读时忽略丢弃（v8.0 已迁到 看板账号.json）。"""
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
    return {"name": name, "负责人": _clean_names(b.get("负责人")),
            "销售": _clean_names(b.get("销售")), "分摊比例": ratio}


def load_bu_config(cfg: dict, root: Path | None = None) -> dict | None:
    """读 BU 配置。返回 {"bus": [规范化条目…]}；缺文件/空/坏 JSON/无有效条目 → None（功能不启用）。
    同名条目保留第一条（BU 名必须唯一）。"""
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
    """管理端保存：逐条校验规范化后落盘（纯数据归属，无密码字段）。
    **一人一 BU**：同一销售名若出现在多个 BU，只保留先出现的那个 BU（拖拽 UI 同规则）。
    返回落盘后的 {"bus": [...]}；空列表=写空配置（=功能关闭）。"""
    out, seen_bu, claimed = [], set(), set()
    for b in bus if isinstance(bus, list) else []:
        if not isinstance(b, dict):
            continue
        name = str(b.get("name") or "").strip()
        if not name or name == MAIN_ACCOUNT or name in seen_bu:
            continue
        seen_bu.add(name)
        sales = []
        for s in _clean_names(b.get("销售")):
            if s in claimed:
                continue  # 已归别的 BU
            claimed.add(s)
            sales.append(s)
        out.append({"name": name, "负责人": _clean_names(b.get("负责人")),
                    "销售": sales,
                    "分摊比例": None})  # 本批固定 null=暂不分摊
    data = {"bus": out}
    _write(cfg, root, data)
    return data


def by_name(bucfg: dict | None) -> dict[str, dict]:
    """{BU名: 条目}，供 /bu/{name} 查找与校验。"""
    return {b["name"]: b for b in (bucfg or {}).get("bus", [])}
