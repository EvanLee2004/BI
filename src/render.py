#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装经营驾驶舱 HTML（科技风暗色默认 + 浅色切换）。四段骨架：基本情况/经营利润/收入与毛利结构/资金与回款（回款情况+下单回款排名）。
全局时间选择器（月/季/年，默认年）驱动 基本情况+利润表+费用构成 一起切；趋势图/回款图是整年时间线。
所有金额 Python 算好，JS 只做主题切换/周期切换/展开折叠/提示定位，不做任何金额运算。"""
from __future__ import annotations

import charts
import theme
import version as product_version

GROUP_COLORS = {"营销费用": "var(--blue)", "管理费用": "var(--purple)", "固定运营费用": "var(--teal)",
                "研发费用": "var(--orange)", "财务费用": "var(--cost)"}
LED_OF = {"营销费用": "市场费用", "管理费用": "管理费用", "固定运营费用": "固定运营费用",
          "研发费用": "技术服务费", "财务费用": "财务费用"}

# 基本情况 KPI 卡（陆总 2026-07-13：5 张）
# (标签, 取值键, 来源, 涨为好, 附率键, 趋势线色, 目标键)
# 交付金额=智云含税交付额(不÷1.06)；脚注另标确认口径交付收入
KPI_CARDS = [
    ("下单", "orders", "智云·下单预估额", True, None, "var(--purple)", "order"),
    ("交付金额", "revenue_gross", "智云直接抓·含税 · 确认口径÷1.06见脚注", True, None, "var(--blue)", None),
    ("管理毛利", "gross_profit", "完整口径·交付收入−生产成本", True, "gross_margin_pct", "var(--orange)", "margin"),
    ("税前利润", "pretax_profit", "毛利−各项费用−附加税±其他", True, "pretax_margin_pct", "var(--pos)", None),
    ("回款", "receipts", "智云·回款(到账)", True, None, "var(--teal)", "receipt"),
]
# 回款/下单比解释小字：陆总 0714 拍板不再展示（"这行不用写，大家都理解"）；常量保留给旧测试/兼容
RECEIPT_NOTE = "当月回款多对应往月下单，反映资金回笼节奏，非当月回收率"

# 右侧抽屉（点利润表大类看构成）——单例，放 body 末尾
DRAWER_HTML = ('<div id="drawer" class="drawer" aria-hidden="true">'
               '<div class="drawer-mask" data-close></div>'
               '<aside class="drawer-panel" role="dialog" aria-modal="true">'
               '<div class="drawer-h"><span id="drawerTitle"></span>'
               '<button class="drawer-x" data-close aria-label="关闭">×</button></div>'
               '<div class="drawer-body" id="drawerBody"></div></aside></div>')

# 背景粒子流（科技风环境动效）——固定位置表，纯装饰、不进任何计算/回归
# (left%, 直径px, 时长s, 延迟s, 颜色变量)
_PARTICLES = [(4, 2, 20, -3, "--blue"), (9, 3, 15, -9, "--purple"), (15, 2, 22, -14, "--teal"),
              (20, 2, 17, -5, "--blue"), (26, 3, 24, -18, "--purple"), (31, 2, 14, -2, "--teal"),
              (37, 2, 21, -11, "--blue"), (43, 3, 27, -7, "--purple"), (48, 2, 16, -15, "--teal"),
              (54, 2, 25, -20, "--teal"), (59, 2, 19, -12, "--blue"), (65, 3, 13, -6, "--purple"),
              (70, 3, 26, -16, "--teal"), (76, 2, 18, -9, "--blue"), (81, 2, 23, -3, "--purple"),
              (87, 2, 15, -13, "--teal"), (92, 3, 28, -8, "--blue"), (97, 2, 20, -17, "--purple"),
              (12, 2, 12, -1, "--blue"), (34, 2, 30, -22, "--teal"), (46, 2, 11, -4, "--purple"),
              (57, 3, 29, -10, "--teal"), (68, 2, 13, -19, "--blue"), (79, 2, 24, -6, "--purple"),
              (90, 2, 16, -14, "--teal"), (24, 3, 21, -2, "--blue"), (50, 2, 27, -11, "--purple"),
              (72, 2, 14, -7, "--teal")]
PARTICLES_HTML = ('<div class="particles" aria-hidden="true">' + "".join(
    f'<i style="left:{l}%;width:{s}px;height:{s}px;background:var({c});box-shadow:0 0 6px var({c});'
    f'animation-duration:{d}s;animation-delay:{dl}s"></i>' for l, s, d, dl, c in _PARTICLES) + '</div>')


def _kpi_val(p, key):
    """KPI 取值：一律取 period 已算好的字段（不做派生聚合，前端零运算）。"""
    return p[key]


def _prev_period_key(pkey, year):
    """环比的上一同粒度周期 key：年→无（缺上年数据）；季→上季(Q1无)；月→上月(1月无)。"""
    yk = f"{year}年"
    if pkey == yk:
        return None
    if "Q" in pkey:
        q = int(pkey.split("Q")[1])
        return f"{yk}Q{q - 1}" if q > 1 else None
    mpart = pkey.split("年")[1].replace("月", "")
    if "-" in mpart:   # 自定义月区间：无"同粒度上期"概念
        return None
    m = int(mpart)
    return f"{yk}{m - 1}月" if m > 1 else None


def _wan(v):
    return charts.fmt_wan(v) + "万"


def _title_version_html() -> str:
    """顶栏产品名旁版本徽章（用户端 / 管理端「看」/ BU 页同源；唯一源=根目录 VERSION）。
    与管理端顶栏一致：主号去 -beta 后缀，试运行/公测附阶段。"""
    v = product_version.read_version()
    base = v.partition("-")[0]
    stage = product_version.product_stage(v)
    text = f"v{base}" if (not stage or stage == "正式版") else f"v{base} · {stage}"
    return f'<span class="tb-ver" title="产品版本">{_esc(text)}</span>'


def _amt(v, colored=False, muted=False):
    s = ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"
    cls = "pl-amt"
    if colored:
        cls += " pos" if v >= 0 else " neg"
    return f'<span class="{cls}">{s}</span>'


def _target_bar(budget, tkey, pkey, year, p):
    """KPI 下业务目标进度条。tkey=order/receipt/margin；无目标→空态小字。
    仅「1-6 月」区间用 H1 目标；Q1≠H1（勿把 Q1 当上半年）。年目标 done=全年累计。"""
    if not budget or not tkey:
        return ""
    # 仅明确的 1–6 月区间用 H1；Q1 仍用年目标
    use_h1 = ("1-6" in pkey) or pkey.endswith("1-6月") or ("1~6" in pkey)
    item = None
    label = "年目标"
    if use_h1 and budget.get(f"{tkey}_h1"):
        item = budget[f"{tkey}_h1"]
        label = "H1目标"
    if item is None:
        item = budget.get(tkey)
        label = "年目标"
    if not item:
        return '<div class="kpi-tgt muted">未设目标</div>'
    tgt, done, pct = item.get("target"), item.get("done"), item.get("pct")
    if tkey == "margin":
        # 「当前」必须与达成率同一口径：H1 用 item.done，否则用本周期毛利率
        if use_h1 and item.get("done") is not None:
            cur = item["done"]
        else:
            cur = p.get("gross_margin_pct")
        cur_s = f"{cur:.1f}%" if cur is not None else "—"
        pct_s = f"{pct:.0f}%" if pct is not None else "—"
        w = min(max(pct or 0, 0), 100)
        cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
        return (f'<div class="kpi-tgt"><div class="kpi-tgt-h">{label} {tgt:.1f}% · 当前 <b>{cur_s}</b></div>'
                f'<span class="kpi-tgt-track"><i class="{cls}" style="width:{w:.1f}%"></i></span>'
                f'<div class="kpi-tgt-n">达成 {pct_s}</div></div>')
    # 金额类：完成 / 目标 · 进度（年目标 done 为全年累计，标签已写「年目标」）
    if done is None:
        done = _kpi_val(p, {"order": "orders", "receipt": "receipts"}.get(tkey, "orders"))
        pct = (done / tgt * 100.0) if tgt else None
    pct_s = f"{pct:.1f}%" if pct is not None else "—"
    w = min(max(pct or 0, 0), 100)
    cls = "ok" if (pct or 0) >= 100 else ("warn" if (pct or 0) >= 80 else "low")
    return (f'<div class="kpi-tgt"><div class="kpi-tgt-h">{label} {charts.fmt_wan(tgt)}万 · 已完成 <b>{charts.fmt_wan(done)}万</b></div>'
            f'<span class="kpi-tgt-track"><i class="{cls}" style="width:{w:.1f}%"></i></span>'
            f'<div class="kpi-tgt-n">进度 {pct_s}</div></div>')


# ---------- 板块① 基本情况（单周期，5 KPI：值+环比+目标进度+峰值/对照）----------
def _kpi_peak_row(month_keys, P, key, year):
    """全年逐月峰值一行（替代迷你折线）：领导扫哪个月最高。金额后端算好。"""
    if not month_keys:
        return ""
    best_v, best_mk = None, None
    for mk in month_keys:
        v = float(_kpi_val(P[mk], key) or 0.0)
        if best_v is None or v > best_v:
            best_v, best_mk = v, mk
    if best_v is None or (best_v == 0.0 and all(
            float(_kpi_val(P[mk], key) or 0.0) == 0.0 for mk in month_keys)):
        return ""
    lab = best_mk.replace(f"{year}年", "") if isinstance(best_mk, str) and best_mk.startswith(f"{year}年") else str(best_mk)
    return (f'<div class="kpi-foot-row"><span class="kpi-foot-l">全年峰值</span>'
            f'<span class="kpi-foot-v"><b>{_esc(lab)}</b> {charts.fmt_wan(best_v)}万</span></div>')


def _bu_orders_block(bu_list):
    """下单卡内各 BU 进度（陆总0714·C1）：期内下单额 + 全年累计/BU 年目标。
    布局：上行 名+金额+率，下行 全宽进度条（更清晰）。
    有目标 → 填充=年累计/年目标；未设目标 → 仍画轨道，填充=期内额相对最大 BU（比大小，非达成率）。
    只在全公司整体页出现（BU 页不传此参数·铁律12）。金额/率全部后端算好。"""
    if not bu_list:
        return ""
    max_amt = max((float(d.get("amount") or 0.0) for d in bu_list), default=0.0) or 1.0
    rows = ""
    for d in bu_list:
        amt_v = float(d.get("amount") or 0.0)
        amt = charts.fmt_wan(amt_v)
        pct = d.get("pct")
        if pct is not None:
            w = min(max(float(pct), 0.0), 100.0)
            cls = "ok" if pct >= 100 else ("warn" if pct >= 80 else "low")
            badge = f'<span class="kpi-bu-p">{pct:.0f}%</span>'
            track = f'<span class="kpi-bu-track"><i class="{cls}" style="width:{w:.1f}%"></i></span>'
            tip = f'年目标 {charts.fmt_wan(d["target"])}万 · 全年累计 {charts.fmt_wan(d.get("year_amount") or 0)}万'
        else:
            # 未设目标：轨道仍在；填充只反映相对大小（最大 BU=100%），文案标明未设
            w = min(max(amt_v / max_amt * 100.0, 0.0), 100.0) if amt_v else 0.0
            badge = '<span class="kpi-bu-p muted">未设目标</span>'
            track = f'<span class="kpi-bu-track soft"><i class="soft" style="width:{w:.1f}%"></i></span>'
            tip = "该 BU 未填下单年目标（管理端·人工填写·业绩目标·选 BU 范围）；条长仅为部门间相对大小"
        rows += (f'<div class="kpi-bu" data-tip="{_esc(_esc(tip))}">'
                 f'<div class="kpi-bu-h"><span class="kpi-bu-n">{_esc(d["name"])}</span>'
                 f'<span class="kpi-bu-a">{amt}万</span>{badge}</div>{track}</div>')
    return f'<div class="kpi-bus">{rows}</div>'


def _kpi_period_label(pkey, year):
    """基本情况卡头旁的时段角标：全年写「2026年」；季/月/区间去掉年份前缀写「Q1」「3月」「1-6月」。
    与顶部「看哪段」同源（.pv 按周期预渲染，前端只切显示、零运算）。"""
    yk = f"{year}年"
    if pkey == yk:
        return yk
    if isinstance(pkey, str) and pkey.startswith(yk):
        rest = pkey[len(yk):]
        return rest or yk
    return str(pkey or yk)


def render_basic(pkey, P, year, month_keys, budget=None, bu_orders=None):
    """基本情况 KPI。month_keys=全年月周期列表（算峰值用）；不再画迷你折线。"""
    p = P[pkey]
    prev = _prev_period_key(pkey, year)
    period_tag = _esc(_kpi_period_label(pkey, year))
    cards = ""
    for label, key, src, up_good, pctkey, _color, tkey in KPI_CARDS:
        val = float(_kpi_val(p, key) or 0.0)
        vhtml = f'{charts.fmt_wan(val)}<span class="u">万</span>'
        # 环比上期（同粒度）
        if prev is not None and _kpi_val(P.get(prev) or {}, key):
            pv = float(_kpi_val(P[prev], key) or 0.0)
            if pv:
                d = (val - pv) / abs(pv) * 100
                good = (d >= 0) == up_good
                arrow = "▲" if d >= 0 else "▼"
                delta = f'<div class="kpi-delta {"up" if good else "down"}">{arrow} {abs(d):.1f}% <span>环比上期</span></div>'
            else:
                delta = '<div class="kpi-delta muted">— 无上期对比</div>'
        else:
            delta = '<div class="kpi-delta muted">— 无上期对比</div>'
        sub = ""
        if key == "revenue_gross":
            sub = f'<div class="kpi-sub">交付收入(÷1.06) <b>{charts.fmt_wan(p["revenue_net"])}万</b></div>'
            o = float(p.get("orders") or 0.0)
            if o > 0:
                sub += f'<div class="kpi-sub">交付占下单 <b>{val / o * 100:.0f}%</b></div>'
        elif pctkey == "gross_margin_pct":
            sub = f'<div class="kpi-sub">毛利率 <b>{p[pctkey]:.1f}%</b></div>'
        elif pctkey == "pretax_margin_pct":
            sub = f'<div class="kpi-sub">利润率 <b>{p[pctkey]:.1f}%</b></div>'
        if key == "receipts":
            r = p["receipt_order_ratio_pct"]
            rtxt = f'{r:.1f}%' if r is not None else '—'
            sub = f'<div class="kpi-sub">总回款/下单比 <b>{rtxt}</b></div>'
        tgt = _target_bar(budget, tkey, pkey, year, p)
        bus_html = _bu_orders_block(bu_orders) if key == "orders" else ""
        # 卡底有用信息：全年峰值；回款卡再加本期「已交付未回款」
        foot_rows = _kpi_peak_row(month_keys, P, key, year)
        if key == "receipts":
            ar = float(p.get("revenue_gross") or 0.0) - val  # 交付金额(含税)−回款，近似应收
            ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar))
            foot_rows += (f'<div class="kpi-foot-row"><span class="kpi-foot-l">已交付未回款</span>'
                          f'<span class="kpi-foot-v"><b>{ar_s}</b>万</span></div>')
        foot = f'<div class="kpi-foot">{foot_rows}</div>' if foot_rows else ""
        cards += (f'<div class="kpi"><div class="kpi-l">{label}'
                  f'<span class="kpi-period" title="当前查看时段">{period_tag}</span></div>'
                  f'<div class="kpi-cum">{vhtml}</div>{sub}{delta}{tgt}{bus_html}'
                  f'{foot}<div class="kpi-src">{src}</div></div>')
    return f'<div class="kpi-grid kpi-5">{cards}</div>'


# ---------- 板块②-1 交付金额 · 毛利趋势（整年，静态）----------
def render_trend(trend, hl):
    # 看端卡头只留「按月」；柱顶/线上说明见图例，不堆运营备注
    return (f'<div class="card"><div class="card-h">交付收入 · 生产毛利趋势 '
            f'<span class="tag">按月</span></div>'
            f'{charts.combo_bar_line_chart(trend, hl)}</div>')


# ---------- 费用构成环形图（随周期切）----------
def render_donut(p):
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    groups = ["营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"]
    segs = [(g, e[g], GROUP_COLORS[g]) for g in groups if e[g] > 0]
    # 悬浮明细：每类拆成 手填人力 / 台账 两块（陆总口径）
    detail = {
        "营销费用": [("营销人力成本(手填)", man["营销人力成本"]), ("市场费用(台账)", led["市场费用"])],
        "管理费用": [("管理人力成本(手填)", man["管理人力成本"]), ("管理费用(台账)", led["管理费用"])],
        "固定运营费用": [("固定运营费用(台账)", led["固定运营费用"])],
        "研发费用": [("研发人力成本(手填)", man["研发人力成本"]), ("技术服务费(台账)", led["技术服务费"])],
        "财务费用": [("财务费用(台账)", led["财务费用"]), ("财务费用补充(手填)", man["财务费用补充"])],
    }
    legend = "".join(f'<span><i style="background:{GROUP_COLORS[g]}"></i>{g} {charts.fmt_wan(e[g])}万</span>' for g in groups)
    return (f'{charts.donut(segs, "期间费用", charts.fmt_wan(e["total"]) + "万", detail=detail)}'
            f'<div class="legend">{legend}</div>')


# 横条「未填/未标」沉底名：部门/BU 视角=未分类；类别视角=未标注明细类型（config 同文案）
_HBAR_SINK = frozenset({"未分类", "未标注明细类型"})


def _hbar_rows(rows, prefix):
    """横向条形列表（台账白名单口径分组）+ 每组的抽屉明细块。rows=[(组名,合计,[(细项,金额),...]),...]。
    宽度按最大组归一（服务端算好，前端零运算）；未分类/未标注明细类型灰色沉底。"""
    if rows is None:
        return '<div class="ev-empty">收单台账缺分组列（老台账），换新表头后自动出现</div>'
    if not rows:
        return '<div class="ev-empty">本期无台账费用</div>'
    ordered = [r for r in rows if r[0] not in _HBAR_SINK] + [r for r in rows if r[0] in _HBAR_SINK]
    mx = max(v for _, v, _ in rows) or 1
    out, details = [], []
    for name, val, fine in ordered:
        key = f"{prefix}:{name}"
        w = max(2.0, val / mx * 100)
        cls = " unfilled" if name in _HBAR_SINK else ""
        out.append(f'<div class="ev-row pl-open{cls}" data-cat="{_esc(key)}" role="button" tabindex="0">'
                   f'<span class="ev-name">{_esc(name)}</span>'
                   f'<span class="ev-track"><i style="width:{w:.1f}%"></i></span>'
                   f'<span class="ev-amt">{charts.fmt_wan(val)}万</span>'
                   f'<span class="pl-more ev-more">构成 ›</span></div>')
        inner = "".join(_drow(n, -a, "", "", sub=True) for n, a in fine[:12])
        rest = fine[12:]
        if rest:
            inner += _drow(f"其他{len(rest)}项", -sum(a for _, a in rest), "", "", sub=True)
        details.append(_detail_block(key, f"{name} · 费用构成（{charts.fmt_wan(val)}万）", inner))
    return f'<div class="ev-list">{"".join(out)}</div><div class="pl-details" hidden>{"".join(details)}</div>'


def _ledger_subtotal(rows):
    return charts.fmt_wan(sum(v for _, v, _ in rows)) + "万" if rows else "0万"


def render_expense_views(p, fine_rows, pc_rows):
    """期间费用构成卡：按大类（环形图）｜按类别（预算明细费用类型）｜按业务BU（利润中心）。
    三态台账白名单含税口径同一；卡头合计含手填人力，横条小计仅为台账部分。"""
    e = p["expense"]
    tabs = ('<span class="ev-tabs">'
            '<button class="ev-tab on" data-ev="cat">按大类</button>'
            '<button class="ev-tab" data-ev="fine">按类别</button>'
            '<button class="ev-tab" data-ev="pc">按业务BU（利润中心）</button></span>')
    # 看端：横条小计可扫读；长口径说明留给管理端数据/异常页，此处不堆字
    fine_note = f'台账小计 {_ledger_subtotal(fine_rows)}'
    pc_note = f'台账小计 {_ledger_subtotal(pc_rows)}'
    return (f'<div class="card"><div class="card-h">期间费用构成 <span class="tag">合计 {charts.fmt_wan(e["total"])}万</span>{tabs}</div>'
            f'<div class="ev-body">'
            f'<div class="ev-pane" data-ev="cat">{render_donut(p)}</div>'
            f'<div class="ev-pane" data-ev="fine" style="display:none">{_hbar_rows(fine_rows, "fine")}'
            f'<div class="chart-note">{fine_note}</div></div>'
            f'<div class="ev-pane" data-ev="pc" style="display:none">{_hbar_rows(pc_rows, "pc")}'
            f'<div class="chart-note">{pc_note}</div></div>'
            f'</div></div>')


def _fine_to_rows(fine_k):
    """把 {大类:[(细类,金额)…]} 摊平成「按类别」横条行 [(细类,合计,[(大类,金额)…])…]（迭代22·D2）。
    同名细类跨大类合并；抽屉里按大类拆开看。金额全后端 round，前端零运算。"""
    if not fine_k:
        return []
    agg: dict[str, float] = {}
    src: dict[str, list] = {}
    for cat, pairs in fine_k.items():
        for name, amt in pairs or []:
            agg[name] = agg.get(name, 0.0) + float(amt)
            src.setdefault(name, []).append((cat, float(amt)))
    rows = [(n, round(v, 2), sorted(src[n], key=lambda x: -x[1])) for n, v in agg.items()]
    rows.sort(key=lambda r: -r[1])
    return rows


def render_bu_expense_views(p, fine_k):
    """BU 页期间费用构成卡：按大类（环形）｜按类别（横条）两态。
    与整体页「按类别」同口径（预算明细费用类型）；不出「按部门」。"""
    e = p.get("expense") or {}
    rows = _fine_to_rows(fine_k)
    tabs = ('<span class="ev-tabs">'
            '<button class="ev-tab on" data-ev="cat">按大类</button>'
            '<button class="ev-tab" data-ev="fine">按类别</button></span>')
    return (f'<div class="card"><div class="card-h">期间费用构成 <span class="tag">合计 {charts.fmt_wan(e.get("total") or 0)}万</span>{tabs}</div>'
            f'<div class="ev-body">'
            f'<div class="ev-pane" data-ev="cat">{render_donut(p)}</div>'
            f'<div class="ev-pane" data-ev="fine" style="display:none">{_hbar_rows(rows, "fine")}'
            f'<div class="chart-note">台账小计 {_ledger_subtotal(rows)}</div></div>'
            f'</div></div>')


def render_dept_budget(dept_budget):
    """部门费用预算执行卡。迭代19 陆总拍板：界面下线（半吊子汇总无意义）；函数保留给旧测试/兼容，恒返回空。"""
    return ""


# ---------- 板块②-2 管理利润表（点大类→侧边抽屉看构成，主表定高不再顶下方图表）----------
def _row(name, impact, kind, src="", total=False, grand=False):
    cls = "pl-row" + (" total grand" if grand else " total" if total else "")
    dot = f'<span class="dot {kind}"></span>' if kind else '<span class="dot none"></span>'
    src_html = f'<span class="src">{src}</span>' if src else ""
    return f'<div class="{cls}">{dot}<div class="pl-name">{name}{src_html}</div>{_amt(impact, colored=(total or grand))}</div>'


def _pct_row(name, pct, src=""):
    """比率行（如销售利润率）：金额列显示百分数，不参与任何求和。pct=None → 灰显 —。"""
    src_html = f'<span class="src">{src}</span>' if src else ""
    txt = f"{pct:.1f}%" if pct is not None else "—"
    return (f'<div class="pl-row"><span class="dot none"></span>'
            f'<div class="pl-name">{name}{src_html}</div>'
            f'<span class="pl-amt">{txt}</span></div>')


def _open_row(cat, name, impact):
    """可点大类行：点击弹出右侧抽屉看构成（不再就地展开、不顶下方图表）。"""
    return (f'<div class="pl-row pl-open" data-cat="{cat}" role="button" tabindex="0">'
            f'<span class="dot none"></span>'
            f'<div class="pl-name">{name}<span class="pl-more">查看构成 ›</span></div>{_amt(impact)}</div>')


def _drow(name, impact, kind, src="", sub=False):
    """抽屉内明细行（始终展开、无需切换）。
    金额只显示绝对值：行名已带「加/减」语义，用户只看数额；主表利润影响仍走 _row/_open_row 带符号。"""
    cls = "pl-drow" + (" sub" if sub else "")
    dot = f'<span class="dot {kind}"></span>' if kind else '<span class="dot none"></span>'
    src_html = f'<span class="src">{src}</span>' if src else ""
    return (f'<div class="{cls}">{dot}<div class="pl-name">{_esc(name)}{src_html}</div>'
            f'{_amt(abs(float(impact or 0)))}</div>')


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
    return f'<div class="pl-detail" data-cat="{_esc(cat)}" data-title="{_esc(title)}">{inner}</div>'


def render_pl_table(p, fine, unclassified_amt=None):
    """管理利润表（看端·领导视角）：行旁只留计算公式；运营备注/填数提示不展示（管理端数据页看）。"""
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    # 主表：公式留 / 运营备注去
    rows = [_row("交付收入（不含税）", p["revenue_net"], "system", "交付金额÷1.06")]
    rows.append(_open_row("cost", "交付成本（生产成本）", -p["production_cost"]))
    rows.append(_row("管理毛利（完整）", p["gross_profit"], "", total=True))
    rows.append(_open_row("sales", "营销费用", -e["营销费用"]))
    rows.append(_open_row("admin", "管理费用", -e["管理费用"]))
    rows.append(_open_row("fixed", "固定运营费用", -e["固定运营费用"]))
    rows.append(_open_row("rd", "研发费用", -e["研发费用"]))
    rows.append(_open_row("fin", "财务费用", -e["财务费用"]))
    rows.append(_row("附加税费", -p["surtax"], "system", "净收入×6%×12%"))
    rows.append(_row("其他损益", p["other_pl"], "manual", ""))
    if unclassified_amt and unclassified_amt > 0:
        rows.append(_row("未计入费用（台账未填大类）", -unclassified_amt, "ledger", ""))
    rows.append(_row("税前利润", p["pretax_profit"], "",
                     "管理毛利−期间费用−附加税±其他", grand=True))
    # 陆总0714：销售利润率（=税前利润÷交付收入）
    rows.append(_pct_row("销售利润率", p.get("pretax_margin_pct"), "税前利润÷交付收入"))

    # 抽屉：只列名目+金额，不堆「手填·默认0」类运营旁注
    # 抽屉行名不带「加/减」：用户只看名目与金额
    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system")
                  + _drow("系统内部译员", p["inhouse_cost"], "system")
                  + _drow("直接成本增值税", man.get("直接成本增值税", 0.0), "manual")
                  + "".join(_drow(n, -man[n], "manual") for n in prod_manual))
    details = "".join([
        _detail_block("cost", "交付成本（生产成本）构成", cost_inner),
        _detail_block("sales", "营销费用构成",
                      _drow("营销人力成本", -man["营销人力成本"], "manual")
                      + _d_ledger("市场费用", led["市场费用"], "", fine.get("市场费用"))),
        _detail_block("admin", "管理费用构成",
                      _drow("管理人力成本", -man["管理人力成本"], "manual")
                      + _d_ledger("管理费用", led["管理费用"], "", fine.get("管理费用"))),
        _detail_block("fixed", "固定运营费用构成",
                      _d_ledger("固定运营费用明细", led["固定运营费用"], "", fine.get("固定运营费用"))),
        _detail_block("rd", "研发费用构成",
                      _drow("研发人力成本", -man["研发人力成本"], "manual")
                      + _d_ledger("技术服务费", led["技术服务费"], "", fine.get("技术服务费"))),
        _detail_block("fin", "财务费用构成",
                      _d_ledger("财务费用（台账）", led["财务费用"], "", fine.get("财务费用"))
                      + _drow("财务费用补充", -man["财务费用补充"], "manual")),
    ])
    kinds = ('<div class="kinds">'
             '<span><i style="background:var(--kind-system)"></i>智云</span>'
             '<span><i style="background:var(--kind-ledger)"></i>台账</span>'
             '<span><i style="background:var(--kind-manual)"></i>手填</span></div>')
    return (f'<div class="pl">{"".join(rows)}</div>{kinds}'
            f'<div class="pl-details" hidden>{details}</div>')


# ---------- 板块②-3 回款按月（整年，静态）+ 每月回款/下单比线 ----------
def _budget_tag(budget):
    """预算完成标签（卡头）：没填预算 → 空串（页面与无预算时代一分不差）。"""
    if not budget:
        return ""
    parts = []
    for key, name in (("receipt", "回款"), ("order", "下单")):
        b = budget.get(key)
        if b:
            p = b.get("pct")
            if p is None:
                pct = "—"
            elif p > 999:
                pct = f"{p:.0f}%"
            else:
                pct = f"{p:.1f}%"
            parts.append(f'{name}年预算 {charts.fmt_wan(b["target"])}万 · 已完成 <b>{pct}</b>')
    return f'<span class="tag">{"　".join(parts)}</span>' if parts else ""


def _receipt_insight_panel(receipt_order_monthly, budget=None, delivered_gross=None):
    """回款右侧驾驶舱：下单未回款大数字 + 已交付未回款（可选）+ 回款占下单 + 可选年预算条。
    delivered_gross=全年交付金额（含税·revenue_gross）；None → 不渲染「已交付未回款」行。"""
    if not receipt_order_monthly:
        return '<div class="rc-side-empty">暂无按月数据</div>'
    tot_r = tot_o = 0.0
    best = worst = None  # (label, rec)
    for label, rec, order, _ratio in receipt_order_monthly:
        rec = rec or 0.0
        order = order or 0.0
        tot_r += rec
        tot_o += order
        if best is None or rec > best[1]:
            best = (label, rec)
        if worst is None or rec < worst[1]:
            worst = (label, rec)
    gap = tot_o - tot_r  # 下单 − 回款：>0 表示尚待回款（含未交付）
    ytd_pct = (tot_r / tot_o * 100.0) if tot_o else None
    ytd_txt = f"{ytd_pct:.1f}%" if ytd_pct is not None else "—"
    bar_w = max(0.0, min(float(ytd_pct or 0), 100.0))
    gap_mod = "warn" if gap > 0 else ("good" if gap < 0 else "flat")
    gap_hint = "尚待回款" if gap > 0 else ("回款超下单" if gap < 0 else "持平")
    gap_num = charts.fmt_wan(abs(gap))

    # 结构：顶行标签+徽章，中行超大数字（避免被挤没），底行不叠进度条
    hero = (
        f'<div class="rc-hero rc-hero-{gap_mod}">'
        f'<div class="rc-hero-top"><span class="rc-hero-l">下单未回款（下单 − 回款）</span>'
        f'<span class="rc-hero-tag">{gap_hint}</span></div>'
        f'<div class="rc-hero-n" title="累计下单 − 累计回款 · 含未交付订单，非应收">'
        f'<span class="rc-hero-num">{gap_num}</span><span class="rc-hero-u">万</span></div>'
        f'</div>'
    )
    # 已交付未回款 = 交付金额(含税) − 累计回款；回款超交付时如实显示负数（全角−）
    recv = ""
    if delivered_gross is not None:
        ar = float(delivered_gross) - tot_r
        ar_s = ("−" if ar < 0 else "") + charts.fmt_wan(abs(ar)) + "万"
        recv = (
            f'<div class="rc-rate rc-recv">'
            f'<div class="rc-rate-h"><span>已交付未回款</span><b>{ar_s}</b></div>'
            f'<div class="rc-recv-note">交付金额 − 回款 · 近似应收（交付口径，非开票口径）</div>'
            f'</div>'
        )
    rate = (
        f'<div class="rc-rate">'
        f'<div class="rc-rate-h"><span>回款占下单</span><b>{ytd_txt}</b></div>'
        f'<div class="rc-rate-bar"><i style="width:{bar_w:.1f}%"></i></div>'
        f'<div class="rc-rate-pair">'
        f'<span><em>累计下单</em>{charts.fmt_wan(tot_o)}万</span>'
        f'<span><em>累计回款</em>{charts.fmt_wan(tot_r)}万</span>'
        f'</div></div>'
    )
    # 峰值/谷值徽章：陆总 0714 拍板去掉（图上已一目了然）；best/worst 计算保留（成本极低，避免连带改动）
    pills = ""
    bud = ""
    rb = (budget or {}).get("receipt") if budget else None
    ob = (budget or {}).get("order") if budget else None
    for key, title, b in (("receipt", "回款年目标", rb), ("order", "下单年目标", ob)):
        if not (b and b.get("target")):
            continue
        pct = b.get("pct")
        # 目标填太小会出夸张完成率，展示上封顶文案避免 UI 崩
        if pct is None:
            pct_txt = "—"
        elif pct > 999:
            pct_txt = f"{pct:.0f}%·目标偏小"
        else:
            pct_txt = f"{pct:.1f}%"
        bw = max(0.0, min(float(pct or 0), 100.0))
        bud += (
            f'<div class="rc-bud">'
            f'<div class="rc-bud-h">{title} <b>{pct_txt}</b></div>'
            f'<div class="rc-bud-bar"><i style="width:{bw:.1f}%"></i></div>'
            f'<div class="rc-bud-t">目标 {charts.fmt_wan(b["target"])}万</div></div>'
        )
    return (
        f'<div class="rc-side-title">累计与回款</div>'
        f'<div class="rc-side-list rc-cockpit">{hero}{recv}{rate}{pills}{bud}</div>'
    )


def _months_for_period_key(key: str, year_key: str) -> list[int]:
    """单个周期 key → 月份列表（与顶部选择器 key 形如 2026年 / 2026年Q1 / 2026年3月 / 2026年1-3月 对齐）。"""
    if not key or key == year_key or (key.endswith("年") and "Q" not in key and "月" not in key):
        return list(range(1, 13))
    try:
        rest = key.split("年", 1)[1]
    except IndexError:
        return list(range(1, 13))
    if rest.startswith("Q"):
        q = int(rest[1:])
        sm = (q - 1) * 3 + 1
        return [sm, sm + 1, sm + 2]
    if rest.endswith("月"):
        body = rest[:-1]  # 去「月」
        if "-" in body:
            a, b = body.split("-", 1)
            return list(range(int(a), int(b) + 1))
        return [int(body)]
    return list(range(1, 13))


def _period_months_map(summary) -> dict[str, list[int]]:
    """周期 key → 应高亮的月份列表（Python 侧预生成塞 data-rm-map，前端只读应用、不解析 key）。
    年=1..12 全亮；季=该季 3 月；月=单月；区间=起止月闭区间。"""
    meta = summary.get("meta") or {}
    yk = meta.get("year_key") or ""
    groups = meta.get("tab_groups") or {}
    keys = [yk] + list(groups.get("季度") or []) + list(groups.get("月") or []) + list(groups.get("区间") or [])
    # 去重保序
    seen, ordered = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            ordered.append(k)
    return {k: _months_for_period_key(k, yk) for k in ordered}


def render_receipts(receipt_order_monthly, budget=None, *, period_months_map=None,
                    year_key=None, delivered_gross=None):
    """回款图（柱顶万 + 线上率%）+ 右侧驾驶舱（下单未回款 / 已交付未回款 / 回款占下单）。
    迭代21：卡根挂 data-rm-map（周期→月份）供前端只切高亮，全年视角数据不变。
    delivered_gross=全年交付金额（含税）；透传侧栏「已交付未回款」；None 则该行不渲染。"""
    import json
    rb = (budget or {}).get("receipt") if budget else None
    budget_month = (rb["target"] / 12.0) if rb and rb.get("target") else None
    side = _receipt_insight_panel(receipt_order_monthly, budget, delivered_gross=delivered_gross)
    rm_map = period_months_map or {}
    yk = year_key or ""
    map_json = json.dumps(rm_map, ensure_ascii=False, separators=(",", ":"))
    # 看端：卡头精简；卡底运营/交互说明去掉（指标名已自解释）
    return (f'<div class="card rc-card" id="rcCard" data-rm-year="{_esc(yk)}" '
            f'data-rm-map="{_esc(map_json)}"><div class="card-h">回款情况 '
            f'<span class="tag">按月</span>'
            f'{_budget_tag(budget)}</div>'
            f'<div class="rc-split">'
            f'<div class="rc-body">{charts.receipt_order_chart(receipt_order_monthly, budget_month=budget_month)}</div>'
            f'<div class="rc-side">{side}</div></div></div>')


# ---------- 板块③ 下单与回款排名（随周期切）----------
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _rank_amt(v):
    """排名金额显示：负数（红冲/退款净额）用全角负号，与利润表 _amt 一致。"""
    return ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"


def _rank_card(title, tag, rk, kind=""):
    """一张排名卡：名次 + 名称 + 横条(按最大值归一) + 金额 + 笔数/占比。金额均后端算好，前端零运算。
    kind=接口里 rankings 的键（orders_by_dept…），「其余」行点开全量明细时前端用它取数。"""
    items = (rk or {}).get("items") or []
    unfilled = (rk or {}).get("unfilled")
    if not items and not unfilled:
        body = '<div class="ev-empty">本期无数据</div>'
    else:
        mx = max((it["amount"] for it in items), default=0) or 1
        total = rk.get("total") or 0
        rows = []
        for i, it in enumerate(items, 1):
            w = max(it["amount"] / mx * 100, 0)
            share = f'{it["amount"] / total * 100:.0f}%' if total > 0 else "—"
            rows.append(f'<div class="ev-row rk-row"><span class="rk-no">{i}</span>'
                        f'<span class="ev-name" title="{_esc(it["name"])}">{_esc(it["name"])}</span>'
                        f'<span class="ev-track"><i style="width:{w:.1f}%"></i></span>'
                        f'<span class="ev-amt">{_rank_amt(it["amount"])}</span>'
                        f'<span class="rk-meta">{it["count"]}笔·{share}</span></div>')
        others = rk.get("others")
        if others:
            rows.append(f'<div class="ev-row rk-row rk-others rk-more" title="点开看 10 名以后的完整明细">'
                        f'<span class="rk-no">…</span>'
                        f'<span class="ev-name">其余 {others["names"]} 个 <span class="rk-open">点开看明细 ›</span></span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(others["amount"])}</span>'
                        f'<span class="rk-meta">{others["count"]}笔</span></div>')
        if unfilled:
            # 源头没填名字的那组：固定置底+灰显+⚠角标，不藏行（守恒：各组合计==总额）；去管理端「异常处理」归类
            rows.append(f'<div class="ev-row rk-row rk-unfilled"><span class="rk-no">⚠</span>'
                        f'<span class="ev-name" title="源头未填，去管理端「异常处理→下单未填部门」归类">（未填）</span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(unfilled["amount"])}</span>'
                        f'<span class="rk-meta">{unfilled["count"]}笔·待归类</span></div>')
        body = f'<div class="ev-list rk-list">{"".join(rows)}</div>'
    # tag 空则不渲染副标题（看端去掉「期内降序·智云」类备注）
    tag_html = f' <span class="tag">{_esc(tag)}</span>' if tag else ""
    return (f'<div class="card" data-kind="{_esc(kind)}"><div class="card-h">{title}{tag_html}</div>{body}</div>')


def render_rankings(p):
    rk = p.get("rankings") or {}
    s, e = p.get("range", ("", ""))
    # 陆总0714·C2：配了 BU 归属 → 首卡"按部门"换"按BU"（按销售→BU 映射聚合；未配 BU 时回退按部门）
    by_bu = rk.get("orders_by_bu")
    if by_bu is not None:
        first = _rank_card("下单 · 按BU", "", by_bu, "orders_by_bu")
    else:
        first = _rank_card("下单 · 按部门", "", rk.get("orders_by_dept"), "orders_by_dept")
    return (f'<div class="grid-3 rk-grid" data-start="{_esc(s)}" data-end="{_esc(e)}">'
            f'{first}'
            f'{_rank_card("下单 · 按销售", "", rk.get("orders_by_sales"), "orders_by_sales")}'
            f'{_rank_card("回款 · 按客户", "", rk.get("receipts_by_customer"), "receipts_by_customer")}'
            f'</div>')


# ---------- 板块③ 收入与毛利结构（确认口径，按客户/销售，随周期切）----------
def _margin_meta(mp):
    """系统成本率 meta：None（收入 0）→ 灰显「系统成本率 —」。
    陆总 0714 改叫「系统成本率」（=系统抓的项目成本÷交付收入）——生产环节大家习惯看成本率；
    只在利润表层才还原成"生产毛利"的利润概念。入参 mp=cost_pct。"""
    return f'系统成本率 {mp:.0f}%' if mp is not None else "系统成本率 —"


def _pname(name):
    """名称 span：悬浮 #tip 显示全名（长名截断也能看全）。data-tip 走 getAttribute+innerHTML
    两层解码→双层转义（铁律10）；title 保留为无 JS 时的原生兜底。"""
    n = _esc(name)
    return f'<span class="ev-name" title="{n}" data-tip="{_esc(n)}">{n}</span>'


def _profit_rank_card(title, tag, rk, dim="", show_meta=True):
    """收入/毛利排名卡：名次 + 名称 + 横条(按收入归一) + 收入 + 系统成本率。金额/率均后端算好，前端零运算（铁律2）。
    与板块④排名卡同款行样式；「其余 N 个」点开→ /api/profit_ranking 全量弹窗（dim=customer/sales）。
    show_meta=False → 隐藏成本率列（陆总 0714：按销售的率先不显示，防"人力算不算"连锁追问）。"""
    items = (rk or {}).get("items") or []
    unfilled = (rk or {}).get("unfilled")

    def _meta(it):
        return f'<span class="rk-meta">{_margin_meta(it.get("cost_pct"))}</span>' if show_meta else ""

    if not items and not unfilled:
        body = '<div class="ev-empty">本期无数据</div>'
    else:
        mx = max((abs(it["revenue"]) for it in items), default=0) or 1
        rows = []
        for i, it in enumerate(items, 1):
            w = max(it["revenue"] / mx * 100, 0)
            rows.append(f'<div class="ev-row rk-row"><span class="rk-no">{i}</span>'
                        f'{_pname(it["name"])}'
                        f'<span class="ev-track"><i style="width:{w:.1f}%"></i></span>'
                        f'<span class="ev-amt">{_rank_amt(it["revenue"])}</span>'
                        f'{_meta(it)}</div>')
        others = rk.get("others")
        if others:
            rows.append(f'<div class="ev-row rk-row rk-others pr-more" title="点开看全部{others["names"]}个明细">'
                        f'<span class="rk-no">…</span>'
                        f'<span class="ev-name">其余 {others["names"]} 个 <span class="rk-open">点开看明细 ›</span></span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(others["revenue"])}</span>'
                        f'{_meta(others)}</div>')
        if unfilled:
            rows.append(f'<div class="ev-row rk-row rk-unfilled"><span class="rk-no">⚠</span>'
                        f'<span class="ev-name" title="源头未填客户/销售，去管理端归类">（未填）</span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(unfilled["revenue"])}</span>'
                        f'{_meta(unfilled)}</div>')
        body = f'<div class="ev-list rk-list">{"".join(rows)}</div>'
    return (f'<div class="card" data-dim="{_esc(dim)}"><div class="card-h">{title} {tag}</div>{body}</div>')


def _conc_tag(rk):
    """卡头标签：确认口径（小灰）+ 前 k 大占收入%（集中度，`.conc` 独立高亮、数字放大）。
    无数据 → 只留口径。返回整段 HTML（含自己的 span，卡头不再外包 .tag）。"""
    c = (rk or {}).get("conc_pct")
    k = (rk or {}).get("conc_k", 5)
    if c is None:
        return '<span class="tag">确认口径</span>'
    return (f'<span class="tag">确认口径</span>'
            f'<span class="conc">前{k}大占收入 <b>{c:.0f}%</b></span>')


def render_profit_rankings(p):
    pr = p.get("profit_rankings") or {}
    s, e = p.get("range", ("", ""))
    cust, sale = pr.get("revenue_by_customer"), pr.get("revenue_by_sales")
    return (f'<div class="grid-2e pr-grid" data-start="{_esc(s)}" data-end="{_esc(e)}">'
            f'{_profit_rank_card("收入 · 按客户", _conc_tag(cust), cust, "customer")}'
            f'{_profit_rank_card("收入 · 按销售", _conc_tag(sale), sale, "sales", show_meta=False)}'
            f'</div>')


# 「其余 N 个」点开全量明细：/api/profit_ranking（确认口径全量），复用 #rkModal（已在 body、已有关闭处理）。
# 行 shape=名称+收入+毛利率（与卡片一致、无横条=与板块④弹窗一致）；金额/率均后端下发串（铁律2）。
PROFIT_JS = r"""
(function(){
 var modal=document.getElementById('rkModal'); if(!modal) return;
 var TITLE={customer:'收入 · 按客户',sales:'收入 · 按销售'};
 var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
   return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c];});};
 document.addEventListener('click',function(ev){
  var row=ev.target.closest?ev.target.closest('.pr-more'):null;
  if(!row)return;
  var card=row.closest('[data-dim]'),grid=row.closest('.pr-grid[data-start]');
  if(!card||!grid)return;
  var dim=card.getAttribute('data-dim'),s=grid.getAttribute('data-start'),e=grid.getAttribute('data-end');
  if(!dim||!s||!e)return;
  if(modal.parentElement!==document.body)document.body.appendChild(modal);
  document.getElementById('rkmTitle').textContent=(TITLE[dim]||'')+' · 完整排名';
  document.getElementById('rkmTag').textContent=(s===e)?s:(s+' ~ '+e);
  var list=document.getElementById('rkmList');
  list.innerHTML='<div class="ev-empty">加载中…</div>';modal.style.display='';
  fetch('/api/profit_ranking?dim='+encodeURIComponent(dim)+'&start='+s+'&end='+e+'&top=5000')
   .then(function(r){if(!r.ok)return r.json().then(function(d){throw new Error(d.detail||('HTTP '+r.status));});return r.json();})
   .then(function(d){
     var h='';(d.items||[]).forEach(function(it,i){
       var nm=esc(it.name);
       h+='<div class="ev-row rk-row"><span class="rk-no">'+(it.unfilled?'⚠':(i+1))+'</span>'+
          '<span class="ev-name" title="'+nm+'" data-tip="'+esc(nm)+'">'+nm+'</span>'+
          '<span class="ev-track"></span>'+
          '<span class="ev-amt">'+esc(it.revenue_disp)+'</span>'+
          '<span class="rk-meta">'+esc(it.margin_disp)+'</span></div>';});
     list.innerHTML='<div class="ev-list">'+(h||'<div class="ev-empty">本期无数据</div>')+'</div>';
   }).catch(function(err){list.innerHTML='<div class="ev-empty">加载失败：'+esc(err.message)+
     '（要在服务器版页面用；file:// 快照不支持）</div>';});
 });
})();
"""


# ---------- 全局周期选择器（下拉菜单）----------
def render_period_bar(summary):
    """周期选择器：按钮 + 日历面板（快捷段：全年/季度；月份网格：点起始月再点结束月=自选区间）。
    所有可选周期（含全部月区间组合）都已后端预渲染成 .pv 块，前端只做显示切换、不算任何数。"""
    meta = summary["meta"]
    tg = meta["tab_groups"]
    year, yk = meta["year"], meta["year_key"]
    cur_month = len(tg["月"])
    chips = f'<button class="pp-chip on" data-key="{yk}">全年</button>'
    chips += "".join(f'<button class="pp-chip" data-key="{q}">{q.split("年")[1]}</button>' for q in tg["季度"])
    cells = "".join(
        f'<button class="pp-m" data-m="{m}"{"" if m <= cur_month else " disabled"}>{m}月</button>'
        for m in range(1, 13))
    return (f'<div class="pbar"><label class="pbar-l">看哪段</label>'
            f'<button id="periodBtn" class="psel pbtn" data-year="{year}" data-cur="{cur_month}" '
            f'aria-haspopup="true" aria-expanded="false">{year}年 <span class="pbtn-c">▾</span></button>'
            f'<div id="ppanel" class="ppanel" hidden>'
            f'<div class="pp-row">{chips}</div>'
            f'<div class="pp-hint" id="ppHint">自选区间：点起始月，再点结束月</div>'
            f'<div class="pp-grid">{cells}</div>'
            f'</div></div>')


def _pv(key, default_key, inner):
    return f'<div class="pv" data-blk="{key}" style="{"" if key == default_key else "display:none"}">{inner}</div>'


JS = """
(function(){
 var root=document.documentElement, btn=document.getElementById('themeBtn');
 function setL(l){root.classList.toggle('theme-light',l);document.body.classList.toggle('theme-light',l);
   btn.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';}
 try{setL(localStorage.getItem('cockpit-theme')==='light');}catch(e){}
 btn.addEventListener('click',function(){var l=!root.classList.contains('theme-light');setL(l);
   try{localStorage.setItem('cockpit-theme',l?'light':'dark');}catch(e){}});
 // 周期选择：日历面板。所有周期块已预渲染，这里只切显示、不算任何数。
 var pbtn=document.getElementById('periodBtn'),ppanel=document.getElementById('ppanel');
 if(pbtn&&ppanel){
  var pYear=pbtn.getAttribute('data-year'),pCur=+pbtn.getAttribute('data-cur'),pStart=null;
  window._curBlk=pYear+'年';
  // 切周期：整区 periodSync 统一淡出→切 .pv→淡入（与基本情况同观感；零金额运算）
  var _periodT=null;
  // 迭代21：回款卡全年视角 · 选中周期月份高亮（映射由服务端 data-rm-map 下发，前端只读写 class）
  window._syncRmHighlight=function(key){
    var card=document.getElementById('rcCard');if(!card)return;
    var els=card.querySelectorAll('[data-rm]');
    var yearKey=card.getAttribute('data-rm-year')||'';
    var mapStr=card.getAttribute('data-rm-map')||'{}';
    var map={};try{map=JSON.parse(mapStr);}catch(e){map={};}
    var months=map[key];
    // 全年 / 无映射 / 映射含 12 月 → 全亮（去掉任何额外样式）
    var full=!months||key===yearKey||months.length>=12;
    if(full){
      card.classList.remove('rc-rm-filter');
      els.forEach(function(el){el.classList.remove('rm-dim','rm-on');});
      return;}
    card.classList.add('rc-rm-filter');
    var on={};months.forEach(function(m){on[String(m)]=1;});
    els.forEach(function(el){
      var m=el.getAttribute('data-rm');
      if(on[m]){el.classList.add('rm-on');el.classList.remove('rm-dim');}
      else{el.classList.add('rm-dim');el.classList.remove('rm-on');}
    });};
  function applyPeriod(key,label){
    if(key===window._curBlk){ // 同周期只更新按钮态
      pbtn.innerHTML=label+' <span class="pbtn-c">▾</span>';
      ppanel.querySelectorAll('.pp-chip').forEach(function(c){c.classList.toggle('on',c.getAttribute('data-key')===key);});
      if(window._syncRmHighlight)window._syncRmHighlight(key);
      return;}
    window._curBlk=key;
    pbtn.innerHTML=label+' <span class="pbtn-c">▾</span>';
    ppanel.querySelectorAll('.pp-chip').forEach(function(c){c.classList.toggle('on',c.getAttribute('data-key')===key);});
    var sync=document.getElementById('periodSync');
    function swap(){
      document.querySelectorAll('.pv').forEach(function(x){x.style.display=x.getAttribute('data-blk')===key?'':'none';});
      if(window._syncDailyDates)window._syncDailyDates(key);
      if(window._syncRmHighlight)window._syncRmHighlight(key);}
    if(!sync||(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)){
      swap();return;}
    if(_periodT){clearTimeout(_periodT);_periodT=null;}
    sync.classList.remove('is-period-enter');
    sync.classList.add('is-period-switching');
    _periodT=setTimeout(function(){
      swap();
      sync.classList.remove('is-period-switching');
      // 强制重播入场动画
      void sync.offsetWidth;
      sync.classList.add('is-period-enter');
      _periodT=setTimeout(function(){sync.classList.remove('is-period-enter');_periodT=null;},380);
    },150);}
  window.applyPeriod=applyPeriod;
  // 初始默认年：全亮（显式调一次，与 _curBlk 对齐）
  if(window._syncRmHighlight)window._syncRmHighlight(window._curBlk);
  function markMonths(a,b){ppanel.querySelectorAll('.pp-m').forEach(function(x){
    var m=+x.getAttribute('data-m');
    x.classList.toggle('sel',a!==null&&b!==null&&m>=a&&m<=b);
    x.classList.toggle('arm',a!==null&&b===null&&m===a);});}
  function hint(t){document.getElementById('ppHint').textContent=t;}
  pbtn.addEventListener('click',function(e){e.stopPropagation();
    var open=ppanel.hasAttribute('hidden');
    if(open){ppanel.removeAttribute('hidden');pbtn.setAttribute('aria-expanded','true');}
    else{ppanel.setAttribute('hidden','');pbtn.setAttribute('aria-expanded','false');}});
  document.addEventListener('click',function(e){
    if(!ppanel.hasAttribute('hidden')&&!ppanel.contains(e.target)&&e.target!==pbtn){
      ppanel.setAttribute('hidden','');pbtn.setAttribute('aria-expanded','false');}});
  ppanel.querySelectorAll('.pp-chip').forEach(function(c){c.addEventListener('click',function(){
    pStart=null;markMonths(null,null);hint('自选区间：点起始月，再点结束月');
    var k=c.getAttribute('data-key');applyPeriod(k,c.textContent==='全年'?pYear+'年':pYear+'年'+c.textContent);});});
  ppanel.querySelectorAll('.pp-m').forEach(function(x){x.addEventListener('click',function(){
    var m=+x.getAttribute('data-m');if(m>pCur)return;
    if(pStart===null||m===pStart){pStart=m;markMonths(m,m);
      applyPeriod(pYear+'年'+m+'月',pYear+'年'+m+'月');hint('已选 '+m+'月，再点另一个月拉成区间');}
    else{var a=Math.min(pStart,m),b=Math.max(pStart,m);markMonths(a,b);
      applyPeriod(pYear+'年'+a+'-'+b+'月',pYear+'年'+a+'~'+b+'月');
      hint('已选 '+a+'~'+b+'月，点任意月重新开始');pStart=null;}});});
 }
 // 利润表大类 → 右侧抽屉看构成（主表定位不动、不再顶下方图表）
 var dr=document.getElementById('drawer'),dbody=document.getElementById('drawerBody'),dttl=document.getElementById('drawerTitle');
 function openDrawer(cat,scope){if(cat==null)return;
   var el=scope.querySelector('.pl-detail[data-cat="'+CSS.escape(String(cat))+'"]');if(!el||!dr)return;
   dttl.textContent=el.getAttribute('data-title');dbody.innerHTML=el.innerHTML;
   dr.classList.add('open');dr.setAttribute('aria-hidden','false');}
 function closeDrawer(){if(!dr)return;dr.classList.remove('open');dr.setAttribute('aria-hidden','true');}
 document.addEventListener('click',function(e){
   var op=e.target.closest('.pl-open');
   if(op){openDrawer(op.getAttribute('data-cat'),op.closest('.pv')||document);return;}
   if(e.target.closest('[data-close]'))closeDrawer();});
 document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDrawer();});
 document.addEventListener('click',function(e){var tb=e.target.closest('.ev-tab');if(!tb)return;
   var m=tb.getAttribute('data-ev');
   document.querySelectorAll('.ev-tab').forEach(function(x){x.classList.toggle('on',x.getAttribute('data-ev')===m);});
   document.querySelectorAll('.ev-pane').forEach(function(x){x.style.display=x.getAttribute('data-ev')===m?'':'none';});});
 var tip=document.getElementById('tip');
 document.addEventListener('mousemove',function(e){var el=e.target.closest('[data-tip]');
   if(!el){tip.style.opacity=0;return;}tip.innerHTML=el.getAttribute('data-tip');tip.style.opacity=1;
   var x=e.clientX+14,y=e.clientY+14;if(x+tip.offsetWidth>innerWidth)x=e.clientX-tip.offsetWidth-14;
   if(y+tip.offsetHeight>innerHeight)y=e.clientY-tip.offsetHeight-14;tip.style.left=x+'px';tip.style.top=y+'px';});
})();
"""

# 看的人自改密码（v8.0）：弹窗文案必须含「密码管理员可见，请勿使用你在其他地方用的密码」
PW_MODAL_HTML = """
<div id="pwModal" style="display:none;position:fixed;inset:0;z-index:80;background:#0f172acc;
 align-items:center;justify-content:center">
 <div style="background:#1e293b;color:#e2e8f0;padding:22px 24px;border-radius:12px;width:min(360px,92vw);
  box-shadow:0 12px 40px #0009;font-family:-apple-system,system-ui,sans-serif">
  <div style="font-size:16px;font-weight:700;margin-bottom:10px">修改密码</div>
  <div style="font-size:12px;color:#fde68a;line-height:1.5;margin-bottom:12px;padding:8px 10px;
   background:#422006;border-radius:8px">密码管理员可见，请勿使用你在其他地方用的密码</div>
  <label style="font-size:12px;color:#94a3b8">旧密码</label>
  <input id="pwOld" type="password" autocomplete="current-password"
   style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;border-radius:7px;
   border:1px solid #334155;background:#0f172a;color:#e2e8f0">
  <label style="font-size:12px;color:#94a3b8">新密码（至少 4 位）</label>
  <input id="pwNew" type="password" autocomplete="new-password"
   style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;border-radius:7px;
   border:1px solid #334155;background:#0f172a;color:#e2e8f0">
  <div id="pwMsg" style="font-size:12px;color:#f87171;min-height:16px;margin-bottom:8px"></div>
  <div style="display:flex;gap:8px;justify-content:flex-end">
   <button type="button" id="pwCancel" style="padding:7px 12px;border-radius:7px;border:1px solid #334155;
    background:transparent;color:#e2e8f0;cursor:pointer">取消</button>
   <button type="button" id="pwOk" style="padding:7px 14px;border-radius:7px;border:0;
    background:#8b5cf6;color:#fff;cursor:pointer">保存</button>
  </div>
 </div>
