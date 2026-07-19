#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手写 SVG 图（无外部库）。颜色全部走 CSS 变量 var(--x)，所以暗色/亮色主题切换时图自动跟随。
提示文字在 Python 里拼好塞进 data-tip，JS 只负责显示/定位，不做任何金额运算（守"客户端不算数"铁律）。"""

from __future__ import annotations

import math
from typing import Sequence

import tpl

BLUE = "var(--blue)"
COST = "var(--cost)"
ORANGE = "var(--orange)"
TEAL = "var(--teal)"
POS = "var(--pos)"
NEG = "var(--neg)"
PURPLE = "var(--purple)"
INK = "var(--ink)"
MUT = "var(--mut)"
MUT2 = "var(--mut2)"
LINE = "var(--line)"
TRACK = "var(--track)"


def value_color(val: float) -> str:
    return POS if val >= 0 else NEG


def fmt_wan(v: float) -> str:
    """金额 → 万元显示串。任务书33·A3 起入参为**分**（INTEGER）；÷100 得元再 ÷10000。

    与改造前「元 ÷10000」在合法分金额上逐位一致（分=元×100）。
    """
    if v is None:
        v = 0
    try:
        fen = int(v)
    except (TypeError, ValueError):
        fen = 0
    if fen == 0:
        return f"{0.0:,.1f}"
    yuan = fen / 100.0
    return f"{yuan / 10000:,.1f}"


def esc(s) -> str:
    """HTML 转义（正文与属性通用）。台账/调整来的自由文本进 HTML 前必须过这里（与 render._esc 同口径）。"""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
    return (
        f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none">'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.1" fill="{color}"/></svg>'
    )


def donut(
    segs: Sequence[tuple[str, float, str]],
    center_label: str,
    center_value: str,
    size: int = 300,
    detail: dict | None = None,
) -> str:
    """环形图。size 默认 300（卡框 ev-body 仍 360，只放大圆盘不撑大外框）。"""
    total = sum(max(v, 0) for _, v, _ in segs) or 1
    cx = cy = size / 2
    # 略加大外径占比，环更饱满；内径同步，中心字仍清晰
    ro, ri = size * 0.45, size * 0.29
    start = 0.0
    paths = []
    for name, v, color in segs:
        if v <= 0:
            continue
        end = start + v / total * 360
        large = 1 if (end - start) > 180 else 0
        x1, y1 = _polar(cx, cy, ro, start)
        x2, y2 = _polar(cx, cy, ro, end)
        x3, y3 = _polar(cx, cy, ri, end)
        x4, y4 = _polar(cx, cy, ri, start)
        tip = ""
        # donut-seg：CSS 用 stroke:var(--bg) 做分段缝；hit-seg 可悬浮
        dcls = "donut-seg"
        if detail is not None:
            # 双层转义：getAttribute 解一层实体、innerHTML 再解析一层——_tip 里名称已转义（innerHTML层），
            # 这里整串再 esc 一次（属性层），<br> 经属性层解码后恢复、名称仍保持转义。
            dcls = "donut-seg hit-seg"
            tip = f' data-tip="{esc(_tip(name, v, detail.get(name)))}"'
        paths.append(
            f'<path class="{dcls}" d="M{x1:.1f} {y1:.1f} A{ro:.1f} {ro:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} '
            f'L{x3:.1f} {y3:.1f} A{ri:.1f} {ri:.1f} 0 {large} 0 {x4:.1f} {y4:.1f} Z" fill="{color}"{tip}/>'
        )
        start = end
    body = "".join(paths) or f'<circle cx="{cx}" cy="{cy}" r="{ro}" fill="{TRACK}"/>'
    import math as _m

    rmid = (ro + ri) / 2
    sweep = (
        f'<circle class="donut-sweep" cx="{cx}" cy="{cy}" r="{rmid:.1f}" fill="none" stroke="#eafcff" '
        f'stroke-width="{ro - ri:.1f}" stroke-dasharray="30 {2 * _m.pi * rmid:.0f}" stroke-linecap="round">'
        f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" '
        f'dur="6s" repeatCount="indefinite"/></circle>'
    )
    # 中心字号随环放大，卡框高度不变；max-height 略留图例位（~48px）防撑破 360
    fs_lab, fs_val = max(12, int(size * 0.052)), max(20, int(size * 0.09))
    max_h = min(size, 308)
    return (
        f'<svg viewBox="0 0 {size} {size}" style="max-width:100%;max-height:{max_h}px;width:min(100%,{size}px);display:block;margin:0 auto;flex:0 0 auto">'
        f'{body}{sweep}<text x="{cx}" y="{cy - size * 0.035:.1f}" text-anchor="middle" font-size="{fs_lab}" fill="{MUT}">{center_label}</text>'
        f'<text x="{cx}" y="{cy + size * 0.07:.1f}" text-anchor="middle" font-size="{fs_val}" font-weight="700" fill="{INK}">{center_value}</text></svg>'
    )


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
    柱顶常显收入/成本（万）；毛利率%标在折线数据点旁（默认点上方）。
    折线带 flowline 流光 + comet 光点动效；柱带光晕。
    柱高留顶空（headroom）保证最高柱的金额字一定在柱上方。
    任务书46·0：板块二图表高度 +10%（288→317）。"""
    w, h = 640, 317
    pl, pr, pt, pb = 54, 36, 34, 32
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(groups)
    if n == 0:
        return tpl.fill("charts/empty.html", color=MUT2)
    mx = max((max(rev, cost) for _, rev, cost, _ in groups), default=0) or 1
    # 柱最多占 plot 的 88%，顶部留给金额字
    bar_h = plot_h * 0.88
    gw = plot_w / n
    bw = min(gw * 0.22, 18)
    parts, line_pts, hits = [], [], []
    # 柱渐变：stop-color 走 CSS 变量，暗/亮主题自动跟随
    parts.append(
        f"<defs>"
        f'<linearGradient id="barGradRev" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BLUE}" stop-opacity=".95"/>'
        f'<stop offset="1" stop-color="{BLUE}" stop-opacity=".25"/></linearGradient>'
        f'<linearGradient id="barGradCost" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{COST}" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="{COST}" stop-opacity=".3"/></linearGradient>'
        f"</defs>"
    )
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w - pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(
            f'<text x="{pl - 8}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
            f"{'0' if frac == 0 else fmt_wan(mx * frac) + '万'}</text>"
        )
        parts.append(
            f'<text x="{w - pr + 6}" y="{y + 3:.1f}" text-anchor="start" font-size="10" fill="{MUT2}">'
            f"{frac * 100:.0f}%</text>"
        )
    for i, (label, rev, cost, margin) in enumerate(groups):
        # 月份号：标签形如「1月」/「10月」；供周期高亮 data-rm（与回款卡同约定，纯展示）
        rm = str(i + 1)
        if isinstance(label, str) and label.endswith("月"):
            head = label[:-1]
            if head.isdigit():
                rm = str(int(head))
        drm = f' data-rm="{rm}"'
        cx = pl + gw * i + gw / 2
        rh = max(1.0, rev / mx * bar_h) if rev else 1.0
        chh = max(1.0, cost / mx * bar_h) if cost else 1.0
        is_hl = highlight_label is not None and label == highlight_label
        ry, cy = pt + plot_h - rh, pt + plot_h - chh
        parts.append(
            f'<rect class="bar bar-rev" style="animation-delay:{i * 0.05:.2f}s;filter:drop-shadow(0 0 5px {BLUE})" '
            f'x="{cx - bw - 2:.1f}" y="{ry:.1f}" width="{bw:.1f}" height="{rh:.1f}" rx="3" fill="url(#barGradRev)" opacity="0.95"{drm}/>'
        )
        parts.append(
            f'<rect class="bar bar-cost" style="animation-delay:{i * 0.05:.2f}s" '
            f'x="{cx + 2:.1f}" y="{cy:.1f}" width="{bw:.1f}" height="{chh:.1f}" rx="3" fill="url(#barGradCost)" opacity="0.9"{drm}/>'
        )
        # 金额始终在柱顶上方（不夹进柱内）
        parts.append(
            f'<text x="{cx - bw / 2 - 1:.1f}" y="{ry - 5:.1f}" text-anchor="middle" '
            f'font-size="9.5" font-weight="700" fill="{BLUE}"{drm}>{fmt_wan(rev)}</text>'
        )
        parts.append(
            f'<text x="{cx + bw / 2 + 3:.1f}" y="{cy - 5:.1f}" text-anchor="middle" '
            f'font-size="9" font-weight="600" fill="{MUT}"{drm}>{fmt_wan(cost)}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{h - pb + 15:.1f}" text-anchor="middle" font-size="11" '
            f'font-weight="{"700" if is_hl else "400"}" fill="{INK if is_hl else MUT}"{drm}>{label}</text>'
        )
        ly = pt + plot_h * (1 - max(0.0, min(margin, 100.0)) / 100.0)
        line_pts.append((cx, ly, margin, rm))
        tip = (
            f"{label}<br>交付收入&nbsp;{fmt_wan(rev)}万&nbsp;·&nbsp;交付成本&nbsp;{fmt_wan(cost)}万"
            f"<br>毛利率&nbsp;{margin:.1f}%"
        )
        hits.append(
            f'<rect class="hit" data-tip="{tip}" x="{pl + gw * i:.1f}" y="{pt:.1f}" width="{gw:.1f}" '
            f'height="{plot_h:.1f}" fill="transparent"/>'
        )
    if len(line_pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _m, _rm in line_pts)
        mpath = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y, _m, _rm in line_pts)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="{ORANGE}" stroke-width="2.2" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="0.88"/>'
        )
        parts.append(
            f'<polyline class="flowline" points="{poly}" fill="none" stroke="#fff" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        parts.append(
            f'<circle class="comet" r="3" fill="#fff">'
            f'<animateMotion dur="3.2s" repeatCount="indefinite" path="{mpath}"/></circle>'
        )
    for x, y, margin, rm in line_pts:
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{ORANGE}" stroke="#04101c" '
            f'stroke-width="1.2" data-rm="{rm}"/>'
        )
        # 毛利率%标在折线点旁（默认点上方；贴顶时改标下方，避免出图）
        ty = y + 15 if y < pt + 20 else y - 8
        parts.append(
            f'<text x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" '
            f'fill="{ORANGE}" data-rm="{rm}">{margin:.0f}%</text>'
        )
    legend = tpl.fill("charts/legend_combo.html", blue=BLUE, cost=COST, orange=ORANGE)
    return (
        f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">{"".join(parts)}{"".join(hits)}</svg>{legend}'
    )


