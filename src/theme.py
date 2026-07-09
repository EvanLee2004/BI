#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题 CSS：科技风暗色(默认) + 浅色可切换。颜色靠 CSS 变量，图表/组件自动跟随。"""


def get_css() -> str:
    return """
:root{
  --bg:#070b16; --panel:rgba(20,28,50,.60); --panel-2:rgba(28,38,66,.70); --panel-solid:#121a30;
  --line:rgba(125,211,252,.14); --line-2:rgba(125,211,252,.22);
  --ink:#e8eefb; --mut:#93a1c0; --mut2:#5f6d92;
  --blue:#22d3ee; --cost:#64769e; --pos:#34d399; --neg:#fb7185; --orange:#fbbf24;
  --purple:#c084fc; --teal:#2dd4bf; --track:rgba(148,163,184,.14);
  --kind-system:#38bdf8; --kind-ledger:#c084fc; --kind-manual:#fbbf24;
  --accent:#22d3ee; --radius:14px;
  --tb:rgba(8,12,24,.72); --glow:0 0 22px rgba(34,211,238,.10);
}
.theme-light{
  --bg:#eef1f5; --panel:#ffffff; --panel-2:#ffffff; --panel-solid:#ffffff;
  --line:#e3e8ef; --line-2:#d5dde8;
  --ink:#233043; --mut:#6b7480; --mut2:#98a1ad;
  --blue:#2E6FAD; --cost:#9aa6b8; --pos:#12805c; --neg:#d1503f; --orange:#d98a2b;
  --purple:#7a5ba8; --teal:#1a9e8f; --track:#eef1f4;
  --kind-system:#2E6FAD; --kind-ledger:#7a5ba8; --kind-manual:#c47d1f;
  --accent:#2E6FAD; --tb:rgba(255,255,255,.85); --glow:0 1px 3px rgba(31,58,95,.08);
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--ink); font-size:14px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(680px 460px at 8% -6%, rgba(34,211,238,.10), transparent 60%),
    radial-gradient(720px 520px at 100% 4%, rgba(192,132,252,.10), transparent 62%),
    radial-gradient(620px 620px at 46% 108%, rgba(45,212,191,.08), transparent 60%);
  background-attachment:fixed; min-height:100vh;
}
.theme-light body,body.theme-light{background-image:none}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 48px}

/* 顶栏 */
.topbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:14px;
  padding:13px 24px;margin:0 0 8px;background:var(--tb);backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line)}
.tb-logo{height:26px;width:auto;border-radius:5px}
.tb-title{font-size:16px;font-weight:600;letter-spacing:.5px}
.tb-title b{color:var(--accent)}
.tb-sub{font-size:11.5px;color:var(--mut2);margin-left:2px}
.tb-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.tb-time{font-size:11.5px;color:var(--mut2)}
.toggle{cursor:pointer;border:1px solid var(--line-2);background:var(--panel);color:var(--mut);
  border-radius:999px;padding:6px 13px;font-size:12px;display:flex;align-items:center;gap:6px;
  font-family:inherit;transition:.2s}
.toggle:hover{color:var(--ink);border-color:var(--accent)}

/* 分区标题 */
.sec{margin:26px 0 12px;display:flex;align-items:baseline;gap:10px}
.sec-n{font-size:12px;font-weight:700;color:var(--accent);border:1px solid var(--line-2);
  border-radius:6px;padding:2px 8px;background:var(--panel)}
.sec-t{font-size:17px;font-weight:600}
.sec-s{font-size:12px;color:var(--mut2);margin-left:auto}

/* 卡片 */
.card{background:var(--panel);backdrop-filter:blur(16px);border:1px solid var(--line);
  border-radius:var(--radius);padding:18px 20px;box-shadow:var(--glow)}
.card-h{font-size:13.5px;font-weight:600;color:var(--ink);margin:0 0 4px;display:flex;align-items:center;gap:8px}
.card-h .tag{font-size:11px;color:var(--mut2);font-weight:400}

/* 基本情况 KPI */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.kpi{background:var(--panel);backdrop-filter:blur(16px);border:1px solid var(--line);
  border-radius:var(--radius);padding:15px 16px;box-shadow:var(--glow);position:relative;overflow:hidden;
  display:flex;flex-direction:column}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent);opacity:.85}
.kpi-l{font-size:12.5px;color:var(--mut);margin-bottom:8px}
.kpi-cum{font-size:26px;font-weight:700;line-height:1.05;letter-spacing:.5px}
.kpi-cum .u{font-size:13px;font-weight:500;color:var(--mut);margin-left:2px}
.kpi-cum-l{font-size:10.5px;color:var(--mut2);margin-bottom:6px}
.kpi-sub{font-size:11.5px;color:var(--mut);margin-top:6px}
.kpi-sub b{color:var(--ink);font-weight:700}
.kpi-note{font-size:10px;color:var(--mut2);margin-top:4px;line-height:1.4}
.kpi-delta{font-size:11.5px;margin-top:7px;font-variant-numeric:tabular-nums;font-weight:600}
.kpi-delta span{color:var(--mut2);font-weight:400;font-size:10.5px;margin-left:2px}
.kpi-delta.up{color:var(--pos)} .kpi-delta.down{color:var(--neg)} .kpi-delta.muted{color:var(--mut2);font-weight:400}
.kpi-spark{margin-top:auto;padding-top:9px}
.kpi-spark .spark{width:100%;height:30px;display:block;opacity:.9}
.kpi-mo{font-size:12px;color:var(--mut);margin-top:8px;padding-top:8px;border-top:1px dashed var(--line)}
.kpi-mo b{color:var(--ink);font-weight:600}
.kpi-src{font-size:10px;color:var(--mut2);margin-top:7px}
.chart-note{font-size:10.5px;color:var(--mut2);margin-top:8px;line-height:1.5}

/* 两栏 */
.grid-2{display:grid;grid-template-columns:1.35fr 1fr;gap:16px;align-items:start}

/* 管理利润表 */
.pl{width:100%}
.pl-row{display:grid;grid-template-columns:14px 1fr auto;align-items:center;gap:10px;
  padding:9px 4px;border-bottom:1px solid var(--line)}
.pl-row .dot{width:8px;height:8px;border-radius:50%}
.dot.system{background:var(--kind-system)} .dot.ledger{background:var(--kind-ledger)}
.dot.manual{background:var(--kind-manual)} .dot.none{background:transparent}
.pl-name{font-size:13.5px;color:var(--ink);display:flex;align-items:center;gap:7px}
.pl-name .src{font-size:10.5px;color:var(--mut2)}
.pl-amt{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums}
.pl-row.total{border-top:1px solid var(--line-2);border-bottom:none}
.pl-row.total .pl-name{font-weight:700;font-size:14.5px}
.pl-row.total .pl-amt{font-size:16px;font-weight:800}
.pl-row.grand{margin-top:4px;background:linear-gradient(90deg,rgba(34,211,238,.08),transparent);
  border-radius:8px;padding:12px 8px}
.pl-row.parent{cursor:pointer}
.pl-row.parent .pl-name::after{content:"›";margin-left:2px;color:var(--mut2);
  transform:rotate(90deg);display:inline-block;transition:.2s;font-size:15px}
.pl-row.parent.open .pl-name::after{transform:rotate(-90deg)}
.pl-child{display:none}
.pl-child.on{display:grid}
.pl-row.child{padding-left:8px;background:var(--track);border-bottom:1px solid transparent}
.pl-row.child .pl-name{font-size:12.5px;color:var(--mut);padding-left:14px}
.pl-row.child .pl-amt{font-size:12.5px;font-weight:500;color:var(--mut)}

/* 图例 kinds */
.kinds{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--mut);margin-top:12px}
.kinds i{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle}

.legend{display:flex;gap:16px;font-size:11.5px;color:var(--mut);margin-top:9px;flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}

/* hbar */
.hbar{display:flex;align-items:center;gap:10px;margin-bottom:9px}
.hbar-n{width:120px;flex:0 0 120px;font-size:12.5px;color:var(--ink);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.hbar-t{flex:1;background:var(--track);border-radius:6px;height:14px;overflow:hidden}
.hbar-f{height:100%;border-radius:6px}
.hbar-v{width:70px;flex:0 0 70px;text-align:right;font-size:12px;color:var(--mut);font-weight:600}

/* banner */
.banner{background:linear-gradient(90deg,rgba(251,191,36,.14),transparent);border:1px solid rgba(251,191,36,.3);
  border-radius:10px;padding:9px 14px;font-size:12.5px;color:var(--ink);margin:10px 0}
.banner b{color:var(--orange)}

/* tooltip */
#tip{position:fixed;z-index:99;pointer-events:none;background:var(--panel-solid);color:var(--ink);
  border:1px solid var(--line-2);border-radius:9px;padding:8px 11px;font-size:12px;line-height:1.55;
  box-shadow:0 8px 30px rgba(0,0,0,.4);opacity:0;transition:opacity .12s;max-width:240px}
.hit,.hit-seg{cursor:pointer}
.ktip{cursor:help}
.hbadge{cursor:help;font-size:11.5px;padding:4px 10px;border-radius:999px;border:1px solid;white-space:nowrap}
.hb-ok{color:var(--pos);border-color:var(--pos);background:rgba(52,211,153,.08)}
.hb-warn{color:var(--orange);border-color:var(--orange);background:rgba(251,191,36,.1)}

/* C1' 极淡小字：老板端不放预警 banner，仅留一行很淡的兜底提示（未分类费用未计入→利润略偏高）*/
.faint-note{margin-top:14px;text-align:center;font-size:11px;color:var(--mut2);opacity:.65}

.foot{margin-top:20px;padding-top:16px;border-top:1px solid var(--line);font-size:11px;color:var(--mut2);line-height:1.7}

/* 全局周期选择器 */
.pbar{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin:4px 0 2px;padding:9px 13px;
  background:var(--panel);backdrop-filter:blur(16px);border:1px solid var(--line);border-radius:12px;box-shadow:var(--glow);
  position:sticky;top:53px;z-index:20}
.pbar-l{font-size:12px;color:var(--mut2);margin-right:4px;display:flex;align-items:center;gap:5px}
.pbar-sep{width:1px;height:15px;background:var(--line-2);margin:0 5px}
.psel{cursor:pointer;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);
  border-radius:8px;padding:6px 30px 6px 12px;font-size:13px;font-family:inherit;font-weight:600;
  transition:.15s;-webkit-appearance:none;appearance:none;
  background-image:linear-gradient(45deg,transparent 50%,var(--mut) 50%),linear-gradient(135deg,var(--mut) 50%,transparent 50%);
  background-position:calc(100% - 15px) 50%,calc(100% - 10px) 50%;background-size:5px 5px,5px 5px;background-repeat:no-repeat}
.psel:hover{border-color:var(--accent)}
.psel:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(34,211,238,.18)}
.psel option,.psel optgroup{background:var(--panel-solid);color:var(--ink)}
.pl-row.gchild .pl-name{padding-left:32px;font-size:12px;color:var(--mut2)}
.pl-row.gchild .pl-name .src{display:none}
.pl-row.gchild .pl-amt{font-size:12px;color:var(--mut2);font-weight:400}
.pl-row.child.parent .pl-name{cursor:pointer}

.pos{color:var(--pos)} .neg{color:var(--neg)}

@media(max-width:900px){
  .kpi-grid{grid-template-columns:repeat(2,1fr)}
  .grid-2{grid-template-columns:1fr}
  .wrap{padding:0 12px 40px}
  .tb-sub{display:none}
  .topbar{padding:10px 12px;flex-wrap:wrap;gap:8px 10px}
  .tb-right{gap:8px}
  .tb-time{display:none}
}
"""
