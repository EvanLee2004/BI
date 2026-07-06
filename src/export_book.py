#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出数据装配：把 summary 整理成"多 sheet 表格"结构，供前端一键导出成 .xlsx。

设计铁律（延续本项目约定）：**每一格的值都在 Python 侧算好**，前端 JS 只负责把
这里产出的 sheets 原样打包成 Excel + 存盘，绝不做任何金额运算。所以导出的数字与
页面上看到的完全一致，不会因为前端再算一遍而对不上。

产出结构：
    {
      "meta": {"stamp": "2026-07-05_1530", "生成时间": "...", "单位": "元"},
      "sheets": [ {"name": "利润表", "columns": [...], "rows": [[...], ...]}, ... ]
    }
金额一律用"元"原值（保留 2 位小数）落表，方便后续在 Excel 里自由二次分析；
百分比字段名里带 % 提示（如 毛利率%），值为百分数（55.16 表示 55.16%）。
"""
from __future__ import annotations

from typing import Any

# 利润表行项（(表头名, summary 取值函数)）——顺序即 Excel 里从上到下的行
_PL_LINES = [
    ("交付单数", lambda p: p["delivery_count"]),
    ("收入(不含税)", lambda p: p["revenue_net"]),
    ("生产成本", lambda p: p["production_cost"]),
    ("毛利", lambda p: p["gross_profit"]),
    ("毛利率%", lambda p: p["gross_margin_pct"]),
    ("营销费用", lambda p: p["expense"].get("营销费用", 0.0)),
    ("管理费用", lambda p: p["expense"].get("管理费用", 0.0)),
    ("固定运营费用", lambda p: p["expense"].get("固定运营费用", 0.0)),
    ("研发费用", lambda p: p["expense"].get("研发费用", 0.0)),
    ("财务费用", lambda p: p["expense"].get("财务费用", 0.0)),
    ("期间费用合计", lambda p: p["expense"].get("total", 0.0)),
    ("附加税费", lambda p: p["surtax"]),
    ("其他损益", lambda p: p["other_pl"]),
    ("税前利润", lambda p: p["pretax_profit"]),
    ("税前利润率%", lambda p: p["pretax_margin_pct"]),
    ("下单额", lambda p: p["orders"]),
    ("回款额(到账)", lambda p: p["receipts"]),
]

_EXPENSE_CATS = ["营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"]


def _num(v):
    """统一成可入表的数值（保留 2 位）；非数值原样返回。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return v


def _all_keys(summary):
    """周期列顺序：年 → 各季度 → 各月（与页面时间选择器一致）。"""
    tg = summary["meta"]["tab_groups"]
    return [summary["meta"]["year_key"]] + list(tg["季度"]) + list(tg["月"])


def _sheet_pl(summary):
    P = summary["periods"]
    keys = _all_keys(summary)
    columns = ["项目"] + [P[k]["label"] for k in keys]
    rows = []
    for name, getter in _PL_LINES:
        row = [name] + [_num(getter(P[k])) for k in keys]
        rows.append(row)
    return {"name": "利润表", "columns": columns, "rows": rows}


def _sheet_expense(summary):
    P = summary["periods"]
    keys = _all_keys(summary)
    columns = ["周期"] + _EXPENSE_CATS + ["合计"]
    rows = []
    for k in keys:
        e = P[k]["expense"]
        rows.append([P[k]["label"]] + [_num(e.get(c, 0.0)) for c in _EXPENSE_CATS] + [_num(e.get("total", 0.0))])
    return {"name": "费用构成", "columns": columns, "rows": rows}


def _sheet_trend(summary):
    columns = ["月份", "收入", "生产成本", "毛利率%"]
    rows = [[m, _num(rev), _num(cost), _num(gm)] for (m, rev, cost, gm) in summary["trend"]]
    return {"name": "月度趋势", "columns": columns, "rows": rows}


def _sheet_receipts(summary):
    columns = ["月份", "回款额(到账)"]
    rows = [[m, _num(v)] for (m, v) in summary["receipt_monthly"]]
    return {"name": "回款", "columns": columns, "rows": rows}


def _sheet_health(summary):
    h = summary["meta"]["health"]
    columns = ["数据源", "行数", "覆盖月份"]
    rows = []
    for s in h["sources"]:
        months = "、".join(f"{m}月" for m in s["months"]) or "无"
        rows.append([s["name"], _num(s["rows"]), months])
    return {"name": "数据体检", "columns": columns, "rows": rows}


def _sheet_notes(summary, cfg):
    meta = summary["meta"]
    h = summary["meta"]["health"]
    warn = "；".join(h["warnings"]) if h["warnings"] else "无异常"
    columns = ["说明项", "内容"]
    rows = [
        ["生成时间", meta["generated_at"]],
        ["数据年份", str(meta["year"])],
        ["金额单位", "元（百分比字段值为百分数，如 55.16 表示 55.16%）"],
        ["数据目录", str(cfg.get("data_dir", ""))],
        ["收入口径", "交付额 ÷ 1.06（不含税）"],
        ["生产成本口径", "系统直接成本 − 内部译员成本 + 手填人力/税费/流量等"],
        ["税前利润口径", "毛利 − 营销 − 管理 − 固定运营 − 研发 − 财务 − 附加税费(收入×6%×12%) + 其他损益"],
        ["数据体检", warn],
    ]
    return {"name": "说明", "columns": columns, "rows": rows}


def build_export_book(summary, cfg):
    """把 summary 整理成多 sheet 导出结构（值全部 Python 侧算好）。"""
    stamp = summary["meta"]["generated_at"].replace(" ", "_").replace(":", "")
    return {
        "meta": {
            "stamp": stamp,
            "生成时间": summary["meta"]["generated_at"],
            "单位": "元",
        },
        "sheets": [
            _sheet_pl(summary),
            _sheet_expense(summary),
            _sheet_trend(summary),
            _sheet_receipts(summary),
            _sheet_health(summary),
            _sheet_notes(summary, cfg),
        ],
    }