def _roc_bar_grads(color: str) -> str:
    return (
        f"<defs>"
        f'<linearGradient id="barGradOrd" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{PURPLE}" stop-opacity=".95"/>'
        f'<stop offset="1" stop-color="{PURPLE}" stop-opacity=".25"/></linearGradient>'
        f'<linearGradient id="barGradRec" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity=".95"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity=".25"/></linearGradient>'
        f"</defs>"
    )


def _roc_grid_labels(parts, pl, pr, pt, plot_h, w, mx, ratios, rmx_axis) -> None:
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w - pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(
            f'<text x="{pl - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
            f"{'0' if frac == 0 else fmt_wan(mx * frac) + '万'}</text>"
        )
        if ratios:
            parts.append(
                f'<text x="{w - pr + 6}" y="{y + 3:.1f}" text-anchor="start" font-size="10" fill="{MUT2}">'
                f"{rmx_axis * frac:.0f}%</text>"
            )


def _roc_month_rm(label, i: int) -> str:
    rm = str(i + 1)
    if isinstance(label, str) and label.endswith("月"):
        head = label[:-1]
        if head.isdigit():
            rm = str(int(head))
    return rm


def _roc_draw_bars(
    parts, hits, line_pts, series, *, pl, pt, plot_h, h, pb, mx, bar_h, gw, bw, rmx_axis, color
) -> None:
    for i, (label, rec, order, ratio) in enumerate(series):
        rm = _roc_month_rm(label, i)
        drm = f' data-rm="{rm}"'
        cx = pl + gw * i + gw / 2
        oh = max(1.0, (order or 0) / mx * bar_h) if order else 0.0
        rh = max(1.0, (rec or 0) / mx * bar_h) if rec else 0.0
        oy, ry0 = pt + plot_h - oh, pt + plot_h - rh
        parts.append(
            f'<rect class="bar bar-ord" style="animation-delay:{i * 0.05:.2f}s;filter:drop-shadow(0 0 5px {PURPLE})" '
            f'x="{cx - bw - 2:.1f}" y="{oy:.1f}" width="{bw:.1f}" height="{max(oh, 1.0):.1f}" rx="3" '
            f'fill="url(#barGradOrd)" opacity="0.95"{drm}/>'
        )
        parts.append(
            f'<rect class="bar bar-rec" style="animation-delay:{i * 0.05:.2f}s;filter:drop-shadow(0 0 5px {color})" '
            f'x="{cx + 2:.1f}" y="{ry0:.1f}" width="{bw:.1f}" height="{max(rh, 1.0):.1f}" rx="3" '
            f'fill="url(#barGradRec)" opacity="0.95"{drm}/>'
        )
        parts.append(
            f'<text x="{cx - bw / 2 - 1:.1f}" y="{oy - 5:.1f}" text-anchor="middle" font-size="9.5" '
            f'font-weight="700" fill="{PURPLE}"{drm}>{fmt_wan(order or 0)}</text>'
        )
        parts.append(
            f'<text x="{cx + bw / 2 + 3:.1f}" y="{ry0 - 5:.1f}" text-anchor="middle" font-size="9" '
            f'font-weight="600" fill="{BLUE}"{drm}>{fmt_wan(rec or 0)}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{h - pb + 15:.1f}" text-anchor="middle" font-size="11" '
            f'fill="{MUT}"{drm}>{label}</text>'
        )
        if ratio is not None:
            ly = pt + plot_h * (1 - max(0.0, min(ratio / rmx_axis, 1.0)))
            ry = ly + 15 if ly < pt + 20 else ly - 8
            parts.append(
                f'<text class="rl" x="{cx:.1f}" y="{ry:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" '
                f'fill="{ORANGE}"{drm}>{ratio:.0f}%</text>'
            )
            line_pts.append((cx, ly, rm))
        tip = (
            f"{label}<br>下单&nbsp;{fmt_wan(order or 0)}万&nbsp;·&nbsp;回款&nbsp;{fmt_wan(rec or 0)}万"
            f"{('<br>回款/下单比&nbsp;' + format(ratio, '.1f') + '%') if ratio is not None else ''}"
        )
        hits.append(
            f'<rect class="hit" data-tip="{tip}" x="{pl + gw * i:.1f}" y="{pt:.1f}" width="{gw:.1f}" '
            f'height="{plot_h:.1f}" fill="transparent"/>'
        )