</div>
"""

PW_JS = r"""
(function(){
 var btn=document.getElementById('pwBtn'),modal=document.getElementById('pwModal');
 if(!btn||!modal)return;
 function open(){modal.style.display='flex';document.getElementById('pwMsg').textContent='';
  document.getElementById('pwOld').value='';document.getElementById('pwNew').value='';}
 function close(){modal.style.display='none';}
 btn.addEventListener('click',open);
 document.getElementById('pwCancel').addEventListener('click',close);
 modal.addEventListener('click',function(e){if(e.target===modal)close();});
 document.getElementById('pwOk').addEventListener('click',function(){
  var old=document.getElementById('pwOld').value,nw=document.getElementById('pwNew').value;
  var msg=document.getElementById('pwMsg');
  if(nw.length<4){msg.textContent='新密码至少 4 位';return;}
  msg.textContent='保存中…';msg.style.color='#94a3b8';
  fetch('/api/my_passwd',{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({old:old,new:nw})})
   .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d,status:r.status};});})
   .then(function(x){
     if(!x.ok){msg.style.color='#f87171';msg.textContent=(x.d&&x.d.detail)||('失败 '+x.status);return;}
     msg.style.color='#86efac';msg.textContent=x.d.note||'已修改';
     setTimeout(close,900);
   }).catch(function(e){msg.style.color='#f87171';msg.textContent='网络错误：'+e.message;});
 });
})();
"""

# 导出=当前所选周期的整页图片（服务端 Playwright 截图返回 PNG，前端只发请求零运算）。
# 双击打开的静态文件版没有服务，点了给提示。旧"Excel+HTML快照 zip"导出已按明昊要求移除（2026-07-11）。
EXPORT_JS = r"""
(function(){
 var btn=document.getElementById('exportBtn');if(!btn)return;
 btn.addEventListener('click',function(){
   if(location.protocol==='file:'){alert('图片导出需在看板服务页面使用（浏览器打开 http://服务器:端口/）');return;}
   var k=window._curBlk||'';var old=btn.innerHTML;btn.disabled=true;btn.innerHTML='<span>⬇</span> 生成中…';
   var url=btn.getAttribute('data-export')||'/export.png';
   fetch(url+'?blk='+encodeURIComponent(k)).then(function(r){
     if(!r.ok){return r.text().then(function(t){throw new Error(t||('HTTP '+r.status));});}
     var fn=decodeURIComponent(r.headers.get('X-Filename')||'')||'甲骨易智能经营罗盘.png';
     return r.blob().then(function(b){var a=document.createElement('a');a.href=URL.createObjectURL(b);
       a.download=fn;document.body.appendChild(a);a.click();a.remove();});
   }).catch(function(e){alert('导出失败：'+e.message);})
     .finally(function(){btn.disabled=false;btn.innerHTML=old;});
 });
})();
"""


# ---------- 按天明细（迭代17 批次A：常显 + 跟顶 + 返回默认全年）----------
# 铁律2：金额显示串全部由 /api/daily 后端算好（*_disp），这里的 JS 只拼字符串、零金额运算；
# 铁律10：接口返回的部门/销售/客户名是自由文本，插 HTML 前必过 esc。file:// 打开时 fetch 失败给提示。
# 顶部「看哪段」不动；本面板只改板块③排名（查询才打 /api/daily；跟顶只改日期框）。
DAILY_HTML = """
<div class="card" id="dailyPanel" style="margin-bottom:16px">
  <div class="card-h">按时间段看</div>
  <div class="daily-bar">
    <input type="date" id="dailyS"> ~ <input type="date" id="dailyE">
    <button class="toggle" id="dailyGo" type="button">查询</button>
    <button class="toggle" id="dailyToday" type="button">今日</button>
    <button class="toggle" id="dailyMonth" type="button">本月</button>
    <button class="toggle" id="dailyClose" type="button">本年</button>
    <span id="dailySum" class="daily-note"></span>
  </div>
