#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理利润表 Excel 导出（2.3.6）。

纯函数：从既有 summary + period_key 组装 xlsx bytes。
数据源复用 pack_pl_by_period / structure_for_vm，金额只写 amt_disp 展示串，
禁止再算税前/毛利。
"""

from __future__ import annotations

import io
import re
import time
from typing import Any

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# Excel sheet 名：≤31、禁 []:*?/\
_SHEET_ILLEGAL = re.compile(r'[\[\]:*?/\\]')
_FNAME_ILLEGAL = re.compile(r'[\\/:*?"<>|\s]+')

_BOLD = Font(bold=True)
_NORMAL = Font(bold=False)


def _safe_sheet_name(raw: str, used: set[str], *, max_len: int = 31) -> str:
    """生成合法且不重复的 sheet 名。"""
    base = _SHEET_ILLEGAL.sub("", str(raw or "").strip()) or "Sheet"
    base = base[:max_len]
    name = base
    n = 2
    while name in used:
        suffix = f"_{n}"
        name = (base[: max_len - len(suffix)] + suffix) if len(base) + len(suffix) > max_len else base + suffix
        n += 1
    used.add(name)
    return name


def _short_detail_sheet_title(open_key: str, title: str) -> str:
    """构成 sheet 短名：优先 title 去尾缀，否则 open_key。"""
    t = (title or "").strip()
    for suf in ("构成", "明细"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    if t:
        t = re.sub(r"[（(][^）)]*[）)]\s*$", "", t).strip() or t
    short = t or open_key or "明细"
    return f"构成_{short}"


def safe_filename_part(s: str) -> str:
    """文件名安全片段：非法字符替换为 _。"""
    part = _FNAME_ILLEGAL.sub("_", str(s or "").strip())
    part = part.strip("._") or "x"
    return part[:80]


def _set_col_widths(ws: Worksheet, headers: list[str], *, extra: int = 8, cap: int = 36) -> None:
    for i, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(len(str(col)) + extra, 12), cap)


def _write_main_sheet(ws: Worksheet, rows: list[dict[str, Any]]) -> None:
    headers = ["科目", "金额", "说明"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _BOLD
    for r in rows:
        name = r.get("name") or ""
        amt = r.get("amt_disp") if r.get("amt_disp") is not None else ""
        formula = r.get("formula") or ""
        ws.append([name, amt, formula])
        row_idx = ws.max_row
        for col in range(1, 4):
            ws.cell(row=row_idx, column=col).font = _BOLD
    _set_col_widths(ws, headers)


def _write_detail_sheet(dws: Worksheet, block: dict[str, Any]) -> None:
    headers = ["明细项", "金额"]
    dws.append(headers)
    for cell in dws[1]:
        cell.font = _BOLD
    for ln in block.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        ln_name = ln.get("name") or ""
        ln_amt = ln.get("amt_disp") if ln.get("amt_disp") is not None else ""
        dws.append([ln_name, ln_amt])
        row_idx = dws.max_row
        for col in range(1, 3):
            dws.cell(row=row_idx, column=col).font = _NORMAL
    _set_col_widths(dws, headers)


def _write_meta_sheet(
    mws: Worksheet,
    *,
    scope_label: str,
    period_key: str,
    version: str,
    is_bu: bool,
    export_time: str | None,
) -> None:
    when = export_time or time.strftime("%Y-%m-%d %H:%M:%S")
    info_rows = [
        ("产品", "甲骨易经营看板"),
        ("VERSION", str(version or "")),
        ("范围", str(scope_label or ("整体" if not is_bu else ""))),
        ("周期", str(period_key)),
        ("导出时间", when),
        ("口径", "与看板管理利润表当前筛选一致；金额为展示串"),
    ]
    mws.append(["项", "值"])
    for cell in mws[1]:
        cell.font = _BOLD
    for k, v in info_rows:
        mws.append([k, v])
    mws.column_dimensions["A"].width = 12
    mws.column_dimensions["B"].width = 56


def build_pl_xlsx_bytes(
    summary: dict,
    *,
    period_key: str,
    is_bu: bool,
    scope_label: str,
    version: str = "",
    export_time: str | None = None,
) -> bytes:
    """组装管理利润表 xlsx。

    Parameters
    ----------
    summary : dict
        整体或该 BU 的 summary（与页面 VM 同源）。
    period_key : str
        周期键（与 store.period / ?blk= 一致）。
    is_bu : bool
        是否按 BU 利润表结构（费用抽屉等）。
    scope_label : str
        「整体」或 BU 名，写入导出说明与文件名语义。
    version : str
        产品 VERSION，可空。
    export_time : str | None
        导出时间串；默认当前本地时间。

    Raises
    ------
    KeyError
        period_key 不在 pack 结果中（路由层应转 400）。
    """
    from viewmodels.packers import pack_pl_by_period

    packed = pack_pl_by_period(summary, is_bu=is_bu)
    if period_key not in packed:
        raise KeyError(period_key)
    pl: dict[str, Any] = packed[period_key]
    rows = list(pl.get("rows") or [])
    details = dict(pl.get("details") or {})

    wb = openpyxl.Workbook()
    used_names: set[str] = set()

    ws = wb.active
    assert ws is not None
    ws.title = _safe_sheet_name("管理利润表", used_names)
    _write_main_sheet(ws, rows)

    for open_key, block in details.items():
        if not isinstance(block, dict):
            continue
        title = block.get("title") or str(open_key)
        sheet_title = _safe_sheet_name(
            _short_detail_sheet_title(str(open_key), str(title)), used_names
        )
        dws = wb.create_sheet(title=sheet_title)
        _write_detail_sheet(dws, block)

    mws = wb.create_sheet(title=_safe_sheet_name("导出说明", used_names))
    _write_meta_sheet(
        mws,
        scope_label=scope_label,
        period_key=period_key,
        version=version,
        is_bu=is_bu,
        export_time=export_time,
    )

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def pl_xlsx_filename(*, scope_label: str, period_key: str, day: str | None = None) -> str:
    """RFC 文件名：管理利润表_{范围}_{period}_{YYYYMMDD}.xlsx"""
    d = day or time.strftime("%Y%m%d")
    scope = safe_filename_part(scope_label or "整体")
    period = safe_filename_part(period_key or "")
    return f"管理利润表_{scope}_{period}_{d}.xlsx"
