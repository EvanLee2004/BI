#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手写 SVG 图（无外部库）。颜色全部走 CSS 变量 var(--x)，所以暗色/亮色主题切换时图自动跟随。
提示文字在 Python 里拼好塞进 data-tip，JS 只负责显示/定位，不做任何金额运算（守"客户端不算数"铁律）。"""
from __future__ import annotations

import math
from typing import Sequence

BLUE = "var(--blue)"; COST = "var(--cost)"; ORANGE = "var(--orange)"; TEAL = "var(--teal)"
POS = "var(--pos)"; NEG = "var(--neg)"; PURPLE = "var(--purple)"
INK = "var(--ink)"; MUT = "var(--mut)"; MUT2 = "var(--mut2)"
LINE = "var(--line)"; TRACK = "var(--track)"


def value_color(val: float) -> str:
    return POS if val >= 0 else NEG


def fmt_wan(v: float) -> str:
    if v == 0:
        v = 0.0
    return f"{v/10000:,.1f}"


def esc(s) -> str:
    """HTML 转义（正文与属性通用）。台账/调整来的自由文本进 HTML 前必须过这里（与 render._esc 同口径）。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _polar(cx, cy, r, deg):
    rad = math.radians(deg - 90)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def sparkline(values: Sequence[float], color: str = BLUE, w: int = 108, h: int = 30) -> str:
    """迷你趋势线：一串数值画成小折线（KPI 卡用）。值全部 Python 侧传入，前端不算数。
    纵向按本串 min..max 归一（含负值也能画）；末点加圆点强调最新。"""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none"></svg>'
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 3.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + (w - 2 * pad) * (i / (n - 1))
        y = pad + (h - 2 * pad) * (1 - (v - lo) / span)
        pts.append((x, y))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none">'
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.1" fill="{color}"/></svg>')


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
            # 双层转义：getAttribute 解一层实体、innerHTML 再解析一层——_tip 里名称已转义（innerHTML层），
            # 这里整串再 esc 一次（属性层），<br> 经属性层解码后恢复、名称仍保持转义。
            cls = ' class="hit-seg"'; tip = f' data-tip="{esc(_tip(name, v, detail.get(name)))}"'
        paths.append(f'<path{cls} d="M{x1:.1f} {y1:.1f} A{ro:.1f} {ro:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} '
                     f'L{x3:.1f} {y3:.1f} A{ri:.1f} {ri:.1f} 0 {large} 0 {x4:.1f} {y4:.1f} Z" fill="{color}"{tip}/>')
        start = end
    body = "".join(paths) or f'<circle cx="{cx}" cy="{cy}" r="{ro}" fill="{TRACK}"/>'
    import math as _m
    rmid = (ro + ri) / 2
    sweep = (f'<circle class="donut-sweep" cx="{cx}" cy="{cy}" r="{rmid:.1f}" fill="none" stroke="#eafcff" '
             f'stroke-width="{ro - ri:.1f}" stroke-dasharray="30 {2 * _m.pi * rmid:.0f}" stroke-linecap="round">'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" '
             f'dur="6s" repeatCount="indefinite"/></circle>')
    return (f'<svg viewBox="0 0 {size} {size}" style="max-width:100%;max-height:{size}px;display:block;margin:0 auto">'
            f'{body}{sweep}<text x="{cx}" y="{cy-6}" text-anchor="middle" font-size="12" fill="{MUT}">{center_label}</text>'
            f'<text x="{cx}" y="{cy+17}" text-anchor="middle" font-size="20" font-weight="700" fill="{INK}">{center_value}</text></svg>')


def _tip(title, total, pairs, limit=6):
    """悬浮提示文本：动态名称先转义（细类名来自台账自由填写列），<br> 是我们自己拼的富文本、放行。"""
    lines = [f"{esc(title)}&nbsp;·&nbsp;{fmt_wan(total)}万"]
    if pairs:
        ordered = sorted(pairs, key=lambda x: -x[1])
        for name, amt in ordered[:limit]:
            lines.append(f"{esc(name)}&nbsp;{fmt_wan(amt)}万")
        if ordered[limit:]:
            lines.append(f"其他{len(ordered[limit:])}项&nbsp;{fmt_wan(sum(a for _, a in ordered[limit:]))}万")
    return "<br>".join(lines)


