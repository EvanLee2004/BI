#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网双端服务（FastAPI + uvicorn）。刀3：双端只读上线（尚无编辑，编辑在刀4）。

- 用户端 `/`：无密码，只含汇总（利润驾驶舱 HTML）；**明细数据不进用户端页面、也无明细接口可达**。
- 管理员端 `/admin`：无有效会话 → 密码页；登录后看同一驾驶舱（刀4 加编辑/明细/台账）。
- `/admin/login`：密码（pbkdf2 哈希，存 config 外的本地文件）+ 选身份(明昊/陆总) → 会话 cookie(24h)。
- `/api/detail`：明细数据，**仅会话内可用**（服务端挡，未登录 401；非前端藏）。
- `/api/health`：最近一次运行日志（体检状态条数据源）。

安全实现用标准库（不引 bcrypt/itsdangerous）：口令 pbkdf2_hmac、会话 HMAC 签名 token。
密码/密钥存 数据/管理员密钥.json（绝不进 git）；首次起服务自动生成，默认口令见 README（可用
环境变量 KANBAN_ADMIN_PW 覆盖）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import loaders
import db
import core
import ingest
import render
import assets

COOKIE = "kanban_session"
SESSION_TTL = 24 * 3600
PBKDF2_ITERS = 200_000
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", "kanban2026")
IDENTITIES = ("明昊", "陆总")

# 服务内存态：当前汇总 + 渲染好的两端页面 + 上次规范化的原始记录（供秒级重算）
_state: dict = {"summary": None, "user_html": "", "admin_html": "", "built_at": None, "records": None}
_LOCK = threading.Lock()  # 写库/重算全局互斥（03：写库一把锁，运行中排队）