def _roc_budget_and_line(parts, line_pts, *, pl, pr, pt, plot_h, w, mx, budget_month) -> None:
    if budget_month:
        by = pt + plot_h * (1 - budget_month / mx)
        parts.append(
            f'<line x1="{pl}" y1="{by:.1f}" x2="{w - pr}" y2="{by:.1f}" stroke="{TEAL}" '
            f'stroke-width="1.4" stroke-dasharray="5 4" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{w - pr - 2:.1f}" y="{by - 4:.1f}" text-anchor="end" font-size="9.5" fill="{TEAL}">'
            f"月均预算 {fmt_wan(budget_month)}万</text>"
        )
    if len(line_pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _rm in line_pts)
        mpath = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y, _rm in line_pts)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="{ORANGE}" stroke-width="2.2" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>'
        )
        parts.append(
            f'<polyline class="flowline" points="{poly}" fill="none" stroke="#fff" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        parts.append(
            f'<circle class="comet" r="3" fill="#fff">'
            f'<animateMotion dur="3.2s" repeatCount="indefinite" path="{mpath}"/></circle>'
        )
    for x, y, rm in line_pts:
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{ORANGE}" stroke="#04101c" '
            f'stroke-width="1.2" data-rm="{rm}"/>'
        )



def receipt_order_chart(
    series: list[tuple[str, float, float, float | None]], color: str = BLUE, budget_month: float | None = None
) -> str:
    """下单柱 + 回款柱 + 回款/下单比折线（A3·陆总#2：同图逐月下单与回款）。
    series=[(label, 回款, 下单, 比率%), ...]；柱顶万；率%在折线点旁。
    任务书39·A：画布规格与板块二趋势图 combo_bar_line_chart 一致（640×288）。"""
    w, h = 640, 288
    pl, pr, pt, pb = 54, 36, 34, 32
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = len(series)
    if n == 0:
        return tpl.fill("charts/empty.html", color=MUT2)
    mx = max((max(rec or 0, order or 0) for _, rec, order, _ in series), default=0) or 1
    if budget_month:
        mx = max(mx, budget_month * 1.15)
    ratios = [r for _, _, _, r in series if r is not None]
    rmx = max(ratios) if ratios else 0.0
    rmx_axis = max(rmx, 100.0) if ratios else 100.0
    bar_h = plot_h * 0.88
    gw = plot_w / n
    bw = min(gw * 0.22, 18)
    parts, hits, line_pts = [], [], []
    parts.append(_roc_bar_grads(color))
    _roc_grid_labels(parts, pl, pr, pt, plot_h, w, mx, ratios, rmx_axis)
    _roc_draw_bars(
        parts, hits, line_pts, series,
        pl=pl, pt=pt, plot_h=plot_h, h=h, pb=pb, mx=mx, bar_h=bar_h, gw=gw, bw=bw,
        rmx_axis=rmx_axis, color=color,
    )
    _roc_budget_and_line(parts, line_pts, pl=pl, pr=pr, pt=pt, plot_h=plot_h, w=w, mx=mx, budget_month=budget_month)
    budget_span = tpl.fill("charts/legend_budget_span.html", teal=TEAL) if budget_month else ""
    legend = tpl.fill("charts/legend_receipt.html", color=color, orange=ORANGE, purple=PURPLE, budget_span=budget_span)
    return (
        f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">'
        f"{''.join(parts)}{''.join(hits)}</svg>{legend}"
    )