def combo_bar_line_chart(groups: list[tuple[str, float, float, float]], highlight_label: str | None = None) -> str:
    """[(label, 收入, 成本, 毛利率%), ...] 收入/成本双柱 + 毛利率折线。
    柱顶常显收入/成本（万）；毛利率%标在月下（不标在折线点上）。
    折线带 flowline 流光 + comet 光点动效；柱带光晕。
    柱高留顶空（headroom）保证最高柱的金额字一定在柱上方。"""
    w, h = 640, 300
    pl, pr, pt, pb = 54, 36, 34, 50
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(groups)
    if n == 0:
        return f'<div style="color:{MUT2};font-size:12px">暂无数据</div>'
    mx = max((max(rev, cost) for _, rev, cost, _ in groups), default=0) or 1
    # 柱最多占 plot 的 88%，顶部留给金额字
    bar_h = plot_h * 0.88
    gw = plot_w / n
    bw = min(gw * 0.22, 18)
    parts, line_pts, hits = [], [], []
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{pl-8}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
                     f'{"0" if frac==0 else fmt_wan(mx*frac)+"万"}</text>')
        parts.append(f'<text x="{w-pr+6}" y="{y+3:.1f}" text-anchor="start" font-size="10" fill="{MUT2}">'
                     f'{frac*100:.0f}%</text>')
    for i, (label, rev, cost, margin) in enumerate(groups):
        cx = pl + gw * i + gw / 2
        rh = max(1.0, rev / mx * bar_h) if rev else 1.0
        chh = max(1.0, cost / mx * bar_h) if cost else 1.0
        is_hl = highlight_label is not None and label == highlight_label
        ry, cy = pt + plot_h - rh, pt + plot_h - chh
        parts.append(f'<rect class="bar" style="animation-delay:{i*0.05:.2f}s;filter:drop-shadow(0 0 5px {BLUE})" '
                     f'x="{cx-bw-2:.1f}" y="{ry:.1f}" width="{bw:.1f}" height="{rh:.1f}" rx="3" fill="{BLUE}" opacity="0.92"/>')
        parts.append(f'<rect class="bar" style="animation-delay:{i*0.05:.2f}s" '
                     f'x="{cx+2:.1f}" y="{cy:.1f}" width="{bw:.1f}" height="{chh:.1f}" rx="3" fill="{COST}" opacity="0.85"/>')
        # 金额始终在柱顶上方（不夹进柱内）
        parts.append(f'<text x="{cx-bw/2-1:.1f}" y="{ry-5:.1f}" text-anchor="middle" '
                     f'font-size="9.5" font-weight="700" fill="{BLUE}">{fmt_wan(rev)}</text>')
        parts.append(f'<text x="{cx+bw/2+3:.1f}" y="{cy-5:.1f}" text-anchor="middle" '
                     f'font-size="9" font-weight="600" fill="{MUT}">{fmt_wan(cost)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h-pb+15:.1f}" text-anchor="middle" font-size="11" '
                     f'font-weight="{"700" if is_hl else "400"}" fill="{INK if is_hl else MUT}">{label}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h-pb+30:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" '
                     f'fill="{ORANGE}">{margin:.0f}%</text>')
        ly = pt + plot_h * (1 - max(0.0, min(margin, 100.0)) / 100.0)
        line_pts.append((cx, ly))
        tip = (f"{label}<br>交付收入&nbsp;{fmt_wan(rev)}万&nbsp;·&nbsp;交付成本&nbsp;{fmt_wan(cost)}万"
               f"<br>毛利率&nbsp;{margin:.1f}%")
        hits.append(f'<rect class="hit" data-tip="{tip}" x="{pl+gw*i:.1f}" y="{pt:.1f}" width="{gw:.1f}" '
                    f'height="{plot_h:.1f}" fill="transparent"/>')
    if len(line_pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        mpath = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{ORANGE}" stroke-width="2.2" '
                     f'stroke-linejoin="round" stroke-linecap="round" opacity="0.88"/>')
        parts.append(f'<polyline class="flowline" points="{poly}" fill="none" stroke="#fff" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<circle class="comet" r="3" fill="#fff">'
                     f'<animateMotion dur="3.2s" repeatCount="indefinite" path="{mpath}"/></circle>')
    for x, y in line_pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{ORANGE}" stroke="#04101c" stroke-width="1.2"/>')
    legend = (f'<div class="legend"><span><i style="background:{BLUE}"></i>交付收入（柱顶·万）</span>'
              f'<span><i style="background:{COST}"></i>交付成本（柱顶·万）</span>'
              f'<span><i style="background:{ORANGE}"></i>毛利率（月下·% · 右轴）</span></div>')
    return f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">{"".join(parts)}{"".join(hits)}</svg>{legend}'


