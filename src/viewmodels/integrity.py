# -*- coding: utf-8 -*-
"""管理层数据完整性 VM（3.5.0）。

只打包已有 meta/health 事实；不造金额、不改入账规则。
"""
from __future__ import annotations

import re
from typing import Any


def _parse_missing_manual(warnings: list[str]) -> tuple[int, list[str]]:
    months: list[str] = []
    count = 0
    for w in warnings:
        s = str(w)
        if "手填缺" not in s and "手填为空" not in s:
            continue
        m = re.search(r"手填缺\s*(\d+)\s*个", s)
        if m:
            count = max(count, int(m.group(1)))
        # 抓 YYYY-MM
        found = re.findall(r"20\d{2}-\d{2}", s)
        for fm in found:
            if fm not in months:
                months.append(fm)
    if count == 0 and months:
        count = len(months)
    return count, months


def _parse_future_records(warnings: list[str]) -> tuple[int, list[str]]:
    n = 0
    samples: list[str] = []
    for w in warnings:
        s = str(w)
        if "晚于今天" not in s and "未来月" not in s:
            continue
        m = re.search(r"有\s*(\d+)\s*行", s)
        if m:
            n += int(m.group(1))
        else:
            n += 1
        for samp in re.findall(r"20\d{2}-\d{2}-\d{2}", s):
            if samp not in samples:
                samples.append(samp)
    return n, samples


def pack_data_integrity(summary: dict | None) -> dict[str, Any]:
    """summary.meta.health → 首屏可读完整性字段（无真实客户名）。"""
    summary = summary or {}
    meta = summary.get("meta") or {}
    health = meta.get("health") if isinstance(meta.get("health"), dict) else {}
    warnings = [str(x) for x in (health.get("warnings") or [])]
    miss_n, miss_months = _parse_missing_manual(warnings)
    fut_n, fut_samples = _parse_future_records(warnings)
    result = health.get("result") or meta.get("health_result") or ""
    built_at = str(meta.get("built_at") or health.get("built_at") or "")
    as_of = str(meta.get("as_of") or built_at or "")

    affected = []
    if miss_n:
        affected.append("费用/利润等含手填口径的数字可能不完整（缺月按 0 计）")
    if fut_n:
        affected.append("存在归属未来日期的源数据行，已计入对应未来月")
    lamp = "green"
    if result in ("黄", "yellow", "Y"):
        lamp = "yellow"
    elif result in ("红", "red", "R"):
        lamp = "red"
    elif miss_n or fut_n:
        lamp = "yellow"

    short = []
    if miss_n:
        short.append(f"手填缺 {miss_n} 个月")
    if fut_n:
        short.append(f"未来日期记录 {fut_n} 条")
    if not short and result:
        short.append(f"体检{result}")

    return {
        "health_result": result or ("黄" if lamp == "yellow" else "绿"),
        "lamp": lamp,
        "as_of": as_of,
        "as_of_disp": as_of,
        "built_at": built_at,
        "missing_manual_count": int(miss_n),
        "missing_manual_months": miss_months,
        "future_record_count": int(fut_n),
        "future_samples": fut_samples[:3],
        "notes": warnings[:8],
        "warnings": warnings[:8],
        "affected_scope": "；".join(affected) if affected else "",
        "short_disp": " · ".join(short) if short else "数据完整性正常",
        "headline": (
            f"数据状态：{result or lamp} · " + (" · ".join(short) if short else "完整")
        ),
    }