# 任务书39·E：费用月度堆叠柱配色（走 CSS 变量，亮暗主题自动跟随）
_STACK_PALETTE = (
    "var(--blue)",
    "var(--purple)",
    "var(--teal)",
    "var(--orange)",
    "var(--cost)",
    "var(--pos)",
    "var(--accent)",
    "var(--neg)",
)


def _esc_stack_months(months: list[dict] | None) -> list[dict]:
    months = list(months or [])
    if not months:
        months = [{"m": i + 1, "total": 0, "total_disp": "0.0", "segs": []} for i in range(12)]
    while len(months) < 12:
        months.append({"m": len(months) + 1, "total": 0, "total_disp": "0.0", "segs": []})
    return months


def _esc_stack_layers(months: list[dict], categories: list[str]) -> tuple[list, list]:
    amt_by_cat: list[dict[str, float]] = []
    for i in range(12):
        m = months[i]
        by = {s.get("cat") or "": float(s.get("amount") or 0) for s in (m.get("segs") or [])}
        amt_by_cat.append(by)
    bottoms: list[dict[str, float]] = []
    tops: list[dict[str, float]] = []
    for i in range(12):
        bot, top = {}, {}
        acc = 0.0
        for c in categories:
            a = float(amt_by_cat[i].get(c) or 0)
            bot[c] = acc
            acc += max(0.0, a)
            top[c] = acc
        bottoms.append(bot)
        tops.append(top)
    return bottoms, tops


