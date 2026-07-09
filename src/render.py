#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装经营驾驶舱 HTML（科技风暗色默认 + 浅色切换）。陆总《驾驶舱规则》三段骨架。
全局时间选择器（月/季/年，默认年）驱动 基本情况+利润表+费用构成 一起切；趋势图/回款图是整年时间线。
所有金额 Python 算好，JS 只做主题切换/周期切换/展开折叠/提示定位，不做任何金额运算。"""
from __future__ import annotations

import json

import charts
import export_book
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
    m = int(pkey.split("年")[1].replace("月", ""))
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
    return (f'<div class="card"><div class="card-h">期间费用构成 <span class="tag">五类合计 {charts.fmt_wan(e["total"])}万 · 悬浮看构成</span></div>'
            f'{charts.donut(segs, "期间费用", charts.fmt_wan(e["total"]) + "万", detail=detail)}'
            f'<div class="legend">{legend}</div></div>')


# ---------- 板块②-2 管理利润表（可展开 + 台账下钻细类）----------
def _row(name, impact, kind, src="", total=False, grand=False):
    cls = "pl-row" + (" total grand" if grand else " total" if total else "")
    dot = f'<span class="dot {kind}"></span>' if kind else '<span class="dot none"></span>'
    src_html = f'<span class="src">{src}</span>' if src else ""
    return f'<div class="{cls}">{dot}<div class="pl-name">{name}{src_html}</div>{_amt(impact, colored=(total or grand))}</div>'


def _fine_rows(sub, fine_pairs, limit=8):
    pairs = sorted(fine_pairs or [], key=lambda x: -x[1])
    rows = ""
    for n, a in pairs[:limit]:
        rows += (f'<div class="pl-row child gchild pl-child" data-c="{sub}">'
                 f'<span class="dot none"></span><div class="pl-name">{n}</div>{_amt(-a)}</div>')
    rest = pairs[limit:]
    if rest:
        rows += (f'<div class="pl-row child gchild pl-child" data-c="{sub}"><span class="dot none"></span>'
                 f'<div class="pl-name">其他{len(rest)}项</div>{_amt(-sum(a for _, a in rest))}</div>')
    return rows


def _ledger_leaf(gkey, name, amount, src, fine_pairs):
    """台账费用叶子：本身可再展开到费用明细细类（到'交通费总额'即止）。"""
    sub = f"{gkey}_f"
    if not fine_pairs:
        return (f'<div class="pl-row child pl-child" data-c="{gkey}"><span class="dot ledger"></span>'
                f'<div class="pl-name">{name}<span class="src">{src}</span></div>{_amt(-amount)}</div>')
    head = (f'<div class="pl-row child parent pl-child" data-c="{gkey}" data-p="{sub}"><span class="dot ledger"></span>'
            f'<div class="pl-name">{name}<span class="src">{src}·点开看明细</span></div>{_amt(-amount)}</div>')
    return head + _fine_rows(sub, fine_pairs)


def _manual_leaf(gkey, name, amount, src):
    return (f'<div class="pl-row child pl-child" data-c="{gkey}"><span class="dot manual"></span>'
            f'<div class="pl-name">{name}<span class="src">{src}</span></div>{_amt(-amount)}</div>')


def _parent(key, name, impact, children_html):
    head = (f'<div class="pl-row parent" data-p="{key}"><span class="dot none"></span>'
            f'<div class="pl-name">{name}</div>{_amt(impact)}</div>')
    return head + children_html


def render_pl_table(p, fine):
    e = p["expense"]; man = p["manual"]; led = p["ledger_expenses"]
    # 生产成本手填6项逐行展示（陆总2026-07-08：不合成一个金额、别漏"实际内部译员成本"），求和仍在profit.py
    prod_manual_names = ["PM人力成本", "VM人力成本", "实际内部译员成本", "税费损失", "技术流量成本", "其他（生产成本）"]
    def _cchild(name, impact, kind, src):
        return (f'<div class="pl-row child pl-child" data-c="cost"><span class="dot {kind}"></span>'
                f'<div class="pl-name">{name}<span class="src">{src}</span></div>{_amt(impact)}</div>')
    rows = [_row("收入（不含税）", p["revenue_net"], "system", "智云交付额÷1.06")]
    rows.append(_parent("cost", "成本（生产成本）", -p["production_cost"],
        _cchild("系统直接成本", -p["system_direct_cost"], "system", "智云项目成本")
        + _cchild("减：系统内部译员成本", p["inhouse_cost"], "system", "in-house结算")
        + "".join(_cchild(f"加：{n}", -man[n], "manual", "手填·默认上月") for n in prod_manual_names)))
    rows.append(_row("毛利", p["gross_profit"], "", total=True))
    rows.append(_parent("sales", "营销费用", -e["营销费用"],
        _manual_leaf("sales", "营销人力成本", man["营销人力成本"], "手填·默认上月")
        + _ledger_leaf("sales", "市场费用", led["市场费用"], "台账", fine.get("市场费用"))))
    rows.append(_parent("admin", "管理费用", -e["管理费用"],
        _manual_leaf("admin", "管理人力成本", man["管理人力成本"], "手填·默认上月")
        + _ledger_leaf("admin", "管理费用", led["管理费用"], "台账", fine.get("管理费用"))))
    rows.append(_parent("fixed", "固定运营费用", -e["固定运营费用"],
        _ledger_leaf("fixed", "固定运营费用明细", led["固定运营费用"], "台账", fine.get("固定运营费用"))))
    rows.append(_parent("rd", "研发费用", -e["研发费用"],
        _manual_leaf("rd", "研发人力成本", man["研发人力成本"], "手填·默认上月")
        + _ledger_leaf("rd", "技术服务费", led["技术服务费"], "台账", fine.get("技术服务费"))))
    rows.append(_parent("fin", "财务费用", -e["财务费用"],
        _ledger_leaf("fin", "财务费用（台账）", led["财务费用"], "台账", fine.get("财务费用"))
        + _manual_leaf("fin", "财务费用补充", man["财务费用补充"], "手填·多为银行自动扣")))
    rows.append(_row("附加税费", -p["surtax"], "system", "收入×6%×12%"))
    rows.append(_row("其他损益", p["other_pl"], "manual", "手填·默认无"))
    rows.append(_row("税前利润", p["pretax_profit"], "", grand=True))
    kinds = ('<div class="kinds"><span class="ktip" data-tip="智云系统自动取数（项目明细/任务/下单/回款）">'
             '<i style="background:var(--kind-system)"></i>智云系统</span>'
             '<span class="ktip" data-tip="财务收单台账取数，可在台账里改">'
             '<i style="background:var(--kind-ledger)"></i>收单台账</span>'
             '<span class="ktip" data-tip="手填与调整表（系统没有的数，财务每月填，不填默认上月）">'
             '<i style="background:var(--kind-manual)"></i>手填与调整表</span>'
             '<span style="margin-left:auto;color:var(--mut2)">点大类展开构成，台账项再点看费用明细</span></div>')
    return f'<div class="pl">{"".join(rows)}</div>{kinds}'


# ---------- 板块②-3 回款按月（整年，静态）+ 每月回款下单率线 ----------
def render_receipts(receipt_order_monthly):
    return (f'<div class="card"><div class="card-h">回款情况 <span class="tag">按月 · 柱=到账额，线=每月回款下单率</span></div>'
            f'{charts.receipt_order_chart(receipt_order_monthly)}'
            f'<div class="chart-note">回款下单率 = 当月回款 ÷ 当月下单；{RECEIPT_NOTE}。</div></div>')


# ---------- 全局周期选择器（下拉菜单）----------
def render_period_bar(summary):
    tg = summary["meta"]["tab_groups"]
    yk = summary["meta"]["year_key"]
    opts = f'<optgroup label="年"><option value="{yk}" selected>{summary["meta"]["year"]}年</option></optgroup>'
    if tg["季度"]:
        opts += ('<optgroup label="季度">'
                 + "".join(f'<option value="{q}">{q.split("年")[1]}</option>' for q in tg["季度"])
                 + '</optgroup>')
    if tg["月"]:
        opts += ('<optgroup label="月">'
                 + "".join(f'<option value="{m}">{m.split("年")[1]}</option>' for m in tg["月"])
                 + '</optgroup>')
    return (f'<div class="pbar"><label class="pbar-l" for="periodSel">看哪段</label>'
            f'<select id="periodSel" class="psel" aria-label="选择周期">{opts}</select></div>')


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
 var psel=document.getElementById('periodSel');
 if(psel){psel.addEventListener('change',function(){var k=psel.value;
   document.querySelectorAll('.pv').forEach(function(x){x.style.display=x.getAttribute('data-blk')===k?'':'none';});});}
 document.addEventListener('click',function(e){var p=e.target.closest('.pl-row.parent');if(!p)return;
   var k=p.getAttribute('data-p'),on=p.classList.toggle('open');
   p.parentNode.querySelectorAll('.pl-child[data-c="'+k+'"]').forEach(function(c){
     c.classList.toggle('on',on);
     if(!on&&c.classList.contains('parent')){c.classList.remove('open');
       var k2=c.getAttribute('data-p');
       p.parentNode.querySelectorAll('.pl-child[data-c="'+k2+'"]').forEach(function(g){g.classList.remove('on');});}});});
 var tip=document.getElementById('tip');
 document.addEventListener('mousemove',function(e){var el=e.target.closest('[data-tip]');
   if(!el){tip.style.opacity=0;return;}tip.innerHTML=el.getAttribute('data-tip');tip.style.opacity=1;
   var x=e.clientX+14,y=e.clientY+14;if(x+tip.offsetWidth>innerWidth)x=e.clientX-tip.offsetWidth-14;
   if(y+tip.offsetHeight>innerHeight)y=e.clientY-tip.offsetHeight-14;tip.style.left=x+'px';tip.style.top=y+'px';});
})();
"""