# ---------------- 密钥文件（口令哈希 + 会话签名密钥） ----------------
def _secret_path(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / "管理员密钥.json"


def _load_or_init_secret(cfg, root=None) -> dict:
    p = _secret_path(cfg, root)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    salt = os.urandom(16)
    sec = {
        "salt": salt.hex(),
        "iters": PBKDF2_ITERS,
        "pw_hash": hashlib.pbkdf2_hmac("sha256", DEFAULT_PW.encode(), salt, PBKDF2_ITERS).hex(),
        "cookie_key": os.urandom(32).hex(),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[server] 已生成管理员密钥文件：{p}（默认口令：{DEFAULT_PW}，可删文件+设 KANBAN_ADMIN_PW 重置）")
    return sec


def _verify_pw(sec: dict, pw: str) -> bool:
    salt = bytes.fromhex(sec["salt"])
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, int(sec["iters"])).hex()
    return hmac.compare_digest(calc, sec["pw_hash"])


# ---------------- 会话 token（HMAC 签名，含过期） ----------------
def _make_token(sec: dict, user: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = f"{user}|{int(now + SESSION_TTL)}".encode()
    b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(bytes.fromhex(sec["cookie_key"]), b64, hashlib.sha256).hexdigest()
    return b64.decode() + "." + sig


def _check_token(sec: dict, token: str, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expect = hmac.new(bytes.fromhex(sec["cookie_key"]), b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        user, exp = base64.urlsafe_b64decode(b64.encode()).decode().split("|")
    except (ValueError, TypeError):
        return None
    if float(exp) < now:
        return None
    return user if user in IDENTITIES else None


# ---------------- 渲染缓存 ----------------
def _publish(cfg, summary, html):
    _state["summary"] = summary
    _state["user_html"] = html
    _state["admin_html"] = _admin_page(html, summary)
    _state["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _do_full(cfg, root, trigger) -> dict:
    today = loaders.pinned_today(cfg)
    summary, html, ing = core.generate(cfg, today, trigger=trigger)
    _state["records"] = ing.get("records")  # 缓存原始记录供秒级重算
    _publish(cfg, summary, html)
    return ing


def _do_recompute(cfg, root) -> None:
    if not _state.get("records"):
        _do_full(cfg, root, "manual")
        return
    today = loaders.pinned_today(cfg)
    conn = db.connect(cfg, root)
    try:
        ingest.reapply(cfg, conn, _state["records"], today)
        summary = core.summary_from_conn(cfg, conn, today)
    finally:
        conn.close()
    html = render.render_dashboard(summary, cfg, assets.load_logo_base64(cfg))
    _publish(cfg, summary, html)


def refresh(cfg, root=None, trigger="manual") -> dict:
    """完整更新（fetch+重读xlsx+重建+重放）+ 渲染两端，刷新缓存。启动与 /api/refresh 用。"""
    with _LOCK:
        return _do_full(cfg, root, trigger)


def recompute(cfg, root=None) -> None:
    """**秒级重算**（保存调整/手填后）：缓存记录重置标准表→重放→重算→重渲染，不读 xlsx。"""
    with _LOCK:
        _do_recompute(cfg, root)


def _admin_page(dash_html: str, summary: dict) -> str:
    """管理员控制台：体检条 + 立即更新 + 明细编辑/手填/可疑单/调整台账 标签页 + 内嵌驾驶舱。"""
    return _ADMIN_CONSOLE


_LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理员登录 · 经营驾驶舱</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#1e293b;padding:32px;border-radius:12px;width:300px;box-shadow:0 8px 30px #0006}}
h1{{font-size:18px;margin:0 0 20px}}label{{font-size:13px;color:#94a3b8}}
input,select{{width:100%;box-sizing:border-box;margin:6px 0 16px;padding:9px;border-radius:7px;
border:1px solid #334155;background:#0f172a;color:#e2e8f0;font-size:14px}}
button{{width:100%;padding:10px;border:0;border-radius:7px;background:#8b5cf6;color:#fff;
font-size:15px;cursor:pointer}}.err{{color:#f87171;font-size:13px;margin-bottom:10px}}</style></head>
<body><form class="card" method="post" action="/admin/login">
<h1>管理员端登录</h1>{err}
<label>身份</label><select name="identity">{opts}</select>
<label>密码</label><input type="password" name="password" autofocus>
<button type="submit">进入</button></form></body></html>"""


def _login_page(err: str = "") -> str:
    opts = "".join(f'<option value="{i}">{i}</option>' for i in IDENTITIES)
    err_html = f'<div class="err">{err}</div>' if err else ""
    return _LOGIN_HTML.format(err=err_html, opts=opts)


_ADMIN_CONSOLE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>管理员控制台 · 经营驾驶舱</title>
<style>
:root{--bg:#0f172a;--panel:#1e293b;--line:#334155;--fg:#e2e8f0;--mut:#94a3b8;--vio:#8b5cf6}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,system-ui,"PingFang SC",sans-serif;background:var(--bg);color:var(--fg)}
#bar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
#bar b{font-size:15px}.pill{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.g{background:#14532d;color:#86efac}.y{background:#713f12;color:#fde68a}.r{background:#7f1d1d;color:#fca5a5}
button{background:var(--vio);color:#fff;border:0;border-radius:7px;padding:6px 12px;font-size:13px;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
button.mini{padding:3px 8px;font-size:12px}button:disabled{opacity:.5;cursor:wait}
a{color:var(--vio)}#tabs{display:flex;gap:4px;flex-wrap:wrap;padding:8px 14px;background:#172033}
.tab{padding:6px 12px;border-radius:7px;cursor:pointer;font-size:13px;color:var(--mut)}
.tab.on{background:var(--vio);color:#fff}.sec{display:none;padding:14px}.sec.on{display:block}
input,select{background:var(--bg);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:6px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}
th,td{border:1px solid var(--line);padding:5px 7px;text-align:left;white-space:nowrap}
th{background:#172033;position:sticky;top:0}tr.exp{background:#3b1d1d}
.wrap{overflow:auto;max-height:70vh}.row-form{margin:6px 0;padding:8px;background:#172033;border-radius:7px}
.muted{color:var(--mut);font-size:12px}iframe{width:100%;height:78vh;border:1px solid var(--line);border-radius:8px;background:#fff}
.note{color:var(--mut);font-size:12px;margin:6px 0}
</style></head><body>
<div id="bar">
  <b>管理员控制台</b>
  <span id="health" class="pill y">体检…</span>
  <button id="btnRefresh" onclick="doRefresh()">立即更新</button>
  <span id="msg" class="muted"></span>
  <span style="margin-left:auto"></span>
  <a href="/admin/logout">退出</a>
</div>
<div id="tabs">
  <div class="tab on" data-t="dash" onclick="showTab('dash')">驾驶舱</div>
  <div class="tab" data-t="detail" onclick="showTab('detail')">明细编辑</div>
  <div class="tab" data-t="manual" onclick="showTab('manual')">手填</div>
  <div class="tab" data-t="suspect" onclick="showTab('suspect')">可疑单</div>
  <div class="tab" data-t="ledger" onclick="showTab('ledger')">调整台账</div>
</div>

<div id="dash" class="sec on"><iframe id="dashFrame" src="/"></iframe>
  <div class="note">改数后此驾驶舱会自动刷新（秒级重算）。</div></div>

<div id="detail" class="sec">
  <div>
    <select id="dTable" onchange="dQuery()">
      <option>收入明细</option><option>下单</option><option>回款</option><option>内部译员</option><option>费用明细</option>
    </select>
    月份<select id="dY"></select><select id="dM"></select>
    搜索<input id="dQ" placeholder="订单号/客户…" size="12">
    <button onclick="dQuery()">查询</button>
    <span id="dInfo" class="muted"></span>
  </div>
  <div class="note">改数=写一条调整记录（重抓不丢）；剔除=软删（可在调整台账撤销）。</div>
  <div class="wrap"><table id="dTbl"></table></div>
</div>

<div id="manual" class="sec">
  月份<select id="mY"></select><select id="mM"></select><button onclick="mLoad()">查询</button>
  <span class="muted">改手填即留痕（manual_历史），当月覆盖。</span>
  <div class="wrap"><table id="mTbl"></table></div>
</div>

<div id="suspect" class="sec">
  <button onclick="sLoad()">刷新待确认</button><span id="sInfo" class="muted"></span>
  <div class="note">可疑单=系统筛出的周期变动/月初1号交付；确认正常或挪月（写调整记录）。</div>
  <div class="wrap"><table id="sTbl"></table></div>
</div>

<div id="ledger" class="sec">
  <button onclick="lLoad()">刷新台账</button><span id="lInfo" class="muted"></span>
  <div class="note">过期疑似（红）= 源头已改、调整未套用，请复核。</div>
  <div class="wrap"><table id="lTbl"></table></div>
</div>

<script>
const ADJ_FIELDS={"收入明细":["整单交付日期","交付额","项目成本"],"下单":["下单日期","下单预估额"],
"回款":["到账日期","到账金额"],"内部译员":["任务提交日期","结算金额"],"费用明细":["含税金额","对应报表大类","业务BU"]};
const STD={"收入明细":"std_收入明细","下单":"std_下单","回款":"std_回款","内部译员":"std_内部译员","费用明细":"std_费用明细"};
const MANUAL_ITEMS=["营销人力成本","管理人力成本","研发人力成本","财务费用补充","PM人力成本","VM人力成本",
"实际内部译员成本","税费损失","技术流量成本","其他（生产成本）","其他损益"];
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function msg(t){document.getElementById("msg").textContent=t||"";}
async function api(path,opts){const r=await fetch(path,Object.assign({credentials:"same-origin"},opts||{}));
  if(r.status===401){location.href="/admin";throw new Error("401");}return r;}
async function jget(p){const r=await api(p);return r.json();}
async function jpost(p,body){const r=await api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));return d;}
function showTab(t){document.querySelectorAll(".tab").forEach(e=>e.classList.toggle("on",e.dataset.t===t));
  document.querySelectorAll(".sec").forEach(e=>e.classList.toggle("on",e.id===t));
  if(t==="suspect")sLoad();if(t==="ledger")lLoad();if(t==="manual")mLoad();if(t==="detail"&&!document.getElementById("dTbl").innerHTML)dQuery();}
function reloadDash(){try{document.getElementById("dashFrame").contentWindow.location.reload();}catch(e){}}
async function loadHealth(){try{const h=await jget("/api/health");const el=document.getElementById("health");
  const c=h.result==="绿"?"g":h.result==="红"?"r":"y";el.className="pill "+c;
  el.textContent="体检 "+(h.result||"?")+" · "+(h.run_time||"")+(h.warnings&&h.warnings.length?(" · "+h.warnings.length+"警"):"");}catch(e){}}
async function doRefresh(){const b=document.getElementById("btnRefresh");b.disabled=true;msg("更新中…");
  try{await jpost("/api/refresh",{});msg("已更新");reloadDash();loadHealth();}catch(e){msg("更新失败:"+e.message);}b.disabled=false;}

// ---- 明细编辑 ----
async function dQuery(){const t=document.getElementById("dTable").value,m=ymVal("dY","dM"),
  q=document.getElementById("dQ").value.trim();let u="/api/detail?table="+encodeURIComponent(t)+"&page_size=50";
  if(m)u+="&month="+encodeURIComponent(m);if(q)u+="&q="+encodeURIComponent(q);
  const d=await jget(u);document.getElementById("dInfo").textContent="共"+d.total+"行（显示前"+d.rows.length+"）";
  const cols=d.columns;let h="<tr>"+cols.map(c=>"<th>"+esc(c)+"</th>").join("")+"<th>操作</th></tr>";
  d.rows.forEach(r=>{const key=r["定位键"];h+="<tr>"+cols.map(c=>"<td>"+esc(r[c])+"</td>").join("")+
    '<td><button class="mini" onclick=\'editRow("'+STD[t]+'","'+encodeURIComponent(key)+'","'+t+'")\'>改</button> '+
    '<button class="mini ghost" onclick=\'removeRow("'+STD[t]+'","'+encodeURIComponent(key)+'")\'>剔除</button></td></tr>';});
  document.getElementById("dTbl").innerHTML=h;}
function editRow(std,keyEnc,tkey){const key=decodeURIComponent(keyEnc);
  const opts=ADJ_FIELDS[tkey].map(f=>"<option>"+f+"</option>").join("");
  const id="ef_"+Math.random().toString(36).slice(2);
  const box=document.createElement("div");box.className="row-form";box.innerHTML=
    "定位键 "+esc(key)+" ｜ 字段<select id='"+id+"_f'>"+opts+"</select> 新值<input id='"+id+"_v' size='12'> "+
    "原因<input id='"+id+"_r' size='14'> <button class='mini' id='"+id+"_s'>保存</button> "+
    "<button class='mini ghost' id='"+id+"_c'>取消</button>";
  document.getElementById("detail").appendChild(box);
  document.getElementById(id+"_c").onclick=()=>box.remove();
  document.getElementById(id+"_s").onclick=async()=>{try{
    await jpost("/api/adjust",{目标表:std,定位键:key,字段:document.getElementById(id+"_f").value,
      新值:document.getElementById(id+"_v").value,原因:document.getElementById(id+"_r").value,类型:"改值"});
    box.remove();msg("已保存调整（秒级重算）");reloadDash();loadHealth();dQuery();}catch(e){alert("保存失败："+e.message);}};}
async function removeRow(std,keyEnc){const key=decodeURIComponent(keyEnc);if(!confirm("剔除该行？（软删，可撤销）"))return;
  try{await jpost("/api/adjust",{目标表:std,定位键:key,字段:"",新值:"",原因:"剔除",类型:"剔除"});
    msg("已剔除");reloadDash();loadHealth();dQuery();}catch(e){alert("失败："+e.message);}}

// ---- 手填 ----
async function mLoad(){const m=ymVal("mY","mM");if(!m){return;}
  const cur=await jget("/api/manual?month="+encodeURIComponent(m));const map={};cur.forEach(x=>map[x["项目"]]=x["金额"]);
  let h="<tr><th>项目</th><th>当前金额</th><th>新值</th><th></th></tr>";
  MANUAL_ITEMS.forEach(it=>{const id="mi_"+MANUAL_ITEMS.indexOf(it);
    h+="<tr><td>"+esc(it)+"</td><td>"+esc(map[it]!=null?map[it]:"（空）")+"</td>"+
    "<td><input id='"+id+"' size='12' value='"+(map[it]!=null?map[it]:"")+"'></td>"+
    "<td><button class='mini' onclick=\"mSave('"+encodeURIComponent(m)+"','"+encodeURIComponent(it)+"','"+id+"')\">保存</button></td></tr>";});
  document.getElementById("mTbl").innerHTML=h;}
async function mSave(mEnc,itEnc,id){const v=document.getElementById(id).value.trim();if(v===""){alert("填金额");return;}
  try{await jpost("/api/manual",{归属月:decodeURIComponent(mEnc),项目:decodeURIComponent(itEnc),金额:parseFloat(v)});
    msg("手填已保存（留痕+重算）");reloadDash();loadHealth();mLoad();}catch(e){alert("失败："+e.message);}}

// ---- 可疑单 ----
async function sLoad(){const d=await jget("/api/suspects");document.getElementById("sInfo").textContent="待确认 "+d.length+" 条";
  let h="<tr><th>规则</th><th>摘要</th><th>目标表</th><th>定位键</th><th>操作</th></tr>";
  d.forEach(s=>{h+="<tr><td>"+esc(s["规则"])+"</td><td>"+esc(s["摘要"])+"</td><td>"+esc(s["目标表"])+"</td><td>"+esc(s["定位键"])+"</td>"+
    "<td><button class='mini' onclick='sResolve("+s.id+",\"正常\")'>确认正常</button> "+
    "<button class='mini ghost' onclick='sAdjust("+s.id+")'>挪月</button></td></tr>";});
  document.getElementById("sTbl").innerHTML=h||"（无）";}
async function sResolve(id,action,ym){try{await jpost("/api/suspects",{id:id,action:action,新归属月:ym});
  msg("已处理");reloadDash();loadHealth();sLoad();}catch(e){alert("失败："+e.message);}}
function sAdjust(id){const ym=prompt("挪到哪个月？填 YYYY-MM");if(!ym)return;sResolve(id,"调整",ym.trim());}

// ---- 调整台账 ----
async function lLoad(){const d=await jget("/api/adjustments");document.getElementById("lInfo").textContent="共 "+d.length+" 条";
  let h="<tr><th>id</th><th>时间</th><th>经手人</th><th>目标表</th><th>字段</th><th>原值→新值</th><th>类型</th><th>状态</th><th></th></tr>";
  d.forEach(a=>{const exp=a["状态"]==="过期疑似";h+="<tr class='"+(exp?"exp":"")+"'><td>"+a.id+"</td><td>"+esc(a["创建时间"])+"</td><td>"+esc(a["经手人"])+
    "</td><td>"+esc(a["目标表"])+"</td><td>"+esc(a["字段"])+"</td><td>"+esc(a["原值"])+" → "+esc(a["新值"])+"</td><td>"+esc(a["类型"])+
    "</td><td>"+esc(a["状态"])+"</td><td>"+(a["状态"]==="已撤销"?"":"<button class='mini ghost' onclick='lRevoke("+a.id+")'>撤销</button>")+"</td></tr>";});
  document.getElementById("lTbl").innerHTML=h;}
async function lRevoke(id){if(!confirm("撤销该调整？"))return;try{await jpost("/api/adjust/"+id+"/revoke",{});
  msg("已撤销");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}

// ---- 年月下拉（数据自2026起，年份随时间自动往后长；2026前不给选）----
function pad2(n){return String(n).padStart(2,"0");}
function ymVal(y,m){const yy=document.getElementById(y).value,mm=document.getElementById(m).value;return (yy&&mm)?(yy+"-"+pad2(mm)):"";}
function fillY(sel,withAll){const top=Math.max(new Date().getFullYear(),2026);let h=withAll?'<option value="">全部年</option>':"";
  for(let y=top;y>=2026;y--)h+="<option value='"+y+"'>"+y+"年</option>";document.getElementById(sel).innerHTML=h;}
function fillM(sel,withAll){let h=withAll?'<option value="">全部月</option>':"";
  for(let m=1;m<=12;m++)h+="<option value='"+m+"'>"+m+"月</option>";document.getElementById(sel).innerHTML=h;}
function initYM(){const d=new Date();
  fillY("mY",false);fillM("mM",false);                                  // 手填：必选、默认当前年月
  document.getElementById("mY").value=String(Math.max(d.getFullYear(),2026));document.getElementById("mM").value=d.getMonth()+1;
  fillY("dY",true);fillM("dM",true);}                                   // 明细筛选：可选、默认全部
initYM();
loadHealth();setInterval(loadHealth,30000);
</script></body></html>"""


# ---------------- FastAPI 应用 ----------------
def create_app(cfg, root=None) -> FastAPI:
    app = FastAPI(title="经营驾驶舱", docs_url=None, redoc_url=None, openapi_url=None)
    sec = _load_or_init_secret(cfg, root)

    def _user(request: Request) -> str | None:
        return _check_token(sec, request.cookies.get(COOKIE, ""))

    @app.get("/", response_class=HTMLResponse)
    def user_page():
        return HTMLResponse(_state["user_html"] or "<h1>数据尚未生成，请稍候刷新</h1>")

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request):
        if _user(request):
            return HTMLResponse(_state["admin_html"] or "<h1>数据尚未生成</h1>")
        return HTMLResponse(_login_page())

    @app.post("/admin/login")
    def admin_login(identity: str = Form(""), password: str = Form("")):
        if identity not in IDENTITIES or not _verify_pw(sec, password):
            return HTMLResponse(_login_page("身份或密码不正确"), status_code=401)
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(COOKIE, _make_token(sec, identity), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        return resp

    @app.get("/admin/logout")
    def admin_logout():
        resp = RedirectResponse("/admin", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/api/detail")
    def api_detail(request: Request, table: str = Query("收入明细"), month: str | None = None,
                   q: str | None = None, page: int = 1, page_size: int = 50):
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        conn = db.connect(cfg, root)
        try:
            try:
                return JSONResponse(db.query_detail(conn, table, month, q, page, page_size))
            except KeyError as e:
                raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()

    @app.get("/api/health")
    def api_health():
        """体检状态条数据源（公开：只给绿/黄/红 + 时间 + 各源行数，不含金额/客户名）。"""
        conn = db.connect(cfg, root)
        try:
            run_log = db.latest_run(conn)
        finally:
            conn.close()
        meta = (_state.get("summary") or {}).get("meta", {})
        health = meta.get("health", {})
        return {
            "result": (run_log or {}).get("结果"),
            "run_time": (run_log or {}).get("时间"),
            "built_at": _state.get("built_at"),
            "sources": health.get("sources", []),
            "warnings": health.get("warnings", []),
        }

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @app.post("/api/refresh")
    def api_refresh(request: Request):
        """立即更新=完整 pipeline（fetch+重读+重建+重放）。运行中互斥，重复点返回进行中。"""
        _require(request)
        if not _LOCK.acquire(blocking=False):
            return JSONResponse({"status": "running", "detail": "更新进行中，请稍候"}, status_code=409)
        try:
            ing = _do_full(cfg, root, "manual")
        finally:
            _LOCK.release()
        return {"status": "ok", "result": ing.get("result"), "built_at": _state["built_at"]}

    @app.post("/api/adjust")
    def api_adjust(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        conn = _conn()
        try:
            aid = db.add_adjustment(conn, user, payload.get("目标表", ""),
                                    payload.get("定位键", ""), payload.get("字段", ""),
                                    payload.get("新值", ""), payload.get("原因", ""),
                                    payload.get("类型", "改值"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "adj_id": aid, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/revoke")
    def api_revoke(request: Request, adj_id: int):
        _require(request)
        conn = _conn()
        try:
            ok = db.revoke_adjustment(conn, adj_id)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok" if ok else "noop", "built_at": _state["built_at"]}

    @app.get("/api/adjustments")
    def api_adjustments(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_adjustments(conn)
        finally:
            conn.close()

    @app.get("/api/manual")
    def api_manual_get(request: Request, month: str | None = None):
        _require(request)
        conn = _conn()
        try:
            return db.get_manual(conn, month)
        finally:
            conn.close()

    @app.post("/api/manual")
    def api_manual_set(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        item = payload.get("项目", "")
        if item not in {it["name"] for it in cfg["manual_items"]}:
            raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
        try:
            金额 = float(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字")
        conn = _conn()
        try:
            db.set_manual(conn, payload.get("归属月", ""), item, 金额, user)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/suspects")
    def api_suspects_get(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_suspects(conn)
        finally:
            conn.close()

    @app.post("/api/suspects")
    def api_suspects_post(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        conn = _conn()
        try:
            res = db.resolve_suspect(conn, int(payload.get("id")), payload.get("action", ""),
                                     user, payload.get("新归属月"))
        except (ValueError, TypeError) as e:
            conn.close()
            raise HTTPException(status_code=400, detail=str(e))
        conn.close()
        recompute(cfg, root)
        return {"status": "ok", **res, "built_at": _state["built_at"]}

    return app


def serve(cfg=None, root=None):
    cfg = cfg or loaders.load_config()
    print("[server] 首次构建页面（跑管道+渲染）……")
    try:
        refresh(cfg, root)
        print(f"[server] 就绪 built_at={_state['built_at']}")
    except Exception as e:  # 数据有问题也让服务起来、页面提示
        print(f"[server] ⚠ 构建失败：{type(e).__name__}: {e}（服务仍启动，修数据后 /api/refresh 或重启）")
    app = create_app(cfg, root)
    import uvicorn
    host, port = cfg.get("server_host", "0.0.0.0"), int(cfg.get("server_port", 8018))
    print(f"[server] 内网服务：用户端 http://<本机IP>:{port}/   管理员端 http://<本机IP>:{port}/admin")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