def receipt_order_chart(series: list[tuple[str, float, float, float | None]], color: str = BLUE,
                        budget_month: float | None = None) -> str:
    """回款柱 + 回款/下单比折线。
    柱顶=回款万（蓝色，与交付收入柱顶统一）；率%在月下；flowline+comet；柱高留顶空。"""
    w, h = 640, 352   # v1.0.5.1 拉高：左图放大后与右侧「累计与缺口」等高对称，不再下方留白
    pl, pr, pt, pb = 52, 40, 34, 50
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(series)
    if n == 0:
        return f'<div style="color:{MUT2};font-size:12px">暂无数据</div>'
    mx = max((v for _, v, _, _ in series), default=0) or 1
    if budget_month:
        mx = max(mx, budget_month * 1.15)
    ratios = [r for _, _, _, r in series if r is not None]
    rmx = max(ratios) if ratios else 0.0
    rmx_axis = max(rmx, 100.0) if ratios else 100.0
    bar_h = plot_h * 0.88
    gw = plot_w / n
    bw = min(gw * 0.38, 28)
    parts, hits, line_pts = [], [], []
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w-pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{pl-6}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
                     f'{"0" if frac==0 else fmt_wan(mx*frac)+"万"}</text>')
        if ratios:
            parts.append(f'<text x="{w-pr+6}" y="{y+3:.1f}" text-anchor="start" font-size="10" fill="{MUT2}">'
                         f'{rmx_axis*frac:.0f}%</text>')
    for i, (label, rec, _order, ratio) in enumerate(series):
        cx = pl + gw * i + gw / 2
        bh = max(1.0, rec / mx * bar_h) if rec else 0.0
        by = pt + plot_h - bh
        parts.append(f'<rect class="bar" style="animation-delay:{i*0.05:.2f}s;filter:drop-shadow(0 0 5px {color})" '
                     f'x="{cx-bw/2:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{max(bh, 1.0):.1f}" rx="3" '
                     f'fill="{color}" opacity="0.9"/>')
        # 柱顶金额用蓝色，与交付收入图统一
        parts.append(f'<text x="{cx:.1f}" y="{by-5:.1f}" text-anchor="middle" font-size="10.5" '
                     f'font-weight="700" fill="{BLUE}">{fmt_wan(rec)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h-pb+15:.1f}" text-anchor="middle" font-size="11.5" fill="{MUT}">{label}</text>')
        if ratio is not None:
            parts.append(f'<text x="{cx:.1f}" y="{h-pb+30:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" '
                         f'fill="{ORANGE}">{ratio:.0f}%</text>')
            ly = pt + plot_h * (1 - max(0.0, min(ratio / rmx_axis, 1.0)))
            line_pts.append((cx, ly))
        tip = (f"{label}<br>回款&nbsp;{fmt_wan(rec)}万&nbsp;·&nbsp;下单&nbsp;{fmt_wan(_order)}万"
               f"{('<br>回款/下单比&nbsp;'+format(ratio,'.1f')+'%') if ratio is not None else ''}")
        hits.append(f'<rect class="hit" data-tip="{tip}" x="{pl+gw*i:.1f}" y="{pt:.1f}" width="{gw:.1f}" '
                    f'height="{plot_h:.1f}" fill="transparent"/>')
    if budget_month:
        by = pt + plot_h * (1 - budget_month / mx)
        parts.append(f'<line x1="{pl}" y1="{by:.1f}" x2="{w-pr}" y2="{by:.1f}" stroke="{TEAL}" '
                     f'stroke-width="1.4" stroke-dasharray="5 4" opacity="0.9"/>')
        parts.append(f'<text x="{w-pr-2:.1f}" y="{by-4:.1f}" text-anchor="end" font-size="9.5" fill="{TEAL}">'
                     f'月均预算 {fmt_wan(budget_month)}万</text>')
    if len(line_pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        mpath = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in line_pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{ORANGE}" stroke-width="2.2" '
                     f'stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>')
        parts.append(f'<polyline class="flowline" points="{poly}" fill="none" stroke="#fff" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<circle class="comet" r="3" fill="#fff">'
                     f'<animateMotion dur="3.2s" repeatCount="indefinite" path="{mpath}"/></circle>')
    for x, y in line_pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{ORANGE}" stroke="#04101c" stroke-width="1.2"/>')
    legend = (f'<div class="legend"><span><i style="background:{color}"></i>回款额（柱顶·万）</span>'
              f'<span><i style="background:{ORANGE}"></i>回款/下单比（月下·% · 右轴）</span>')
    if budget_month:
        legend += f'<span><i style="background:{TEAL}"></i>月均预算</span>'
    legend += '</div>'
    return (f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;max-height:300px;display:block">'
            f'{"".join(parts)}{"".join(hits)}</svg>{legend}')