# 一键导出：点击 → 用户选文件夹（showDirectoryPicker，不支持则回退普通下载）→
# 落一个多 sheet 真·xlsx（纯手写 zip，零外部库、过"自包含"守卫）+ 一份当前 HTML 快照。
# 铁律：每格的值都是 Python 侧算好嵌进 JSON 的，这里只做打包/存盘，不做任何金额运算。
EXPORT_JS = r"""
(function(){
 var btn=document.getElementById('exportBtn'),dataEl=document.getElementById('cockpit-export');
 if(!btn||!dataEl)return;
 var CRC=(function(){var t=[];for(var n=0;n<256;n++){var c=n;for(var k=0;k<8;k++){c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);}t[n]=c>>>0;}return t;})();
 function crc32(b){var c=0xFFFFFFFF;for(var i=0;i<b.length;i++){c=CRC[(c^b[i])&0xFF]^(c>>>8);}return (c^0xFFFFFFFF)>>>0;}
 var enc=new TextEncoder();
 function xe(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
 function col(n){var s='';n++;while(n>0){var m=(n-1)%26;s=String.fromCharCode(65+m)+s;n=Math.floor((n-1)/26);}return s;}
 function isN(v){return typeof v==='number'&&isFinite(v);}
 function sheetXml(sh){
   var o=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
     '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'];
   var all=[sh.columns].concat(sh.rows);
   for(var r=0;r<all.length;r++){var cs=all[r];o.push('<row r="'+(r+1)+'">');
     for(var c=0;c<cs.length;c++){var ref=col(c)+(r+1),v=cs[c];
       if(r>0&&isN(v)){o.push('<c r="'+ref+'"><v>'+v+'</v></c>');}
       else{o.push('<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+xe(v==null?'':v)+'</t></is></c>');}}
     o.push('</row>');}
   o.push('</sheetData></worksheet>');return o.join('');}
 function sName(n,used){n=String(n).replace(/[\\\/\*\?\:\[\]]/g,' ').slice(0,31)||'Sheet';
   var b=n,i=1;while(used[n]){n=b.slice(0,28)+'_'+(i++);}used[n]=1;return n;}
 function buildXlsxBytes(sheets){
   var used={},names=sheets.map(function(s){return sName(s.name,used);}),files=[];
   files.push(['[Content_Types].xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'+
     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+
     '<Default Extension="xml" ContentType="application/xml"/>'+
     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+
     sheets.map(function(s,i){return '<Override PartName="/xl/worksheets/sheet'+(i+1)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';}).join('')+'</Types>']);
   files.push(['_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+
     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>']);
   files.push(['xl/workbook.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
     '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+
     names.map(function(nm,i){return '<sheet name="'+xe(nm)+'" sheetId="'+(i+1)+'" r:id="rId'+(i+1)+'"/>';}).join('')+'</sheets></workbook>']);
   files.push(['xl/_rels/workbook.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+
     sheets.map(function(s,i){return '<Relationship Id="rId'+(i+1)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+(i+1)+'.xml"/>';}).join('')+'</Relationships>']);
   sheets.forEach(function(s,i){files.push(['xl/worksheets/sheet'+(i+1)+'.xml',sheetXml(s)]);});
   return zipBytes(files.map(function(f){return [f[0],enc.encode(f[1])];}),false);}
 // 通用 store 法 zip → Uint8Array。files=[[名字, Uint8Array], ...]；utf8=true 置 UTF-8 文件名标志(中文名必须)。
 // xlsx 本身就是个 zip（装 xml），打包下载兜底也复用它（装 xlsx+html 快照）。
 function zipBytes(files,utf8){
   var flag=utf8?0x0800:0,chunks=[],central=[],offset=0;
   function u16(n){return [n&0xFF,(n>>>8)&0xFF];}
   function u32(n){return [n&0xFF,(n>>>8)&0xFF,(n>>>16)&0xFF,(n>>>24)&0xFF];}
   files.forEach(function(f){
     var nb=enc.encode(f[0]),db=f[1],crc=crc32(db),sz=db.length;
     var loc=[].concat(u32(0x04034b50),u16(20),u16(flag),u16(0),u16(0),u16(0),u32(crc),u32(sz),u32(sz),u16(nb.length),u16(0));
     chunks.push(new Uint8Array(loc),nb,db);
     var cen=[].concat(u32(0x02014b50),u16(20),u16(20),u16(flag),u16(0),u16(0),u16(0),u32(crc),u32(sz),u32(sz),u16(nb.length),u16(0),u16(0),u16(0),u16(0),u32(0),u32(offset));
     central.push({h:new Uint8Array(cen),n:nb});
     offset+=loc.length+nb.length+db.length;});
   var cdStart=offset,cdSize=0;
   central.forEach(function(c){chunks.push(c.h,c.n);cdSize+=c.h.length+c.n.length;});
   var eo=[].concat(u32(0x06054b50),u16(0),u16(0),u16(files.length),u16(files.length),u32(cdSize),u32(cdStart),u16(0));
   chunks.push(new Uint8Array(eo));
   var total=0;chunks.forEach(function(c){total+=c.length;});
   var out=new Uint8Array(total),pos=0;chunks.forEach(function(c){out.set(c,pos);pos+=c.length;});return out;}
 function dl(blob,name){var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;
   document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1500);}
 async function writeInto(dir,name,bytes){var fh=await dir.getFileHandle(name,{create:true});var w=await fh.createWritable();await w.write(bytes);await w.close();}
 function toast(msg){var t=document.createElement('div');t.textContent=msg;
   t.style.cssText='position:fixed;left:50%;bottom:32px;transform:translateX(-50%);background:rgba(20,24,36,.95);color:#fff;padding:10px 18px;border-radius:8px;font-size:14px;z-index:9999;box-shadow:0 6px 24px rgba(0,0,0,.4)';
   document.body.appendChild(t);setTimeout(function(){t.style.transition='opacity .4s';t.style.opacity=0;setTimeout(function(){t.remove();},400);},2400);}
 btn.addEventListener('click',async function(){
   var snap='<!DOCTYPE html>\n'+document.documentElement.outerHTML;
   btn.disabled=true;
   try{
     var data=JSON.parse(dataEl.textContent);
     var stamp=(data.meta&&data.meta.stamp)||'export';
     var xN='经营驾驶舱数据_'+stamp+'.xlsx',hN='经营驾驶舱快照_'+stamp+'.html';
     var xB=buildXlsxBytes(data.sheets),hB=enc.encode(snap);
     if(window.showDirectoryPicker){
       var dir=null;
       try{dir=await window.showDirectoryPicker();}catch(e){if(e&&e.name==='AbortError'){btn.disabled=false;return;}dir=null;}
       if(dir){try{await writeInto(dir,xN,xB);await writeInto(dir,hN,hB);toast('已导出到所选文件夹：Excel + HTML 快照');btn.disabled=false;return;}catch(e2){/* 落到打包下载兜底 */}}}
     // 兜底：两份装进一个 zip 单次下载——单次下载不会被浏览器丢第二个文件
     var bundle=zipBytes([[xN,xB],[hN,hB]],true);
     dl(new Blob([bundle],{type:'application/zip'}),'经营驾驶舱导出_'+stamp+'.zip');
     toast('已下载压缩包：内含 Excel + HTML 快照（解压即用）');
   }catch(err){toast('导出失败：'+((err&&err.message)||err));}
   btn.disabled=false;});
})();
"""


