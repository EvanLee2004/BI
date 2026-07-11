#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装经营驾驶舱 HTML（科技风暗色默认 + 浅色切换）。四段骨架：基本情况/经营利润/收入与毛利结构/下单与回款排名。
全局时间选择器（月/季/年，默认年）驱动 基本情况+利润表+费用构成 一起切；趋势图/回款图是整年时间线。
所有金额 Python 算好，JS 只做主题切换/周期切换/展开折叠/提示定位，不做任何金额运算。"""
from __future__ import annotations

import charts
import theme

GROUP_COLORS = {"营销费用": "var(--blue)", "管理费用": "var(--purple)", "固定运营费用": "var(--teal)",
                "研发费用": "var(--orange)", "财务费用": "var(--cost)"}
LED_OF = {"营销费用": "市场费用", "管理费用": "管理费用", "固定运营费用": "固定运营费用",
          "研发费用": "技术服务费", "财务费用": "财务费用"}

# 基本情况 KPI 卡（陆总口径：4 张，各配环比+迷你趋势线）：(标签, 取值键, 来源, 涨为好, 附率键, 趋势线色)
KPI_CARDS = [
    ("收入", "revenue_net", "智云·交付额÷1.06", True, None, "var(--blue)"),
    ("成本费用合计", "_cost_total", "生产成本＋期间费用", False, None, "var(--cost)"),
    ("税前利润", "pretax_profit", "毛利−费用−附加税+其他", True, "pretax_margin_pct", "var(--pos)"),
    ("回款额", "receipts", "智云·回款(到账)", True, None, "var(--teal)"),
]
# 回款下单率防误读小字（回款柱图 + 回款额卡下方两处都放，防姜总误读）
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
    """KPI 取值：成本费用合计=生产成本+期间费用（展示聚合，非新口径），其余直接取。"""
    if key == "_cost_total":
        return p["production_cost"] + p["expense"]["total"]
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


def _amt(v, colored=False, muted=False):
    s = ("−" if v < 0 else "") + charts.fmt_wan(abs(v)) + "万"
    cls = "pl-amt"
    if colored:
        cls += " pos" if v >= 0 else " neg"
    return f'<span class="{cls}">{s}</span>'


# ---------- 板块① 基本情况（单周期，4 KPI：值+环比+迷你趋势线）----------
def _spark_cache(P, month_keys):
    """每张卡的迷你趋势线（全年逐月，与所选周期无关）——一次算好、各周期视图共用。"""
    cache = {}
    for _, key, _, _, _, color in KPI_CARDS:
        cache[key] = charts.sparkline([_kpi_val(P[mk], key) for mk in month_keys], color)
    return cache


def render_basic(pkey, P, year, spark_cache):
    p = P[pkey]
    prev = _prev_period_key(pkey, year)
    cards = ""
    for label, key, src, up_good, pctkey, _color in KPI_CARDS:
        val = _kpi_val(p, key)
        vhtml = f'{charts.fmt_wan(val)}<span class="u">万</span>'
        # 环比上期（同粒度）：涨/跌方向配"favorable"上色，成本涨=红、收入涨=绿
        if prev is not None and _kpi_val(P[prev], key):
            pv = _kpi_val(P[prev], key)
            d = (val - pv) / abs(pv) * 100
            good = (d >= 0) == up_good
            arrow = "▲" if d >= 0 else "▼"
            delta = f'<div class="kpi-delta {"up" if good else "down"}">{arrow} {abs(d):.1f}% <span>环比上期</span></div>'
        else:
            delta = '<div class="kpi-delta muted">— 无上期对比</div>'
        # 附加行：税前利润卡显利润率；回款额卡显总回款下单率 + 防误读小字
        sub = ""
        if pctkey:
            sub = f'<div class="kpi-sub">利润率 <b>{p[pctkey]:.1f}%</b></div>'
        if key == "receipts":
            r = p["receipt_order_ratio_pct"]
            rtxt = f'{r:.1f}%' if r is not None else '—'
            sub = (f'<div class="kpi-sub">总回款下单率 <b>{rtxt}</b></div>'
                   f'<div class="kpi-note">{RECEIPT_NOTE}</div>')
        cards += (f'<div class="kpi"><div class="kpi-l">{label}</div>'
                  f'<div class="kpi-cum">{vhtml}</div>{sub}{delta}'
                  f'<div class="kpi-spark">{spark_cache[key]}</div>'
                  f'<div class="kpi-src">{src}</div></div>')
    return f'<div class="kpi-grid">{cards}</div>'


# ---------- 板块②-1 收入毛利趋势（整年，静态）----------
def render_trend(trend, hl):
    return (f'<div class="card"><div class="card-h">收入 · 毛利趋势 <span class="tag">按月 · 柱=收入/成本，线=毛利率</span></div>'
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


def _hbar_rows(rows, prefix):
    """横向条形列表（台账白名单口径分组）+ 每组的抽屉明细块。rows=[(组名,合计,[(细类,金额),...]),...]。
    宽度按最大组归一（服务端算好，前端零运算）；「未分类」灰色沉底。"""
    if rows is None:
        return '<div class="ev-empty">收单台账无「预算归属部门」列（老台账），换新表头台账后自动出现</div>'
    if not rows:
        return '<div class="ev-empty">本期无台账费用</div>'
    ordered = [r for r in rows if r[0] != "未分类"] + [r for r in rows if r[0] == "未分类"]
    mx = max(v for _, v, _ in rows) or 1
    out, details = [], []
    for name, val, fine in ordered:
        key = f"{prefix}:{name}"
        w = max(2.0, val / mx * 100)
        cls = " unfilled" if name == "未分类" else ""
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


def render_expense_views(p, dept_rows, pc_rows):
    """期间费用构成卡：按大类（环形图）｜按部门｜按利润中心 三态切换。口径同一（白名单内含税）。"""
    e = p["expense"]
    tabs = ('<span class="ev-tabs">'
            '<button class="ev-tab on" data-ev="cat">按大类</button>'
            '<button class="ev-tab" data-ev="dept">按部门</button>'
            '<button class="ev-tab" data-ev="pc">按利润中心</button></span>')
    return (f'<div class="card"><div class="card-h">期间费用构成 <span class="tag">合计 {charts.fmt_wan(e["total"])}万</span>{tabs}</div>'
            f'<div class="ev-body">'
            f'<div class="ev-pane" data-ev="cat">{render_donut(p)}</div>'
            f'<div class="ev-pane" data-ev="dept" style="display:none">{_hbar_rows(dept_rows, "dept")}'
            f'<div class="chart-note">按收单台账「预算归属部门」，台账部分小计 {_ledger_subtotal(dept_rows)}（白名单内含税；不含手填人力，故小于卡头合计）；点部门看细类。</div></div>'
            f'<div class="ev-pane" data-ev="pc" style="display:none">{_hbar_rows(pc_rows, "pc")}'
            f'<div class="chart-note">按收单台账「利润归属中心」（语言/数据/游戏/公共），台账部分小计 {_ledger_subtotal(pc_rows)}（口径同左）；点条看细类。</div></div>'
            f'</div></div>')


def render_dept_budget(dept_budget):
    """部门费用预算执行卡（管理员填了部门费用年预算才出现；没填=不渲染，页面与旧版一分不差）。"""
    if not dept_budget or not dept_budget.get("rows"):
        return ""
    rows_html = ""
    for r in dept_budget["rows"]:
        pct = r["pct"]
        if pct is None:
            cls, w, ptxt = "warn", 100.0, "—（预算为0）"
        else:
            cls = "ok" if pct < 80 else ("warn" if pct <= 100 else "over")
            w, ptxt = min(pct, 100.0), f"{pct:.1f}%"
        rows_html += (f'<div class="bud-row"><span class="bud-name">{_esc(r["dept"])}</span>'
                      f'<span class="bud-track"><i class="{cls}" style="width:{w:.1f}%"></i></span>'
                      f'<span class="bud-num">{charts.fmt_wan(r["used"])} / {charts.fmt_wan(r["target"])}万'
                      f' · <b class="{cls}">{ptxt}</b></span></div>')
    return (f'<div class="card" style="margin-top:16px"><div class="card-h">部门费用预算执行 '
            f'<span class="tag">{dept_budget["year"]}年 · 已用/年预算 · 口径：台账白名单内含税·年累计·含特批</span></div>'
            f'<div class="bud-list">{rows_html}</div>'
            f'<div class="chart-note">已用=收单台账按「预算归属部门」年累计；预算在管理员端·手填·年度预算维护（改动留痕）。</div></div>')


# ---------- 板块②-2 管理利润表（点大类→侧边抽屉看构成，主表定高不再顶下方图表）----------
def _row(name, impact, kind, src="", total=False, grand=False):
    cls = "pl-row" + (" total grand" if grand else " total" if total else "")
    dot = f'<span class="dot {kind}"></span>' if kind else '<span class="dot none"></span>'
    src_html = f'<span class="src">{src}</span>' if src else ""
    return f'<div class="{cls}">{dot}<div class="pl-name">{name}{src_html}</div>{_amt(impact, colored=(total or grand))}</div>'


def _open_row(cat, name, impact):
    """可点大类行：点击弹出右侧抽屉看构成（不再就地展开、不顶下方图表）。"""
    return (f'<div class="pl-row pl-open" data-cat="{cat}" role="button" tabindex="0">'
            f'<span class="dot none"></span>'
            f'<div class="pl-name">{name}<span class="pl-more">查看构成 ›</span></div>{_amt(impact)}</div>')


def _drow(name, impact, kind, src="", sub=False):
    """抽屉内明细行（始终展开、无需切换）。"""
    cls = "pl-drow" + (" sub" if sub else "")
    dot = f'<span class="dot {kind}"></span>' if kind else '<span class="dot none"></span>'
    src_html = f'<span class="src">{src}</span>' if src else ""
    return f'<div class="{cls}">{dot}<div class="pl-name">{_esc(name)}{src_html}</div>{_amt(impact)}</div>'


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


def render_pl_table(p, fine):
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    # 生产成本手填6项（陆总2026-07-08：别漏"实际内部译员成本"），求和仍在profit.py
    prod_manual = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    # 主表只留一级行；费用大类点开→抽屉看构成
    rows = [_row("收入（不含税）", p["revenue_net"], "system", "智云交付额÷1.06")]
    rows.append(_open_row("cost", "成本（生产成本）", -p["production_cost"]))
    rows.append(_row("毛利", p["gross_profit"], "", total=True))
    rows.append(_open_row("sales", "营销费用", -e["营销费用"]))
    rows.append(_open_row("admin", "管理费用", -e["管理费用"]))
    rows.append(_open_row("fixed", "固定运营费用", -e["固定运营费用"]))
    rows.append(_open_row("rd", "研发费用", -e["研发费用"]))
    rows.append(_open_row("fin", "财务费用", -e["财务费用"]))
    rows.append(_row("附加税费", -p["surtax"], "system", "增值税×12%"))
    rows.append(_row("其他损益", p["other_pl"], "manual", "手填·默认无"))
    rows.append(_row("税前利润", p["pretax_profit"], "", grand=True))

    # 抽屉明细片段（每大类一块，藏起来；点击时 JS 拷进抽屉）
    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system", "智云项目成本")
                  + _drow("减：系统内部译员成本", p["inhouse_cost"], "system", "in-house结算")
                  + "".join(_drow(f"加：{n}", -man[n], "manual", "手填·默认上月") for n in prod_manual))
    details = "".join([
        _detail_block("cost", "成本（生产成本）构成", cost_inner),
        _detail_block("sales", "营销费用构成",
                      _drow("营销人力成本", -man["营销人力成本"], "manual", "手填·默认上月")
                      + _d_ledger("市场费用", led["市场费用"], "台账", fine.get("市场费用"))),
        _detail_block("admin", "管理费用构成",
                      _drow("管理人力成本", -man["管理人力成本"], "manual", "手填·默认上月")
                      + _d_ledger("管理费用", led["管理费用"], "台账", fine.get("管理费用"))),
        _detail_block("fixed", "固定运营费用构成",
                      _d_ledger("固定运营费用明细", led["固定运营费用"], "台账", fine.get("固定运营费用"))),
        _detail_block("rd", "研发费用构成",
                      _drow("研发人力成本", -man["研发人力成本"], "manual", "手填·默认上月")
                      + _d_ledger("技术服务费", led["技术服务费"], "台账", fine.get("技术服务费"))),
        _detail_block("fin", "财务费用构成",
                      _d_ledger("财务费用（台账）", led["财务费用"], "台账", fine.get("财务费用"))
                      + _drow("财务费用补充", -man["财务费用补充"], "manual", "手填·多为银行自动扣")),
    ])
    kinds = ('<div class="kinds"><span class="ktip" data-tip="智云系统自动取数（项目明细/任务/下单/回款）">'
             '<i style="background:var(--kind-system)"></i>智云系统</span>'
             '<span class="ktip" data-tip="财务收单台账取数，可在台账里改">'
             '<i style="background:var(--kind-ledger)"></i>收单台账</span>'
             '<span class="ktip" data-tip="手填与调整表（系统没有的数，财务每月填，不填默认上月）">'
             '<i style="background:var(--kind-manual)"></i>手填与调整表</span>'
             '<span style="margin-left:auto;color:var(--mut2)">点费用大类 → 右侧看构成明细</span></div>')
    return (f'<div class="pl">{"".join(rows)}</div>{kinds}'
            f'<div class="pl-details" hidden>{details}</div>')


# ---------- 板块②-3 回款按月（整年，静态）+ 每月回款下单率线 ----------
def _budget_tag(budget):
    """预算完成标签（卡头）：没填预算 → 空串（页面与无预算时代一分不差）。"""
    if not budget:
        return ""
    parts = []
    for key, name in (("receipt", "回款"), ("order", "下单")):
        b = budget.get(key)
        if b:
            pct = f'{b["pct"]:.1f}%' if b["pct"] is not None else "—"
            parts.append(f'{name}年预算 {charts.fmt_wan(b["target"])}万 · 已完成 <b>{pct}</b>')
    return f'<span class="tag">{"　".join(parts)}</span>' if parts else ""


def render_receipts(receipt_order_monthly, budget=None):
    rb = (budget or {}).get("receipt") if budget else None
    budget_month = (rb["target"] / 12.0) if rb and rb.get("target") else None
    return (f'<div class="card"><div class="card-h">回款情况 <span class="tag">按月 · 柱=到账额，线=每月回款下单率</span>'
            f'{_budget_tag(budget)}</div>'
            f'{charts.receipt_order_chart(receipt_order_monthly, budget_month=budget_month)}'
            f'<div class="chart-note">回款下单率 = 当月回款 ÷ 当月下单；{RECEIPT_NOTE}。</div></div>')


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
    return (f'<div class="card" data-kind="{_esc(kind)}"><div class="card-h">{title} <span class="tag">{tag}</span></div>{body}</div>')


def render_rankings(p):
    rk = p.get("rankings") or {}
    s, e = p.get("range", ("", ""))
    return (f'<div class="grid-3 rk-grid" data-start="{_esc(s)}" data-end="{_esc(e)}">'
            f'{_rank_card("下单 · 按部门", "期内下单额降序 · 智云", rk.get("orders_by_dept"), "orders_by_dept")}'
            f'{_rank_card("下单 · 按销售", "期内下单额降序 · 智云", rk.get("orders_by_sales"), "orders_by_sales")}'
            f'{_rank_card("回款 · 按客户", "期内到账额降序 · 智云", rk.get("receipts_by_customer"), "receipts_by_customer")}'
            f'</div>')


# ---------- 板块③ 收入与毛利结构（确认口径，按客户/销售，随周期切）----------
def _margin_meta(mp):
    """毛利率 meta：None（收入 0）→ 灰显「毛利率 —」。"""
    return f'毛利率 {mp:.0f}%' if mp is not None else "毛利率 —"


def _pname(name):
    """名称 span：悬浮 #tip 显示全名（长名截断也能看全）。data-tip 走 getAttribute+innerHTML
    两层解码→双层转义（铁律10）；title 保留为无 JS 时的原生兜底。"""
    n = _esc(name)
    return f'<span class="ev-name" title="{n}" data-tip="{_esc(n)}">{n}</span>'


def _profit_rank_card(title, tag, rk, dim=""):
    """收入/毛利排名卡：名次 + 名称 + 横条(按收入归一) + 收入 + 毛利率。金额/率均后端算好，前端零运算（铁律2）。
    与板块④排名卡同款行样式；「其余 N 个」点开→ /api/profit_ranking 全量弹窗（dim=customer/sales）。"""
    items = (rk or {}).get("items") or []
    unfilled = (rk or {}).get("unfilled")
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
                        f'<span class="rk-meta">{_margin_meta(it["margin_pct"])}</span></div>')
        others = rk.get("others")
        if others:
            rows.append(f'<div class="ev-row rk-row rk-others pr-more" title="点开看全部{others["names"]}个明细">'
                        f'<span class="rk-no">…</span>'
                        f'<span class="ev-name">其余 {others["names"]} 个 <span class="rk-open">点开看明细 ›</span></span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(others["revenue"])}</span>'
                        f'<span class="rk-meta">{_margin_meta(others["margin_pct"])}</span></div>')
        if unfilled:
            rows.append(f'<div class="ev-row rk-row rk-unfilled"><span class="rk-no">⚠</span>'
                        f'<span class="ev-name" title="源头未填客户/销售，去管理端归类">（未填）</span>'
                        f'<span class="ev-track"></span>'
                        f'<span class="ev-amt">{_rank_amt(unfilled["revenue"])}</span>'
                        f'<span class="rk-meta">{_margin_meta(unfilled["margin_pct"])}</span></div>')
        body = f'<div class="ev-list rk-list">{"".join(rows)}</div>'
    return (f'<div class="card" data-dim="{_esc(dim)}"><div class="card-h">{title} <span class="tag">{tag}</span></div>{body}</div>')


def _conc_tag(rk):
    """卡头标签：确认口径 + 前 k 大占收入%（集中度）。无数据 → 只留口径。"""
    c = (rk or {}).get("conc_pct")
    k = (rk or {}).get("conc_k", 5)
    return f'确认口径 · 前{k}大占收入 {c:.0f}%' if c is not None else "确认口径"


def render_profit_rankings(p):
    pr = p.get("profit_rankings") or {}
    s, e = p.get("range", ("", ""))
    cust, sale = pr.get("revenue_by_customer"), pr.get("revenue_by_sales")
    return (f'<div class="grid-2e pr-grid" data-start="{_esc(s)}" data-end="{_esc(e)}">'
            f'{_profit_rank_card("收入 · 按客户", _conc_tag(cust), cust, "customer")}'
            f'{_profit_rank_card("收入 · 按销售", _conc_tag(sale), sale, "sales")}'
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
  function applyPeriod(key,label){
    if(key===window._curBlk){ // 同周期只更新按钮态
      pbtn.innerHTML=label+' <span class="pbtn-c">▾</span>';
      ppanel.querySelectorAll('.pp-chip').forEach(function(c){c.classList.toggle('on',c.getAttribute('data-key')===key);});
      return;}
    window._curBlk=key;
    pbtn.innerHTML=label+' <span class="pbtn-c">▾</span>';
    ppanel.querySelectorAll('.pp-chip').forEach(function(c){c.classList.toggle('on',c.getAttribute('data-key')===key);});
    var sync=document.getElementById('periodSync');
    function swap(){
      document.querySelectorAll('.pv').forEach(function(x){x.style.display=x.getAttribute('data-blk')===key?'':'none';});
      if(window._syncDailyDates)window._syncDailyDates(key);}
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
   fetch('/export.png?blk='+encodeURIComponent(k)).then(function(r){
     if(!r.ok){return r.text().then(function(t){throw new Error(t||('HTTP '+r.status));});}
     var fn=decodeURIComponent(r.headers.get('X-Filename')||'')||'经营驾驶舱.png';
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
  <div class="card-h">按时间段看 <span class="tag">默认跟顶部周期 · 可改任意起止日查询 · 费用/利润按月仍看上面板块</span>
    <button class="toggle daily-close" id="dailyClose" type="button">返回默认（年）</button></div>
  <div class="daily-bar">
    <input type="date" id="dailyS"> ~ <input type="date" id="dailyE">
    <button class="toggle" id="dailyGo" type="button">查询</button>
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
 var KIND_TITLE={orders_by_dept:'下单 · 按部门',orders_by_sales:'下单 · 按销售',receipts_by_customer:'回款 · 按客户'};
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
 /** 返回默认（年）：清自定义、排名回预渲染全年、顶部切全年、日期回全年。 */
 function restoreYear(){
  range=null;sum.textContent='';
  if(rkCustom){rkCustom.style.display='none';rkCustom.innerHTML='';}
  if(rkGlobal)rkGlobal.style.display='';
  var yk=yearKey(),yl=yearStr()+'年';
  if(window.applyPeriod)window.applyPeriod(yk,yl);
  else{window._curBlk=yk;fillDates(yearRange());}
 }
 document.getElementById('dailyClose').addEventListener('click',restoreYear);
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
    rkCustom.innerHTML='<div class="grid-3 rk-grid" data-start="'+esc(s)+'" data-end="'+esc(e)+'">'+
      rkHtml('orders_by_dept',d.rankings.orders_by_dept,tag)+
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
    # C1'：老板端不放体检徽章/预警 banner（财务自检工具，只留管理员端），但保留一行极淡小字兜底
    # 防"利润悄悄虚高"——未分类费用未计入会让税前利润偏高。金额取 summary 现成的未分类额，不新算。
    faint_note = (f'<div class="faint-note">口径提示：另含 {_wan(unc["amount"])} 待分类费用尚未计入（税前利润略偏高）</div>'
                  if unc["count"] else "")

    month_keys = meta["tab_groups"]["月"]
    spark_cache = _spark_cache(P, month_keys)
    kpi_views = "".join(_pv(k, yk, render_basic(k, P, meta["year"], spark_cache)) for k in all_keys)
    BD = summary.get("expense_by_department", {})
    BP = summary.get("expense_by_profit_center", {})
    donut_views = "".join(_pv(k, yk, render_expense_views(P[k], BD.get(k), BP.get(k))) for k in all_keys)
    pl_views = "".join(_pv(k, yk, render_pl_table(P[k], FT.get(k, {}))) for k in all_keys)
    profit_rank_views = "".join(_pv(k, yk, render_profit_rankings(P[k])) for k in all_keys)
    rank_views = "".join(_pv(k, yk, render_rankings(P[k])) for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]


    body = f"""
{PARTICLES_HTML}
<div class="topbar">{logo}<span class="tb-title">经营<b>驾驶舱</b></span>
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
   <div class="card pl-card"><div class="card-h">管理利润表 <span class="tag">算到税前利润 · 可展开看构成</span></div>{pl_views}</div>
 </div>
 <div class="period-receipts" style="margin-top:16px">{render_receipts(summary['receipt_order_monthly'], summary['meta'].get('budget'))}</div>
 {render_dept_budget(meta.get('dept_budget'))}

 <div class="sec"><span class="sec-n">三</span><span class="sec-t">收入与毛利结构</span></div>
 <div id="profitRankViews">{profit_rank_views}</div>

 <div class="sec"><span class="sec-n">四</span><span class="sec-t">下单与回款排名</span></div>
 {DAILY_HTML}
 <div id="rankViews">{rank_views}</div>
 <div id="rkCustom" style="display:none"></div>
 {faint_note}
 </div>
 <div class="foot">
  经营驾驶舱 · 甲骨易财务部 &nbsp;|&nbsp; 口径：收入=交付额÷1.06；生产成本=系统直接成本−内部译员成本+手填；
  税前利润=毛利−营销−管理−固定运营−研发−财务−附加税费(增值税×12%)+其他损益 &nbsp;|&nbsp;
  收入与毛利结构（按客户/销售）：确认口径按整单交付日期归属；毛利=收入−项目成本（项目直接毛利，未含内部译员/手填调整，故各客户/销售毛利之和与利润表总毛利略有差异）；集中度=前5大客户/销售占期内收入比 &nbsp;|&nbsp;
  数据源：智云项目明细/任务/下单/回款 + 收单台账 + 手填与调整表。
 </div>
