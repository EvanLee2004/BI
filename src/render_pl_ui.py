#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 render.py 纯搬家（任务书54.13）；禁止改算法。"""
from __future__ import annotations

import tpl
from render_widgets import (
    _amt,
    _esc,
)


def _row(name, impact, kind, src="", total=False, grand=False):
    cls = "pl-row" + (" total grand" if grand else " total" if total else "")
    dot = tpl.fill("render/dot.html", kind=kind) if kind else tpl.load("render/dot_none.html")
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    return tpl.fill(
        "render/pl_row.html", cls=cls, dot=dot, name=name, src_html=src_html, amt=_amt(impact, colored=(total or grand))
    )

def _pct_row(name, pct, src=""):
    """比率行（如税前利润率）：金额列显示百分数，不参与任何求和。pct=None → 灰显 —。"""
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    txt = f"{pct:.1f}%" if pct is not None else "—"
    return tpl.fill("render/pct_row.html", name=name, src_html=src_html, txt=txt)

def _open_row(cat, name, impact):
    """可点大类行：点击弹出右侧抽屉看构成（不再就地展开、不顶下方图表）。"""
    return tpl.fill("render/open_row.html", cat=cat, name=name, amt=_amt(impact))

def _drow(name, impact, kind, src="", sub=False):
    """抽屉内明细行（始终展开、无需切换）。
    金额只显示绝对值：行名已带「加/减」语义，用户只看数额；主表利润影响仍走 _row/_open_row 带符号。"""
    cls = "pl-drow" + (" sub" if sub else "")
    dot = tpl.fill("render/dot.html", kind=kind) if kind else tpl.load("render/dot_none.html")
    src_html = tpl.fill("render/src.html", src=src) if src else ""
    return tpl.fill(
        "render/drow.html", cls=cls, dot=dot, name=_esc(name), src_html=src_html, amt=_amt(abs(float(impact or 0)))
    )

def _d_ledger(name, amount, src, fine_pairs, limit=8):
    """抽屉内台账叶子 + 其费用明细细类（平铺，不再二次点开）。"""
    out = _drow(name, -amount, "ledger", src)
    pairs = sorted(fine_pairs or [], key=lambda x: -x[1])
    for n, a in pairs[:limit]:
        out += _drow(n, -a, "", "", sub=True)
    rest = pairs[limit:]
    if rest:
        out += _drow(f"其他{len(rest)}项", -sum(a for _, a in rest), "", "", sub=True)
    return out

def _detail_block(cat, title, inner):
    return tpl.fill("render/detail_block.html", cat=_esc(cat), title=_esc(title), inner=inner)

def _pl_structure_to_html(struct, *, bu_display: bool = False) -> str:  # noqa: C901
    """任务书51·B2：结构 → legacy 利润表 HTML（与重构前逐字节对齐）。"""
    row_html: list[str] = []
    for r in struct.get("rows") or []:
        if r.get("pending"):
            row_html.append(_bu_pending_row(r["name"]))
            continue
        if r.get("is_pct"):
            row_html.append(_pct_row(r["name"], r.get("pct"), r.get("formula") or ""))
            continue
        impact = float(r.get("impact") or 0)
        ok = r.get("open_key")
        formula = r.get("formula") or ""
        if bu_display and r.get("name") == "税前利润" and r.get("grand"):
            formula = "毛利−期间费用−附加税±其他"
        if ok:
            row_html.append(_open_row(ok, r["name"], impact))
        else:
            row_html.append(
                _row(
                    r["name"],
                    impact,
                    r.get("kind") or "",
                    formula,
                    total=bool(r.get("total")),
                    grand=bool(r.get("grand")),
                )
            )

    pending_keys = {r.get("open_key") for r in (struct.get("rows") or []) if r.get("pending") and r.get("open_key")}
    # 顺序：cost → sales/admin/fixed/rd/fin（与旧 render 一致）
    order = ["cost", "sales", "admin", "fixed", "rd", "fin"]
    details = struct.get("details") or {}
    detail_parts: list[str] = []
    for cat in order:
        if cat not in details or cat in pending_keys:
            continue
        block = details[cat]
        title = block.get("title") or ""
        if bu_display and cat == "cost":
            title = "交付成本构成"
        inner = ""
        for ln in block.get("lines") or []:
            kind = ln.get("kind") or ""
            # 旧 HTML：系统内部译员传正值、其余抽屉行传负值；_drow 最终 abs 显示
            raw = float(ln.get("impact") or 0)
            if ln.get("name") == "系统内部译员":
                signed = raw
            else:
                signed = -raw
            inner += _drow(ln["name"], signed, kind, "", sub=bool(ln.get("sub")))
        detail_parts.append(_detail_block(cat, title, inner))

    kinds = tpl.load("render/kinds.html")
    return tpl.fill(
        "render/pl_table.html",
        rows="".join(row_html),
        kinds=kinds,
        details="".join(detail_parts),
    )

def render_pl_table(p, fine, unclassified_amt=None):
    """管理利润表（看端·领导视角）：任务书51·B2 消费 pl_structure → HTML。"""
    from domain.pl.structure import pl_structure

    unc = float(unclassified_amt) if unclassified_amt and float(unclassified_amt) > 0 else None
    struct = pl_structure(p, fine or {}, is_bu=False, unclassified_amt=unc)
    return _pl_structure_to_html(struct, bu_display=False)

def _bu_pending_row(name, note="—"):
    """待补数据行：金额位显示 — 而非 ¥0（不把"没有数"显示成"数是 0"）。"""
    return tpl.fill("render/bu_pending_row.html", name=_esc(name), note=_esc(note))

def render_bu_pl_table(p, alloc_meta=None, fine=None):
    """BU 版利润表：任务书51·B2 消费 pl_structure → HTML；返回 (html, tag_note)。"""
    from domain.pl.structure import pl_structure

    struct = pl_structure(p, fine or {}, is_bu=True, alloc_meta=alloc_meta or {})
    return _pl_structure_to_html(struct, bu_display=True), struct.get("tag_note") or ""