def render_dashboard(summary, cfg, logo_b64):
    meta = summary["meta"]; P = summary["periods"]; FT = summary["expense_fine_type"]
    yk = meta["year_key"]
    all_keys = [yk] + meta["tab_groups"]["季度"] + meta["tab_groups"]["月"]
    logo = f'<img class="tb-logo" src="{logo_b64}" alt="logo">' if logo_b64 else ""
    unc = meta["unclassified"]["expense"]
    # C1'：老板端不放体检徽章/预警 banner（财务自检工具，只留管理员端），但保留一行极淡小字兜底
    # 防"利润悄悄虚高"——未分类费用未计入会让税前利润偏高。金额取 summary 现成的未分类额，不新算。
    faint_note = (f'<div class="faint-note">口径提示：另含 {_wan(unc["amount"])} 待分类费用尚未计入（税前利润略偏高）</div>'
                  if unc["count"] else "")

    month_keys = meta["tab_groups"]["月"]
    spark_cache = _spark_cache(P, month_keys)
    kpi_views = "".join(_pv(k, yk, render_basic(k, P, meta["year"], spark_cache)) for k in all_keys)
    donut_views = "".join(_pv(k, yk, render_donut(P[k])) for k in all_keys)
    pl_views = "".join(_pv(k, yk, render_pl_table(P[k], FT.get(k, {}))) for k in all_keys)
    hl = meta["current_month_label"].split("年")[1]

    # 导出数据（每格已算好）嵌进页面，供前端一键导出；转义 </ 防止提前闭合 <script>
    export_json = json.dumps(export_book.build_export_book(summary, cfg), ensure_ascii=False).replace("</", "<\\/")

    body = f"""
<div class="topbar">{logo}<span class="tb-title">经营<b>驾驶舱</b></span>
 <span class="tb-right"><span class="tb-time">数据更新 {meta['generated_at']}</span>
 <button class="toggle" id="exportBtn"><span>⬇</span> 导出</button>
 <button class="toggle" id="themeBtn"><span>◑</span> 浅色</button></span></div>
<div class="wrap">
 {render_period_bar(summary)}
 <div class="sec"><span class="sec-n">一</span><span class="sec-t">基本情况</span></div>
 {kpi_views}

 <div class="sec"><span class="sec-n">二</span><span class="sec-t">经营利润</span></div>
 <div class="grid-2">
   <div>{render_trend(summary['trend'], hl)}<div style="margin-top:16px">{donut_views}</div></div>
   <div class="card"><div class="card-h">管理利润表 <span class="tag">算到税前利润 · 可展开看构成</span></div>{pl_views}</div>
 </div>
 <div style="margin-top:16px">{render_receipts(summary['receipt_order_monthly'])}</div>
 {faint_note}
 <div class="foot">
  经营驾驶舱 · 甲骨易财务部 &nbsp;|&nbsp; 口径：收入=交付额÷1.06；生产成本=系统直接成本−内部译员成本+手填；
  税前利润=毛利−营销−管理−固定运营−研发−财务−附加税费(收入×6%×12%)+其他损益 &nbsp;|&nbsp;
  数据源：智云项目明细/任务/下单/回款 + 收单台账 + 手填与调整表。
 </div>
</div>
<div id="tip"></div>
<script type="application/json" id="cockpit-export">{export_json}</script>
<script>{JS}{EXPORT_JS}</script>
"""
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>经营驾驶舱</title><style>{theme.get_css()}</style></head><body>{body}</body></html>')
