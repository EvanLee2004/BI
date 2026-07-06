#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手写 SVG 图（无外部库）。颜色全部走 CSS 变量 var(--x)，所以暗色/亮色主题切换时图自动跟随。
提示文字在 Python 里拼好塞进 data-tip，JS 只负责显示/定位，不做任何金额运算（守"客户端不算数"铁律）。"""
from __future__ import annotations

import math
from typing import Sequence

BLUE = "var(--blue)"; COST = "var(--cost)"; ORANGE = "var(--orange)"
POS = "var(--pos)"; NEG = "var(--neg)"; PURPLE = "var(--purple)"
INK = "var(--ink)"; MUT = "var(--mut)"; MUT2 = "var(--mut2)"
LINE = "var(--line)"; TRACK = "var(--track)"


def value_color(val: float) -> str:
    return POS if val >= 0 else NEG


def fmt_wan(v: float) -> str:
    if v == 0:
        v = 0.0
    return f"{v/10000:,.1f}"


def _polar(cx, cy, r, deg):
    rad = math.radians(deg - 90)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def mini_ring(pct: float, color: str | None = None, size: int = 64) -> str:
    color = color or value_color(pct)
    cx = cy = size / 2
    r = size * 0.38
    sw = size * 0.15
    circ = 2 * math.pi * r
    dash = circ * max(0.0, min(pct, 100.0)) / 100
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" style="display:block;flex:0 0 auto">'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{TRACK}" stroke-width="{sw:.1f}"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{sw:.1f}" '
        f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})" '
        f'style="filter:drop-shadow(0 0 4px {color})"/>'
        f'<text x="{cx}" y="{cy+size*0.08:.1f}" text-anchor="middle" font-size="{size*0.24:.0f}" '
        f'font-weight="700" fill="{INK}">{pct:.0f}%</text></svg>'
    )


def donut(segs: Sequence[tuple[str, float, str]], center_label: str, center_value: str,
          size: int = 190, detail: dict | None = None) -> str:
    total = sum(max(v, 0) for _, v, _ in segs) or 1
    cx = cy = size / 2
    ro, ri = size * 0.42, size * 0.27
    start = 0.0
    paths = []
    for name, v, color in segs:
        if v <= 0:
            continue
        end = start + v / total * 360
        large = 1 if (end - start) > 180 else 0
        x1, y1 = _polar(cx, cy, ro, start); x2, y2 = _polar(cx, cy, ro, end)
        x3, y3 = _polar(cx, cy, ri, end); x4, y4 = _polar(cx, cy, ri, start)
        tip = ""
        cls = ""
        if detail is not None:
            cls = ' class="hit-seg"'; tip = f' data-tip="{_tip(name, v, detail.get(name))}"'
        paths.append(f'<path{cls} d="M{x1:.1f} {y1:.1f} A{ro:.1f} {ro:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} '
                     f'L{x3:.1f} {y3:.1f} A{ri:.1f} {ri:.1f} 0 {large} 0 {x4:.1f} {y4:.1f} Z" fill="{color}"{tip}/>')
        start = end
    body = "".join(paths) or f'<circle cx="{cx}" cy="{cy}" r="{ro}" fill="{TRACK}"/>'
    return (f'<svg viewBox="0 0 {size} {size}" style="max-width:100%;max-height:{size}px;display:block;margin:0 auto">'
            f'{body}<text x="{cx}" y="{cy-6}" text-anchor="middle" font-size="12" fill="{MUT}">{center_label}</text>'
            f'<text x="{cx}" y="{cy+17}" text-anchor="middle" font-size="20" font-weight="700" fill="{INK}">{center_value}</text></svg>')


def _tip(title, total, pairs, limit=6):
    lines = [f"{title}&nbsp;·&nbsp;{fmt_wan(total)}万"]
    if pairs:
        ordered = sorted(pairs, key=lambda x: -x[1])
        for name, amt in ordered[:limit]:
            lines.append(f"{name}&nbsp;{fmt_wan(amt)}万")
        if ordered[limit:]:
            lines.append(f"其他{len(ordered[limit:])}项&nbsp;{fmt_wan(sum(a for _, a in ordered[limit:]))}万")
    return "<br>".join(lines)


def combo_bar_line_chart(groups: list[tuple[str, float, float, float]], highlight_label: str | None = None) -> str:
    """[(label, 收入, 成本, 毛利率%), ...] 月度组合图：收入/成本双柱 + 毛利率折线。"""
    w, h = 580, 250
    pl, pr, pt, pb = 64, 18, 18, 34
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(groups)
    if n == 0:
        return f'<div style="color:{MUT2};font-size:12px">暂无数据</div>'
    mx = max((max(rev, cost) for _, rev, cost, _ in groups), default=0) or 1
    gw = plot_w / n
    bw = min(gw * 0.26, 22)
    parts, line_pts, hits = [], [], []
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{pl-8}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
                     f'{"0" if frac==0 else fmt_wan(mx*frac)+"万"}</text>')
    for i, (label, rev, cost, margin) in enumerate(groups):
        cx = pl + gw * i + gw / 2
        rh = max(1.0, rev / mx * plot_h); chh = max(1.0, cost / mx * plot_h)
        is_hl = highlight_label is not None and label == highlight_label
        # 趋势图每月柱子一样亮（都是真实数据，不调暗）；当前月只靠下方标签加粗做轻提示
        parts.append(f'<rect x="{cx-bw-2:.1f}" y="{pt+plot_h-rh:.1f}" width="{bw:.1f}" height="{rh:.1f}" rx="3" '
                     f'fill="{BLUE}" style="filter:drop-shadow(0 0 5px {BLUE})"/>')
        parts.append(f'<rect x="{cx+2:.1f}" y="{pt+plot_h-chh:.1f}" width="{bw:.1f}" height="{chh:.1f}" rx="3" '
                     f'fill="{COST}"/>')
        parts.append(f'<text x="{cx:.1f}" y="{h-pb+18:.1f}" text-anchor="middle" font-size="11.5" '
                     f'font-weight="{"700" if is_hl else "400"}" fill="{INK if is_hl else MUT}">{label}</text>')
        ly = pt + plot_h * (1 - max(0.0, min(margin, 100.0)) / 100)
        line_pts.append((cx, ly))
        tip = f"{label}<br>收入&nbsp;{fmt_wan(rev)}万&nbsp;·&nbsp;成本&nbsp;{fmt_wan(cost)}万<br>毛利率&nbsp;{margin:.1f}%"
        hits.append(f'<rect class="hit" data-tip="{tip}" x="{pl+gw*i:.1f}" y="{pt:.1f}" width="{gw:.1f}" '
                    f'height="{plot_h:.1f}" fill="transparent"/>')
    if len(line_pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{ORANGE}" stroke-width="2.5" '
                     f'stroke-linejoin="round" stroke-linecap="round" style="filter:drop-shadow(0 0 4px {ORANGE})"/>')
    for x, y in line_pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{ORANGE}"/>')
    legend = (f'<div class="legend"><span><i style="background:{BLUE}"></i>收入</span>'
              f'<span><i style="background:{COST}"></i>成本</span>'
              f'<span><i style="background:{ORANGE}"></i>毛利率</span>'
              f'<span style="margin-left:auto;color:{MUT2}">悬浮/点击柱子看当月明细</span></div>')
    return f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">{"".join(parts)}{"".join(hits)}</svg>{legend}'


def month_bar_chart(series: list[tuple[str, float]], color: str = BLUE) -> str:
    """[(label, amount), ...] 简单月度柱状图（回款按月）。"""
    w, h = 580, 210
    pl, pr, pt, pb = 64, 18, 16, 30
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(series)
    if n == 0:
        return f'<div style="color:{MUT2};font-size:12px">暂无数据</div>'
    mx = max((v for _, v in series), default=0) or 1
    gw = plot_w / n
    bw = min(gw * 0.5, 34)
    parts, hits = [], []
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{pl-8}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
                     f'{"0" if frac==0 else fmt_wan(mx*frac)+"万"}</text>')
    for i, (label, v) in enumerate(series):
        cx = pl + gw * i + gw / 2
        bh = max(1.0, v / mx * plot_h)
        parts.append(f'<rect x="{cx-bw/2:.1f}" y="{pt+plot_h-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" '
                     f'fill="{color}" style="filter:drop-shadow(0 0 5px {color})"/>')
        parts.append(f'<text x="{cx:.1f}" y="{h-pb+17:.1f}" text-anchor="middle" font-size="11.5" fill="{MUT}">{label}</text>')
        hits.append(f'<rect class="hit" data-tip="{label}&nbsp;回款&nbsp;{fmt_wan(v)}万" x="{pl+gw*i:.1f}" '
                    f'y="{pt:.1f}" width="{gw:.1f}" height="{plot_h:.1f}" fill="transparent"/>')
    return f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">{"".join(parts)}{"".join(hits)}</svg>'


def hbar_list(items: list[tuple[str, float]], color: str = BLUE) -> str:
    if not items:
        return f'<div style="color:{MUT2};font-size:12px;padding:8px 0">暂无数据</div>'
    mx = max((v for _, v in items), default=0) or 1
    rows = []
    for name, v in items:
        pct = max(0.0, min(v / mx * 100, 100.0))
        rows.append(f'<div class="hbar"><span class="hbar-n" title="{name}">{name}</span>'
                    f'<div class="hbar-t"><div class="hbar-f" style="width:{pct:.1f}%;background:{color}"></div></div>'
                    f'<span class="hbar-v">{fmt_wan(v)}万</span></div>')
    return "".join(rows)