def _esc_draw_areas(parts, categories, cat_colors, bottoms, tops, _x, _y) -> None:
    for c in categories:
        color = cat_colors.get(c, MUT)
        top_pts = [f"{_x(i):.1f},{_y(tops[i].get(c, 0)):.1f}" for i in range(12)]
        bot_pts = [f"{_x(i):.1f},{_y(bottoms[i].get(c, 0)):.1f}" for i in range(11, -1, -1)]
        d = "M " + " L ".join(top_pts) + " L " + " L ".join(bot_pts) + " Z"
        parts.append(
            f'<path class="exp-area" data-cat="{esc(c)}" d="{d}" fill="{color}" fill-opacity="0.72" '
            f'stroke="{color}" stroke-width="1" stroke-opacity="0.95"/>'
        )


def _esc_draw_month_hits(parts, hits, months, *, pl, pt, plot_h, h, pb, gw, _x, _y) -> None:
    for i in range(12):
        m = months[i]
        cx = _x(i)
        total = float(m.get("total") or 0)
        tot_disp = m.get("total_disp") or fmt_wan(total)
        if total > 0:
            ty = _y(total) - 5
            parts.append(
                f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="9.5" font-weight="700" '
                f'fill="{INK}">{esc(tot_disp)}</text>'
            )
        parts.append(
            f'<text x="{cx:.1f}" y="{h - pb + 15:.1f}" text-anchor="middle" font-size="11" fill="{MUT}">'
            f"{i + 1}月</text>"
        )
        seg_tips = []
        for seg in m.get("segs") or []:
            cat = seg.get("cat") or ""
            if float(seg.get("amount") or 0) <= 0:
                continue
            seg_tips.append(
                f"{esc(cat)} {esc(seg.get('amount_disp') or fmt_wan(seg.get('amount') or 0))}万"
                f"（{esc(seg.get('pct_disp') or '—')}）"
            )
        tip_detail = "<br>".join(seg_tips)
        tip = f"{i + 1}月合计 {esc(tot_disp)}万" + (f"<br>{tip_detail}" if tip_detail else "")
        hits.append(
            f'<rect class="hit" data-tip="{tip}" x="{pl + gw * i:.1f}" y="{pt:.1f}" '
            f'width="{gw:.1f}" height="{plot_h:.1f}" fill="transparent"/>'
        )


