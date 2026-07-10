#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 6 个数据源（项目明细 / 收单台账 / 下单 / 回款 / 内部译员 / 手填与调整）+ 通用解析工具。

设计要点（沿用 v1.3 已验证做法，并按真实数据形态扩展）：
- 金额既可能是数字也可能是文本（陆总手动导出的是 '560.00' 文本），parse_amount 两种都吃。
- Excel 一律用完整加载模式，**绝不用 read_only=True**（智云导出的 xlsx `<dimension>` 标签谎报只有1格，
  流式读会静默只读1行，详见 docs/数据来源说明）。
- 列全部按表头文字定位，不认死列号。
- data_dir + period_pin 由 config 决定，测试/正式一键切换。
"""
from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parents[1]  # 程序根目录（config.json 所在层）


# ---------------- 配置 / 时间 ----------------
def load_config(root: Path | None = None) -> dict:
    base = root or ROOT
    with open(base / "config.json", encoding="utf-8") as f:
        return json.load(f)


def pinned_today(cfg: dict) -> datetime.date:
    """当前年月：config.period_pin 钉住则用它（测试=2024-07），否则用系统当天（正式版数据是当月的）。"""
    pin = cfg.get("period_pin")
    if pin and pin.get("year") and pin.get("month"):
        import calendar
        last = calendar.monthrange(pin["year"], pin["month"])[1]
        return datetime.date(pin["year"], pin["month"], min(datetime.date.today().day, last))
    return datetime.date.today()


def data_dir(cfg: dict, root: Path | None = None) -> Path:
    return (root or ROOT) / cfg["data_dir"]


# ---------------- 通用解析 ----------------
def parse_amount(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def amount_parse_fails(val: Any) -> bool:
    """单元格非空、但 parse_amount 只能按 0 算的情形——供数据体检计数，别让坏值无声消失。"""
    if val is None:
        return False
    s = str(val).replace(",", "").strip()
    if not s:
        return False
    try:
        float(s)
        return False
    except ValueError:
        return True


_DATE_PARTS_CACHE: dict = {}


def parse_date_parts(val: Any) -> tuple[int, int, int] | None:
    """解析日期为 (年,月,日)，带结果缓存（周期矩阵含月区间后同一值会被解析几十次）。"""
    try:
        return _DATE_PARTS_CACHE[val]
    except KeyError:
        r = _parse_date_parts(val)
        _DATE_PARTS_CACHE[val] = r
        return r
    except TypeError:  # 不可哈希的怪值：不缓存直接算
        return _parse_date_parts(val)


def _parse_date_parts(val: Any) -> tuple[int, int, int] | None:
    """解析日期为 (年,月,日)。支持 datetime、YYYY-MM-DD、YYYY/MM/DD、YYYYMMDD。"""
    if val is None:
        return None
    if hasattr(val, "year") and hasattr(val, "month"):
        try:
            return int(val.year), int(val.month), int(getattr(val, "day", 1) or 1)
        except (TypeError, ValueError):
            return None
    s = str(val).strip()
    if not s:
        return None
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) >= 8:
        try:
            return int(digits[:4]), int(digits[4:6]), int(digits[6:8])
        except ValueError:
            return None
    norm = s.replace("/", "-").split("-")
    if len(norm) >= 3:
        try:
            return int(norm[0]), int(norm[1]), int(norm[2][:2])
        except ValueError:
            return None
    if len(norm) >= 2:
        try:
            return int(norm[0]), int(norm[1]), 1
        except ValueError:
            return None
    return None


def _header_index(header: list[str], path: Path, required: tuple[str, ...]) -> dict[str, int]:
    """表头 → 列号。重名列：是我们要读的列 → 直接报错（不能猜哪列对）；不用的列 → 保留第一处出现。
    智云导出真实出现过重名列（内部译员表有两个"PM"），所以不能一刀切全报错。"""
    dups = {h for h in header if h and header.count(h) > 1}
    bad = sorted(dups & set(required))
    if bad:
        raise ValueError(f"「{path.name}」必需列出现重名：{bad}\n无法确定读哪一列，请先在源文件里改名去重再导入。")
    idx: dict[str, int] = {}
    for i, h in enumerate(header):
        if h and h not in idx:
            idx[h] = i
    return idx


def _rows_as_dicts(path: Path, required: tuple[str, ...] = ()) -> list[dict[str, str]]:
    """Excel/CSV → list[dict]，键=表头文字，值=字符串。Excel 读激活的第一个 sheet（智云导出只有一份数据）。"""
    if path.suffix.lower() in (".xlsx", ".xls"):
        wb = openpyxl.load_workbook(path, data_only=True)  # 完整加载，绝不 read_only
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(it)]
        idx = _header_index(header, path, required)
        out: list[dict[str, str]] = []
        for row in it:
            if all(v is None for v in row):
                continue
            out.append({h: ("" if row[i] is None else str(row[i])) for h, i in idx.items() if i < len(row)})
        return out
    with open(path, encoding="utf-8-sig") as f:
        rdr = csv.reader(f)
        header = [str(h).strip() for h in next(rdr, [])]
        idx = _header_index(header, path, required)
        return [{h: (row[i] if i < len(row) else "") for h, i in idx.items()} for row in rdr if any(row)]


# ---------------- 各源 ----------------
def resolve_project_detail_path(cfg: dict, root: Path | None = None) -> Path:
    base = data_dir(cfg, root)
    stem = cfg["files"]["project_detail_stem"]
    for ext in (".xlsx", ".csv"):
        p = base / f"{stem}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"未找到项目明细：{base}/{stem}.xlsx 或 .csv（导出步骤见 docs/取数操作手册）。")


def _require_file(path: Path, name: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(
            f"未找到「{name}」：{path}\n请把该文件放进数据目录（文件名固定，来源见 数据/README.md）。")
    return path


def _load_checked(path: Path, name: str, required: list[str]) -> list[dict[str, str]]:
    """读表并**校验必需列都在**——列被改名/导错文件时立刻报错，绝不静默读成0算出错数字。"""
    rows = _rows_as_dicts(path, tuple(required))
    if rows:
        have = set(rows[0].keys())
        missing = [c for c in required if c not in have]
        if missing:
            raise ValueError(
                f"「{name}」缺少必需列：{missing}\n实际列：{sorted(have)}\n"
                f"可能是导出格式变了或导错了文件——请核对来源（数据/README.md），或在 config.json 的 columns 里更新列名。")
    return rows


def load_project_detail(cfg: dict, root: Path | None = None) -> list[dict[str, str]]:
    c = cfg["columns"]
    return _load_checked(resolve_project_detail_path(cfg, root), "项目明细",
                         [c["project_delivery_date"], c["project_revenue"], c["project_cost"]])


def load_orders(cfg: dict, root: Path | None = None) -> list[dict[str, str]]:
    c = cfg["columns"]
    return _load_checked(_require_file(data_dir(cfg, root) / cfg["files"]["orders"], cfg["files"]["orders"]),
                         "下单", [c["order_amount"], c["order_date"]])


def load_receipts(cfg: dict, root: Path | None = None) -> list[dict[str, str]]:
    c = cfg["columns"]
    return _load_checked(_require_file(data_dir(cfg, root) / cfg["files"]["receipts"], cfg["files"]["receipts"]),
                         "回款记录", [c["receipt_amount"], c["receipt_date"]])


def load_inhouse(cfg: dict, root: Path | None = None) -> list[dict[str, str]]:
    c = cfg["columns"]
    return _load_checked(_require_file(data_dir(cfg, root) / cfg["files"]["inhouse"], cfg["files"]["inhouse"]),
                         "内部译员", [c["inhouse_amount"], c["inhouse_date"], c["inhouse_type"]])


# 收单台账：按年份 sheet + 表头文字定位列
def _open_ledger_sheet(path: Path, sheet_name: str):
    wb = openpyxl.load_workbook(path, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise KeyError(
            f"收单台账里找不到「{sheet_name}」sheet（现有：{wb.sheetnames}）。通常是新一年的sheet还没建，找亮晶确认。"
        )
    return wb[sheet_name]


def load_ledger(cfg: dict, sheet_name: str, root: Path | None = None) -> tuple[list, list[tuple]]:
    """返回 (表头行, 数据行)。"""
    path = data_dir(cfg, root) / cfg["files"]["ledger"]
    if not path.exists():
        raise FileNotFoundError(f"未找到收单台账：{path}")
    ws = _open_ledger_sheet(path, sheet_name)
    rows = list(ws.iter_rows(values_only=True))
    return list(rows[0]), rows[1:]


def load_manual(cfg: dict, root: Path | None = None) -> dict[str, dict[str, float]]:
    """手填与调整表（宽表：项目=行、月份=列）→ {月份'YYYY-MM': {项目: 金额float}}。
    表头形如 [项目, 归属, 备注, 2026-01, 2026-02, ...]；某项某月留空=不写入（留给"默认上月/0"逻辑）。
    维护友好：每月只在最右加一列，11 个项目始终整列可见、不会漏填。"""
    import re
    path = data_dir(cfg, root) / cfg["files"]["manual"]
    if not path.exists():
        return {}
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["手填与调整"] if "手填与调整" in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    def _hdr(h):
        # 月份列名可能被 Excel 存成日期单元格(datetime)——统一格式化成 YYYY-MM，否则该月整列会被漏读
        if h is None:
            return ""
        if hasattr(h, "year") and hasattr(h, "month"):
            return f"{int(h.year):04d}-{int(h.month):02d}"
        s = str(h).strip()
        # 手打不补零的月份列名（2026-1 / 2026/1）也归一成 2026-01，否则该月整列被静默漏读
        m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        return s
    header = [_hdr(h) for h in rows[0]]
    month_cols = {i: h for i, h in enumerate(header) if re.fullmatch(r"\d{4}-\d{2}", h)}
    try:
        i_item = header.index("项目")
    except ValueError:
        return {}
    out: dict[str, dict[str, float]] = {}
    for r in rows[1:]:
        item = str(r[i_item]).strip() if i_item < len(r) and r[i_item] is not None else ""
        if not item:
            continue
        for i, month in month_cols.items():
            v = r[i] if i < len(r) else None
            if v is None or str(v).strip() == "":
                continue
            out.setdefault(month, {})[item] = parse_amount(v)
    return out