</div>
{DRAWER_HTML}
<div id="tip"></div>
<script>{JS}{EXPORT_JS}{DAILY_JS}{PROFIT_JS}{PW_JS}</script>
"""
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>经营驾驶舱</title><style>{theme.get_css()}</style></head><body>{body}</body></html>')


# ---------- BU 分页（迭代 14）：每 BU 一张独立只读页 /bu/{token} ----------
# 口径（陆总 2026-07-12）：完整利润表结构；公共费用暂不分摊（台账费用行标注、不显示成真 0）、
# 手填项待陆总按 BU 填（标注、不显示成真 0）→ 本页税前利润 = 毛利 − 附加税费。
# 严格保密：本函数只吃"已按该 BU 销售名单过滤"的 summary，页面不含其他 BU 任何名字与数字（测试守卫）。

def _bu_pending_row(name, note):
    """待补数据行：金额位显示说明文字而非 ¥0（不把"没有数"显示成"数是 0"）。"""
    return (f'<div class="pl-row"><span class="dot none"></span>'
            f'<div class="pl-name">{_esc(name)}<span class="src">{_esc(note)}</span></div>'
            f'<span class="pl-amt" style="color:var(--mut2);font-size:12px">{_esc(note)}</span></div>')


def render_bu_pl_table(p, alloc_meta=None):
    """BU 版利润表：结构与全公司版一致（全口径）。
    分摊关：公共费用/手填项标注待补、不出 ¥0 假数。
    分摊开：5 类公共费用显示按比例分摊额（服务端已算好），手填仍待补。"""
    alloc = alloc_meta or {}
    on = bool(alloc.get("enabled"))
    rdisp = _esc(alloc.get("ratio_disp") or "")
    rows = [_row("收入（不含税）", p["revenue_net"], "system", "智云交付额÷1.06")]
    rows.append(_open_row("cost", "成本（生产成本·未含手填项）", -p["production_cost"]))
    rows.append(_row("毛利", p["gross_profit"], "", total=True))
    if on:
        exp = p.get("expense") or {}
        for nm in ("营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"):
            rows.append(_row(nm, -float(exp.get(nm) or 0), "ledger",
                             f"公共费用按 {rdisp} 分摊" if rdisp else "公共费用分摊"))
        pretax_label = "税前利润（=毛利−分摊公共−附加税费）"
        kind_tip = f"台账 5 类公共费用按本 BU {rdisp} 从全公司分摊（守恒）"
        kind_label = f"公共费用·按{rdisp}分摊" if rdisp else "公共费用·已分摊"
        tag_note = f"公共费用按 {rdisp} 分摊" if rdisp else "公共费用已分摊"
    else:
        for nm in ("营销费用", "管理费用", "固定运营费用", "研发费用", "财务费用"):
            rows.append(_bu_pending_row(nm, "公共费用·暂不分摊"))
        pretax_label = "税前利润（=毛利−附加税费）"
        kind_tip = "公共费用（台账）暂不分摊到 BU；可在管理端开启分摊比例"
        kind_label = "公共费用·暂不分摊"
        tag_note = "公共费用与手填项待补"
    rows.append(_row("附加税费", -p["surtax"], "system", "增值税×12%"))
    rows.append(_bu_pending_row("其他损益", "待陆总手填"))
    rows.append(_row(pretax_label, p["pretax_profit"], "", grand=True))

    cost_inner = (_drow("系统直接成本", -p["system_direct_cost"], "system", "智云项目成本")
                  + _drow("减：系统内部译员成本", p["inhouse_cost"], "system", "in-house结算")
                  + '<div class="pl-drow sub"><span class="dot none"></span>'
                    '<div class="pl-name">加：PM/VM/实际内部译员/税费损失/技术流量等手填项'
                    '<span class="src">待陆总按 BU 手填·未计入</span></div>'
                    '<span class="pl-amt" style="color:var(--mut2);font-size:12px">待手填</span></div>')
    details = _detail_block("cost", "成本（生产成本）构成", cost_inner)
    kinds = (f'<div class="kinds"><span class="ktip" data-tip="智云系统自动取数，已按本 BU 销售名单过滤">'
             f'<i style="background:var(--kind-system)"></i>智云系统</span>'
             f'<span class="ktip" data-tip="{_esc(kind_tip)}">'
             f'<i style="background:var(--kind-ledger)"></i>{_esc(kind_label)}</span>'
             f'<span class="ktip" data-tip="人力等手填项待陆总按 BU 填；填法确认后开放">'
             f'<i style="background:var(--kind-manual)"></i>手填·待陆总填</span>'
             f'<span style="margin-left:auto;color:var(--mut2)">点成本行 → 右侧看构成</span></div>')
    return (f'<div class="pl">{"".join(rows)}</div>{kinds}'
            f'<div class="pl-details" hidden>{details}</div>', tag_note)


def render_bu_page(bu_name, summary, cfg, logo_b64):
    """单 BU 独立只读页：周期选择（与主页同一套日历面板/预渲染切换）+ BU 利润表 + BU 下单/回款排名。
    不带导出（/export.png 截全公司主页）与按时间段看（/api/daily 是全公司口径出口）——防越权取数。"""
    meta = summary["meta"]; P = summary["periods"]
    yk = meta["year_key"]
    all_keys = ([yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
                + meta["tab_groups"].get("区间", []))
    logo = f'<img class="tb-logo" src="{logo_b64}" alt="logo">' if logo_b64 else ""
    alloc = meta.get("public_allocation") or {"enabled": False}
    pl_parts, tag_note = [], "公共费用与手填项待补"
    for k in all_keys:
        pl_html, tag_note = render_bu_pl_table(P[k], alloc)
        pl_parts.append(_pv(k, yk, pl_html))
    pl_views = "".join(pl_parts)
    rank_views = "".join(_pv(k, yk, render_rankings(P[k])) for k in all_keys)
    name = _esc(bu_name)
    if alloc.get("enabled"):
        rdisp = _esc(alloc.get("ratio_disp") or "")
        faint = (f'仅含 <b>{name}</b> BU 数据（按营销人员归属拆分）；'
                 f'公共费用按 <b>{rdisp}</b> 从全公司台账分摊、人力等手填项待陆总填 → '
                 f'本页税前利润=毛利−分摊公共−附加税费。')
    else:
        faint = (f'仅含 <b>{name}</b> BU 数据（按营销人员归属拆分，销售→BU 映射待陆总确认）；'
                 f'公共费用暂不分摊、人力等手填项待陆总填 → 本页税前利润=毛利−附加税费。')

    body = f"""
{PARTICLES_HTML}
<div class="topbar">{logo}<span class="tb-title">经营<b>驾驶舱</b> · {name}</span>
 <span class="tb-right">
 <a class="bu-back" href="/" title="返回整体看板（也可当刷新）">← 返回整体</a>
 <span class="live"><i></i>实时</span><span class="tb-time">数据更新 {meta['generated_at']}</span>
 <button class="toggle" id="pwBtn" type="button"><span>🔑</span> 密码</button>
 <button class="toggle" id="themeBtn"><span>◑</span> 浅色</button></span></div>
{PW_MODAL_HTML}
<div class="wrap">
 <div class="bu-subnav" role="navigation" aria-label="返回整体">
  <a class="bu-back bu-back-inline" href="/" title="返回整体看板（点一下即回主页/刷新）">← 返回整体</a>
  <span class="bu-subnav-cur">当前 BU · <b>{name}</b></span>
 </div>
 <div class="faint-note" style="margin:8px 0 0">{faint}</div>
 {render_period_bar(summary)}
 <div class="sec"><span class="sec-n">一</span><span class="sec-t">{name} · 管理利润表</span></div>
 <div class="card"><div class="card-h">管理利润表 <span class="tag">全口径结构 · {_esc(tag_note)}</span></div>{pl_views}</div>
 <div class="sec"><span class="sec-n">二</span><span class="sec-t">{name} · 下单与回款排名</span></div>
 <div id="rankViews">{rank_views}</div>
 <div class="foot">
  经营驾驶舱 · {name} BU 分页 &nbsp;|&nbsp; 口径：收入=交付额÷1.06；生产成本=系统直接成本−内部译员成本（手填项待补）；
  附加税费=增值税×12% &nbsp;|&nbsp; 数据源：智云项目明细/任务/下单/回款（按本 BU 销售名单过滤）。
 </div>
</div>
{DRAWER_HTML}
<div id="tip"></div>
<style>.rk-open{{display:none}}</style>
<script>{JS}{PW_JS}</script>
"""
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>经营驾驶舱 · {name}</title><style>{theme.get_css()}</style></head><body>{body}</body></html>')