</div>
<div id="rkModal" style="display:none">
  <div class="rkm-box">
    <div class="card-h"><span id="rkmTitle"></span> <span class="tag" id="rkmTag"></span>
      <button class="toggle daily-close" id="rkmClose" type="button"><span>✕</span> 关闭</button></div>
    <div class="rkm-list" id="rkmList"></div>
  </div>
</div>"""

DAILY_JS = """
(function(){
 var panel=document.getElementById('dailyPanel');
 if(!panel)return;
 var iS=document.getElementById('dailyS'),iE=document.getElementById('dailyE'),sum=document.getElementById('dailySum');
 var rkGlobal=document.getElementById('rankViews'),rkCustom=document.getElementById('rkCustom');
 var range=null;   // {s,e}=当前生效的自定义日段；null=跟顶部预渲染排名
 var KIND_TITLE={orders_by_dept:'下单 · 按部门',orders_by_bu:'下单 · 按BU',orders_by_sales:'下单 · 按销售',receipts_by_customer:'回款 · 按客户'};
 function yearStr(){var b=document.getElementById('periodBtn');return b?b.getAttribute('data-year'):'';}
 function yearKey(){return yearStr()+'年';}
 function yearRange(){var y=yearStr();return {s:y+'-01-01',e:y+'-12-31'};}
 /** 从预渲染排名块读该周期起止日（后端已写 data-start/end）；无则回退全年。纯字符串，零金额运算。 */
 function datesForKey(key){
  var el=document.querySelector('#rankViews .pv[data-blk="'+key+'"] .rk-grid[data-start]');
  if(el){var s=el.getAttribute('data-start')||'',e=el.getAttribute('data-end')||'';
    if(s&&e)return {s:s,e:e};}
  return yearRange();}
 function fillDates(se){if(!se)return;iS.value=se.s;iE.value=se.e;}
 /** 非自定义态：日期框跟顶部；不请求 /api/daily。 */
 window._syncDailyDates=function(key){if(range!==null)return;fillDates(datesForKey(key||window._curBlk||yearKey()));};
 // 首屏默认全年起止（顶部默认全年）
 fillDates(yearRange());
 iS.addEventListener('change',function(){if(iE.value&&iE.value<iS.value)iE.value=iS.value;});
 var esc=function(s){return String(s==null?'':s).replace(/[&<>\"]/g,function(c){
   return({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'})[c];});};
 /** 本年：清自定义、排名回预渲染全年、顶部切全年、日期回全年。 */
 function restoreYear(){
  range=null;sum.textContent='';
  if(rkCustom){rkCustom.style.display='none';rkCustom.innerHTML='';}
  if(rkGlobal)rkGlobal.style.display='';
  var yk=yearKey(),yl=yearStr()+'年';
  if(window.applyPeriod)window.applyPeriod(yk,yl);
  else{window._curBlk=yk;fillDates(yearRange());}
 }
 document.getElementById('dailyClose').addEventListener('click',restoreYear);
 function isoToday(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
 function monthRange(){var d=new Date(),y=d.getFullYear(),m=d.getMonth()+1;
   var last=new Date(y,m,0).getDate();
   return {s:y+'-'+String(m).padStart(2,'0')+'-01',e:y+'-'+String(m).padStart(2,'0')+'-'+String(last).padStart(2,'0')};}
 var btnToday=document.getElementById('dailyToday'),btnMonth=document.getElementById('dailyMonth');
 if(btnToday)btnToday.addEventListener('click',function(){var t=isoToday();iS.value=t;iE.value=t;document.getElementById('dailyGo').click();});
 if(btnMonth)btnMonth.addEventListener('click',function(){var r=monthRange();iS.value=r.s;iE.value=r.e;document.getElementById('dailyGo').click();});
 function rowsHtml(rk){
  var h='',items=(rk&&rk.items)||[];
  if(!items.length&&!(rk&&rk.unfilled))return '<div class="ev-empty">本期无数据</div>';
  items.forEach(function(it,i){h+='<div class="ev-row rk-row"><span class="rk-no">'+(i+1)+'</span>'+
    '<span class="ev-name" title="'+esc(it.name)+'">'+esc(it.name)+'</span><span class="ev-track"></span>'+
    '<span class="ev-amt">'+esc(it.disp)+'</span><span class="rk-meta">'+it.count+'笔</span></div>';});
  if(rk&&rk.others)h+='<div class="ev-row rk-row rk-others rk-more" title="点开看 10 名以后的完整明细"><span class="rk-no">…</span>'+
    '<span class="ev-name">其余 '+rk.others.names+' 个 <span class="rk-open">点开看明细 ›</span></span>'+
    '<span class="ev-track"></span><span class="ev-amt">'+esc(rk.others.disp)+'</span><span class="rk-meta">'+rk.others.count+'笔</span></div>';
  if(rk&&rk.unfilled)h+='<div class="ev-row rk-row rk-unfilled"><span class="rk-no">⚠</span><span class="ev-name">（未填）</span>'+
    '<span class="ev-track"></span><span class="ev-amt">'+esc(rk.unfilled.disp)+'</span><span class="rk-meta">'+rk.unfilled.count+'笔·待归类</span></div>';
  return h;}
 function rkHtml(kind,rk,tag){
  return '<div class="card" data-kind="'+kind+'"><div class="card-h">'+KIND_TITLE[kind]+' <span class="tag">'+esc(tag)+'</span></div>'+
    '<div class="ev-list rk-list">'+rowsHtml(rk)+'</div></div>';}
 document.getElementById('dailyGo').addEventListener('click',function(){
  var s=iS.value,e=iE.value;
  if(!s||!e){sum.textContent='请选起止日期';return;}
  sum.textContent='查询中…';
  fetch('/api/daily?start='+s+'&end='+e).then(function(r){
    if(!r.ok)return r.json().then(function(d){throw new Error(d.detail||('HTTP '+r.status));});
    return r.json();
  }).then(function(d){
    range={s:s,e:e};
    sum.innerHTML='这段合计：下单 <b>'+esc(d.totals.orders_disp)+'</b>·'+d.totals.orders_count+
      '笔 ｜ 回款 <b>'+esc(d.totals.receipts_disp)+'</b>·'+d.totals.receipts_count+'笔';
    var tag=(s===e)?('只看 '+s):(s+' ~ '+e);
    // 与全年预渲染一致：有 orders_by_bu 则首卡按 BU，否则回退按部门
    var firstKind=d.rankings.orders_by_bu?'orders_by_bu':'orders_by_dept';
    var firstRk=d.rankings[firstKind]||d.rankings.orders_by_dept;
    rkCustom.innerHTML='<div class="grid-3 rk-grid" data-start="'+esc(s)+'" data-end="'+esc(e)+'">'+
      rkHtml(firstKind,firstRk,tag)+
      rkHtml('orders_by_sales',d.rankings.orders_by_sales,tag)+
      rkHtml('receipts_by_customer',d.rankings.receipts_by_customer,tag)+'</div>';
    rkGlobal.style.display='none';rkCustom.style.display='';
  }).catch(function(err){sum.textContent='查询失败：'+err.message+
    '（要在服务器版页面用；file:// 快照不支持）';});
 });
 // 「其余 N 个」点开全量明细：预渲染卡与自定义卡共用（区间取最近的 data-start/end）
 var modal=document.getElementById('rkModal');
 // 弹窗须挂 body 直下：否则被 #periodSync 的 will-change:transform 祖先困住，
 // position:fixed 变成相对该祖先（高达整页）定位 → 弹窗跑到页面中部而非视口居中。
 if(modal&&modal.parentElement!==document.body)document.body.appendChild(modal);
 document.addEventListener('click',function(ev){
  var row=ev.target.closest?ev.target.closest('.rk-more'):null;
  if(!row)return;
  var card=row.closest('.card'),grid=row.closest('[data-start]');
  if(!card||!grid)return;
  var kind=card.dataset.kind,s=grid.dataset.start,e=grid.dataset.end;
  if(!kind||!s||!e)return;
  document.getElementById('rkmTitle').textContent=(KIND_TITLE[kind]||'')+' · 完整排名';
  document.getElementById('rkmTag').textContent=(s===e)?s:(s+' ~ '+e);
  var list=document.getElementById('rkmList');
  list.innerHTML='<div class="ev-empty">加载中…</div>';modal.style.display='';
  fetch('/api/daily?start='+s+'&end='+e+'&top=2000').then(function(r){
    if(!r.ok)return r.json().then(function(d){throw new Error(d.detail||('HTTP '+r.status));});
    return r.json();
  }).then(function(d){
    var rk=d.rankings[kind]||{};
    list.innerHTML='<div class="ev-list">'+rowsHtml(rk)+'</div>';
  }).catch(function(err){list.innerHTML='<div class="ev-empty">加载失败：'+esc(err.message)+
    '（要在服务器版页面用；file:// 快照不支持）</div>';});
 });
 document.getElementById('rkmClose').addEventListener('click',function(){modal.style.display='none';});
 modal.addEventListener('click',function(ev){if(ev.target===modal)modal.style.display='none';});
})();
"""


def render_dashboard(summary, cfg, logo_b64):
    meta = summary["meta"]; P = summary["periods"]; FT = summary["expense_fine_type"]
    yk = meta["year_key"]
    all_keys = ([yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
                + meta["tab_groups"].get("区间", []))
    logo = f'<img class="tb-logo" src="{logo_b64}" alt="logo">' if logo_b64 else ""
    unc = meta["unclassified"]["expense"]
    # 看端不再展示底部「口径提示」淡字（未分类仍进利润表全年行 + 管理端体检/异常处理）

    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    BUO = meta.get("bu_orders") or {}
    kpi_views = "".join(
        _pv(k, yk, render_basic(k, P, meta["year"], month_keys, budget, bu_orders=BUO.get(k)))
        for k in all_keys)
    # 费用构成：按大类 | 按类别（预算明细费用类型，与 FT 同源守恒）| 按业务BU
    BP = summary.get("expense_by_profit_center", {})
    donut_views = "".join(
        _pv(k, yk, render_expense_views(P[k], _fine_to_rows(FT.get(k) or {}), BP.get(k)))
        for k in all_keys)

    unc_amt = float(unc.get("amount") or 0) if unc else 0.0
    # 未分类金额行只挂全年利润表（分周期拆分未做，避免假精确）
    pl_views = "".join(
        _pv(k, yk, render_pl_table(P[k], FT.get(k, {}), unclassified_amt=unc_amt if k == yk else None))
        for k in all_keys)
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k])) for k in all_keys)
    rank_views = "".join(_pv(k, yk, render_rankings(P[k])) for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]

    # 回款情况：全年视角固定 12 月 + 周期高亮映射（迭代21）；交付金额→已交付未回款
    receipts_html = render_receipts(
        summary['receipt_order_monthly'], summary['meta'].get('budget'),
        period_months_map=_period_months_map(summary), year_key=yk,
        delivered_gross=P[yk]["revenue_gross"])
    receipts_budget = f'<div class="period-receipts" style="margin-top:16px">{receipts_html}</div>'

    body = f"""
{PARTICLES_HTML}
<div class="topbar">{logo}<span class="tb-title">甲骨易智能经营<b>罗盘</b></span>{_title_version_html()}
 <span class="tb-right"><span class="live"><i></i>实时</span><span class="tb-time">数据更新 {meta['generated_at']}</span>
 <button class="toggle" id="pwBtn" type="button"><span>🔑</span> 密码</button>
 <button class="toggle" id="exportBtn"><span>⬇</span> 导出</button>
 <button class="toggle" id="themeBtn"><span>◑</span> 浅色</button></span></div>
{PW_MODAL_HTML}
<div class="wrap">
 {render_period_bar(summary)}
 <div id="periodSync">
 <div class="sec"><span class="sec-n">一</span><span class="sec-t">基本情况</span></div>
 {kpi_views}

 <div class="sec"><span class="sec-n">二</span><span class="sec-t">经营利润</span></div>
 <div class="grid-2">
   <div class="grid-2-main">{render_trend(summary['trend'], hl)}<div style="margin-top:16px">{donut_views}</div></div>
   <div class="card pl-card"><div class="card-h">管理利润表 <span class="tag">算到税前利润</span></div>{pl_views}</div>
 </div>

 <div class="sec"><span class="sec-n">三</span><span class="sec-t">收入与毛利结构</span></div>
 <div id="profitRankViews">{profit_rank_views}</div>
 <div class="pr-formula">
  <span class="pr-f-h">计算逻辑</span>
  <span class="pr-f-item"><b>交付金额</b> = 智云含税原数</span>
  <span class="pr-f-item"><b>交付收入</b> = 交付金额 ÷ 1.06</span>
  <span class="pr-f-item"><b>系统成本率</b> = 项目成本 ÷ 交付收入</span>
  <span class="pr-f-item"><b>集中度</b> = 前5大交付收入 ÷ 期内总交付收入</span>
 </div>

 <div class="sec"><span class="sec-n">四</span><span class="sec-t">资金与回款</span></div>
 {receipts_budget}
 {DAILY_HTML}
 <div id="rankViews">{rank_views}</div>
 <div id="rkCustom" style="display:none"></div>
 </div>
 <div class="foot">
  甲骨易智能经营罗盘 · 财务部 &nbsp;|&nbsp;
  税前利润 = 管理毛利 − 期间费用 − 附加税费 ± 其他损益 &nbsp;|&nbsp;
  交付收入 = 交付金额 ÷ 1.06
 </div>
</div>
{DRAWER_HTML}
<div id="tip"></div>
<script>{JS}{EXPORT_JS}{DAILY_JS}{PROFIT_JS}{PW_JS}</script>
"""
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>甲骨易智能经营罗盘</title><style>{theme.get_css()}</style></head><body>{body}</body></html>')


# ---------- BU 分页（迭代 14 → 费用直记）：完整利润表 ----------
# 收入/成本：智云按销售过滤；费用：台账「利润归属中心」=本 BU 直记 + 可选公共池×比例；
# 手填：按 BU 范围（有填显示金额，无填标注待填）。严格保密：summary 已按本 BU 过滤。

def _bu_pending_row(name, note="—"):
    """待补数据行：金额位显示 — 而非 ¥0（不把"没有数"显示成"数是 0"）。"""
    return (f'<div class="pl-row"><span class="dot none"></span>'
            f'<div class="pl-name">{_esc(name)}</div>'
            f'<span class="pl-amt" style="color:var(--mut2);font-size:12px">{_esc(note)}</span></div>')


def render_bu_pl_table(p, alloc_meta=None, fine=None):
    """BU 版利润表（看端精简备注）：费用有数就显示；抽屉只列名目+金额；公式保留。"""
    alloc = alloc_meta or {}
    on = bool(alloc.get("enabled"))
    rdisp = alloc.get("ratio_disp") or ""
    exp = p.get("expense") or {}
    man = p.get("manual") or {}
    led = p.get("ledger_expenses") or {}
    exp_total = float(exp.get("total") or 0)
    has_fee = exp_total > 0.005 or any(float(led.get(c) or 0) > 0.005 for c in led)
    man_keys = ("营销人力成本", "管理人力成本", "研发人力成本", "财务费用补充",
                "PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失",
                "技术流量成本", "其他（生产成本）", "其他损益")
    has_manual = any(abs(float(man.get(k) or 0)) > 0.005 for k in man_keys)
    other_pl = float(p.get("other_pl") or 0)

    if on and rdisp:
        tag_note = f"含公共分摊 {rdisp}"
    elif has_fee:
        tag_note = "本BU直记"
    else:
        tag_note = ""

    fine = fine or {}
    alloc_added = p.get("alloc_added") or {}
    # 大类 → (抽屉key, 手填项, 台账类)；财务费用的手填是"补充"、挂台账行后面
    _GROUPS = (("sales", "营销费用", "营销人力成本", "市场费用"),
               ("admin", "管理费用", "管理人力成本", "管理费用"),
               ("fixed", "固定运营费用", None, "固定运营费用"),
               ("rd", "研发费用", "研发人力成本", "技术服务费"),
               ("fin", "财务费用", None, "财务费用"))

    rows = [_row("交付收入（不含税）", p["revenue_net"], "system", "交付金额÷1.06")]
    rows.append(_open_row("cost", "交付成本（生产成本）", -p["production_cost"]))
    rows.append(_row("管理毛利", p["gross_profit"], "", total=True))
    exp_details = []
    for cat_key, nm, man_key, led_cat in _GROUPS:
        v = float(exp.get(nm) or 0)
        if has_fee or abs(v) > 0.005:
            rows.append(_open_row(cat_key, nm, -v))
            alloc_amt = float(alloc_added.get(led_cat) or 0.0)
            direct_amt = round(float(led.get(led_cat) or 0.0) - alloc_amt, 2)
            inner = ""
            if man_key:
                inner += _drow(man_key, -float(man.get(man_key) or 0), "manual")
            inner += _d_ledger(f"{led_cat}（台账直记）", direct_amt, "", fine.get(led_cat))
            if nm == "财务费用":
                inner += _drow("财务费用补充", -float(man.get("财务费用补充") or 0), "manual")
            if alloc_amt > 0.005:
                inner += _drow("分摊自公共", -alloc_amt, "ledger")
            exp_details.append(_detail_block(cat_key, f"{nm}构成", inner))
        else:
            rows.append(_bu_pending_row(nm))
    rows.append(_row("附加税费", -p["surtax"], "system", "净收入×6%×12%"))
    if abs(other_pl) > 0.005 or has_manual:
        rows.append(_row("其他损益", other_pl, "manual", ""))
    else:
        rows.append(_bu_pending_row("其他损益"))
    pretax_src = "毛利−期间费用−附加税±其他"
    rows.append(_row("税前利润", p["pretax_profit"], "", pretax_src, grand=True))
    rows.append(_pct_row("销售利润率", p.get("pretax_margin_pct"), "税前利润÷交付收入"))

    prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    if has_manual:
        man_cost_html = "".join(
            _drow(n, -float(man.get(n) or 0), "manual") for n in prod_manual)
    else:
        man_cost_html = "".join(_drow(n, 0.0, "manual") for n in prod_manual)
    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system")
                  + _drow("系统内部译员", p["inhouse_cost"], "system")
                  + _drow("直接成本增值税", float(man.get("直接成本增值税") or 0), "manual")
                  + man_cost_html)
    details = _detail_block("cost", "交付成本构成", cost_inner) + "".join(exp_details)
    kinds = ('<div class="kinds">'
             '<span><i style="background:var(--kind-system)"></i>智云</span>'
             '<span><i style="background:var(--kind-ledger)"></i>台账</span>'
             '<span><i style="background:var(--kind-manual)"></i>手填</span></div>')
    return (f'<div class="pl">{"".join(rows)}</div>{kinds}'
            f'<div class="pl-details" hidden>{details}</div>', tag_note)


def render_bu_page(bu_name, summary, cfg, logo_b64):
    """单 BU 独立只读页（迭代22·D：口径与整体页全对齐，只是数按本 BU 过滤）：
    周期选择 + KPI + 趋势图 + 利润表（可下钻）+ 费用构成（大类/类别）+ 收入毛利结构 + 回款情况 + 排名 + 导出。
    仍不含全公司出口（/api/daily、/api/profit_ranking 弹窗在本页不启用·铁律12）。"""
    meta = summary["meta"]; P = summary["periods"]; FT = summary.get("expense_fine_type") or {}
    yk = meta["year_key"]
    all_keys = ([yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
                + meta["tab_groups"].get("区间", []))
    logo = f'<img class="tb-logo" src="{logo_b64}" alt="logo">' if logo_b64 else ""
    alloc = meta.get("public_allocation") or {"enabled": False}
    pl_parts, tag_note = [], ""
    for k in all_keys:
        pl_html, tag_note = render_bu_pl_table(P[k], alloc, fine=FT.get(k))
        pl_parts.append(_pv(k, yk, pl_html))
    pl_views = "".join(pl_parts)
    donut_views = "".join(_pv(k, yk, render_bu_expense_views(P[k], FT.get(k))) for k in all_keys)
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k])) for k in all_keys)
    rank_views = "".join(_pv(k, yk, render_rankings(P[k])) for k in all_keys)
    name = _esc(bu_name)
    # 看端不展示口径说明长文（管理端数据/设置里看明细）

    # BU 基本情况 KPI（与整体页同构；目标取该 BU 的 budget meta，无则空态）
    month_keys = meta["tab_groups"]["月"]
    budget = meta.get("budget")
    kpi_views = "".join(_pv(k, yk, render_basic(k, P, meta["year"], month_keys, budget)) for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]
    # 回款情况：与整体页同款；交付金额取本 BU 已过滤的全年 revenue_gross（铁律12）
    receipts_html = render_receipts(
        summary['receipt_order_monthly'], budget,
        period_months_map=_period_months_map(summary), year_key=yk,
        delivered_gross=P[yk]["revenue_gross"])
    from urllib.parse import quote as _q
    export_url = f"/bu/{_q(bu_name)}/export.png"
    pl_tag = f' <span class="tag">{_esc(tag_note)}</span>' if tag_note else ""

    body = f"""
{PARTICLES_HTML}
<div class="topbar">{logo}<span class="tb-title">甲骨易智能经营<b>罗盘</b> · {name}</span>{_title_version_html()}
 <span class="tb-right">
 <span class="live"><i></i>实时</span><span class="tb-time">数据更新 {meta['generated_at']}</span>
 <button class="toggle" id="exportBtn" data-export="{export_url}"><span>⬇</span> 导出</button>
 <button class="toggle" id="pwBtn" type="button"><span>🔑</span> 密码</button>
 <button class="toggle" id="themeBtn"><span>◑</span> 浅色</button></span></div>
{PW_MODAL_HTML}
<div class="wrap">
 <div class="bu-subnav" role="navigation" aria-label="返回整体">
  <a class="bu-back bu-back-inline" href="/" title="返回整体看板（点一下即回主页/刷新）">← 返回整体</a>
  <span class="bu-subnav-cur">当前 BU · <b>{name}</b></span>
 </div>
 {render_period_bar(summary)}
 <div id="periodSync">
 <div class="sec"><span class="sec-n">一</span><span class="sec-t">基本情况</span></div>
 {kpi_views}
 <div class="sec"><span class="sec-n">二</span><span class="sec-t">{name} · 经营利润</span></div>
 <div class="grid-2">
   <div class="grid-2-main">{render_trend(summary['trend'], hl)}<div style="margin-top:16px">{donut_views}</div></div>
   <div class="card pl-card"><div class="card-h">管理利润表{pl_tag}</div>{pl_views}</div>
 </div>
 <div class="sec"><span class="sec-n">三</span><span class="sec-t">{name} · 收入与毛利结构</span></div>
 <div id="profitRankViews">{profit_rank_views}</div>
 <div class="sec"><span class="sec-n">四</span><span class="sec-t">{name} · 资金与回款</span></div>
 <div class="period-receipts" style="margin-top:4px">{receipts_html}</div>
 <div id="rankViews">{rank_views}</div>
 </div>
 <div class="foot">
  甲骨易智能经营罗盘 · {name} &nbsp;|&nbsp;
  税前利润 = 管理毛利 − 期间费用 − 附加税费 ± 其他损益 &nbsp;|&nbsp;
  交付收入 = 交付金额 ÷ 1.06
 </div>
</div>
{DRAWER_HTML}
<div id="tip"></div>
<style>.rk-open{{display:none}}</style>
<script>{JS}{PW_JS}{EXPORT_JS}</script>
"""
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>甲骨易智能经营罗盘 · {name}</title><style>{theme.get_css()}</style></head><body>{body}</body></html>')