def expense_stack_chart(
    months: list[dict],
    categories: list[str],
    *,
    note: str = "",
) -> str:
    """费用月度趋势·按报表大类堆叠面积图（任务书46·阶段0：柱→面积）。
    months=[{m:1..12, total:分, total_disp:万串, segs:[{cat, amount, amount_disp, pct_disp}…]}]
    高度/显示串均由调用方预算好（铁律2）；本函数只拼 SVG。
    X=1~12 月、分层=报表大类、配色沿用图例、顶部总额标签+悬浮月份合计 tooltip 保留。"""
    w, h = 640, 317  # 任务书46·0：整体放大一档，图表高度 +10%（原 288）
    pl, pr, pt, pb = 54, 36, 34, 40
    plot_w, plot_h = w - pl - pr, h - pt - pb
    n = 12
    months = _esc_stack_months(months)
    mx = max((float(m.get("total") or 0) for m in months[:12]), default=0) or 1
    area_h = plot_h * 0.88
    gw = plot_w / n
    cat_colors = {c: _STACK_PALETTE[i % len(_STACK_PALETTE)] for i, c in enumerate(categories)}
    bottoms, tops = _esc_stack_layers(months, categories)

    def _y(val: float) -> float:
        return pt + plot_h - (val / mx * area_h)

    def _x(i: int) -> float:
        return pl + gw * i + gw / 2

    parts: list[str] = []
    hits: list[str] = []
    for frac in (0, 0.5, 1.0):
        y = pt + plot_h * (1 - frac)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{w - pr}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(
            f'<text x="{pl - 8}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="{MUT2}">'
            f"{'0' if frac == 0 else fmt_wan(mx * frac) + '万'}</text>"
        )
    _esc_draw_areas(parts, categories, cat_colors, bottoms, tops, _x, _y)
    _esc_draw_month_hits(parts, hits, months, pl=pl, pt=pt, plot_h=plot_h, h=h, pb=pb, gw=gw, _x=_x, _y=_y)
    legend_items = "".join(
        tpl.fill("charts/legend_expense_item.html", color=cat_colors[c], name=esc(c)) for c in categories
    )
    legend = tpl.fill("charts/legend_expense_stack.html", items=legend_items)
    note_html = tpl.fill("charts/exp_trend_note.html", note=esc(note)) if note else ""
    return (
        f'<svg viewBox="0 0 {w} {h}" style="max-width:100%;display:block">'
        f"{''.join(parts)}{''.join(hits)}</svg>{legend}{note_html}"
    )
