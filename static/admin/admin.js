

/* 主题：与驾驶舱共用 cockpit-theme；iframe 同源 localStorage 同步 */
(function(){
  var root=document.documentElement, btn=document.getElementById("themeBtn");
  function apply(l){
    root.classList.toggle("theme-light", !!l);
    document.body&&document.body.classList.toggle("theme-light", !!l);
    if(btn) btn.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';
    // 同步内嵌看板 iframe（同域）
    try{
      var f=document.getElementById("dashFrame");
      if(f&&f.contentWindow){
        f.contentWindow.postMessage({type:"cockpit-theme", theme:l?"light":"dark"}, location.origin);
        try{
          var d=f.contentDocument; if(d){
            d.documentElement.classList.toggle("theme-light", !!l);
            if(d.body) d.body.classList.toggle("theme-light", !!l);
            var b=d.getElementById("themeBtn");
            if(b) b.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';
          }
        }catch(e){}
      }
    }catch(e){}
  }
  function read(){try{return localStorage.getItem("cockpit-theme")==="light";}catch(e){return false;}}
  apply(read());
  if(btn) btn.addEventListener("click", function(){
    var l=!root.classList.contains("theme-light");
    try{localStorage.setItem("cockpit-theme", l?"light":"dark");}catch(e){}
    apply(l);
  });
  window.addEventListener("storage", function(e){
    if(e.key==="cockpit-theme") apply(e.newValue==="light");
  });
})();

let ADJ_FIELDS={};  // R1：可调字段由服务端下发（schema 黑名单制推导），不再前端写死
async function loadAdjFields(){try{ADJ_FIELDS=await jget("/api/adjust_fields");}catch(e){}}
const STD={"收入明细":"std_收入明细","下单":"std_下单","回款":"std_回款","内部译员":"std_内部译员","费用明细":"std_费用明细"};
const MANUAL_ITEMS=__MANUAL_ITEMS__; /* 由 config.manual_items 服务端注入（迭代22修：曾硬编码致新增项不出现在填写页） */
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function msg(t){document.getElementById("msg").textContent=t||"";}
async function api(path,opts){const r=await fetch(path,Object.assign({credentials:"same-origin"},opts||{}));
  if(r.status===401){location.href="/admin";throw new Error("401");}return r;}
async function jget(p){const r=await api(p);return r.json();}
async function jpost(p,body){const r=await api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));return d;}
function showSec(id){document.querySelectorAll(".sec").forEach(e=>e.classList.toggle("on",e.id===id));}
// 未保存离开保护（人工填写 / 业绩目标矩阵）
let _formDirty=0,_budgetDirty=0;
function confirmLeave(){const n=(_formDirty||0)+(_budgetDirty||0);if(!n)return true;return confirm("有 "+n+" 项未保存的修改，确定离开？未保存将丢失。");}
function setDirtyCount(n){_formDirty=n||0;const bar=document.getElementById("saveBar"),c=document.getElementById("dirtyCount");
  if(bar)bar.classList.toggle("on",_formDirty>0);if(c)c.textContent=String(_formDirty);}
function setBudgetDirtyCount(n){_budgetDirty=n||0;const bar=document.getElementById("bSaveBar"),c=document.getElementById("bDirtyCount");
  if(bar)bar.classList.toggle("on",_budgetDirty>0);if(c)c.textContent=String(_budgetDirty);}
function refreshDirtyUI(){let n=0;
  document.querySelectorAll("#mTbl input[data-orig],#aTbl input[data-orig],#dxTbl input[data-orig]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim();
    const orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    const dirty=cur!==orig;el.closest("tr")&&el.closest("tr").classList.toggle("dirty",dirty);if(dirty)n++;});
  setDirtyCount(n);
  refreshBudgetDirtyUI();}
function refreshBudgetDirtyUI(){let n=0;
  document.querySelectorAll("#bMatrix input[data-orig]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim();
    const orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    const dirty=cur!==orig;
    const cell=el.closest("td");if(cell)cell.classList.toggle("dirty",dirty);
    if(dirty)n++;});
  setBudgetDirtyCount(n);
  bUpdateSumTips();}
window.addEventListener("beforeunload",e=>{if((_formDirty||0)+(_budgetDirty||0)>0){e.preventDefault();e.returnValue="";}});
// 顶层四区：看 / 数据调整 / 异常处理 / 设置
function showGroup(g){
  if(!confirmLeave())return;
  document.querySelectorAll(".gtab").forEach(e=>e.classList.toggle("on",e.dataset.g===g));
  document.querySelectorAll(".subgrp").forEach(e=>e.style.display=e.dataset.g===g?"flex":"none");
  if(g==="see")showSec("dash");
  else if(g==="edit")pickTable(curTable);
  else if(g==="review")showReview("overview");
  else if(g==="cfg"){showSec("settings");loadVersion();loadSettings();loadBuCfg();loadAccts();setBindDirty();}}
function reloadDash(){try{document.getElementById("dashFrame").contentWindow.location.reload();}catch(e){}}
function showToast(t,isErr,onclick){const el=document.getElementById("toast");el.textContent=t||"";
  el.className=(isErr===true?"err":(isErr||""))+(onclick?" clickable":"");
  el.onclick=onclick?()=>{el.style.display="none";onclick();}:null;
  el.style.display="block";
  clearTimeout(window._toastT);window._toastT=setTimeout(()=>{el.style.display="none";},onclick?9000:4000);}
function _shortReason(h){const rr=(h.run_reasons||[])[0]||"";
  if(rr)return rr.length>36?rr.slice(0,36)+"…":rr;
  const w=(h.warnings||[])[0]||"";return w?(w.length>36?w.slice(0,36)+"…":w):"";}
function paintFetchBanners(h){
  const box=document.getElementById("fetchBanner");if(!box)return;
  const list=(h&&h.fetch_banners)||[];
  if(!list.length){box.style.display="none";box.innerHTML="";return;}
  box.innerHTML=list.map(b=>'<div class="fb-line">'+esc((b&&b.text)||"")+'</div>').join("");
  box.style.display="block";
}
async function loadHealth(){try{const h=await jget("/api/health");window._health=h;const el=document.getElementById("health");
  paintFetchBanners(h);
  const c=h.result==="绿"?"g":h.result==="红"?"r":"y";el.className="pill "+c;
  const nWarn=(h.warnings&&h.warnings.length)||0;
  let label="体检 "+(h.result||"?");
  if(h.result&&h.result!=="绿"){const s=_shortReason(h);if(s)label+=" · "+s;}
  else if(nWarn)label+=" · "+nWarn+"警";
  el.textContent=label+" ▾";
  if(document.getElementById("hDetail").style.display==="block")renderHealth(h);
  if(typeof buUpdateUnknownPcHint==="function")buUpdateUnknownPcHint();}catch(e){}}
function toggleHealth(){const d=document.getElementById("hDetail");
  if(d.style.display==="block"){d.style.display="none";return;}renderHealth(window._health||{});d.style.display="block";}
function renderHealth(h){h=h||{};const reasons=h.run_reasons||[],warns=h.warnings||[];
  let html="<h4>体检明细 · 运行 "+esc(h.run_time||"?")+"</h4>";
  html+="<div class='grp'><div class='k'>① 管道运行："+esc(h.result||"?")+"</div>";
  html+=reasons.length?("<ul>"+reasons.map(r=>"<li>"+esc(r)+"</li>").join("")+"</ul>")
    :"<div class='ok'>✓ 运行正常（fetch/调整无异常）</div>";
  html+="</div><div class='grp'><div class='k'>② 数据体检："+(warns.length?(warns.length+" 警"):"无")+"</div>";
  html+=warns.length?("<ul>"+warns.map(w=>"<li>"+esc(w)+"</li>").join("")+"</ul>")
    :"<div class='ok'>✓ 无数据质量告警</div>";
  html+="</div><div class='grp'><div class='k'>数据源覆盖</div><div>"+
    (h.sources||[]).map(s=>esc(s.name)+"："+s.rows+"行").join("　")+"</div></div>";
  document.getElementById("hDetail").innerHTML=html;}
// 更新完成后的诚实提示：管道 ok ≠ 全绿——抓数降级/数据体检问题都要报出来，点击跳体检明细
async function refreshResultToast(L){
  const secs=(L&&L.seconds)?("（"+L.seconds+"s）"):"";
  try{await loadHealth();}catch(e){}
  const h=window._health||{};
  const probs=[...(h.run_reasons||[]),...(h.warnings||[])];
  if(h.result==="绿"&&!probs.length){const t="更新成功"+secs;msg(t);showToast("✓ "+t);return;}
  const n=probs.length||1;
  const t="更新完成，但有 "+n+" 个问题"+secs+" · 点击查看";
  msg("更新有误："+(probs[0]||("体检 "+(h.result||"?"))));
  showToast("⚠ "+t,(h.result==="红")?"err":"warn",()=>{
    window.scrollTo({top:0,behavior:"smooth"});
    renderHealth(window._health||{});document.getElementById("hDetail").style.display="block";});}
// 更新数据：后台跑+轮询进度；完成后 toast
let refT0=0;
async function doRefresh(){const b=document.getElementById("btnRefresh");b.disabled=true;
  b.textContent="更新中…";refT0=Date.now();
  try{await jpost("/api/refresh",{});}catch(e){/* 409=已在更新 → 直接跟着轮询 */}
  msg("更新数据中…");pollRefresh();}
async function pollRefresh(){const b=document.getElementById("btnRefresh");
  try{const s=await jget("/api/refresh_status");
    if(s.running){const el=Math.round((Date.now()-refT0)/1000);
      msg("更新数据中… "+el+"s"+(s.zhiyun_auto_fetch?"（含智云在线抓数，约1~2分钟）":""));
      b.textContent="更新中…";setTimeout(pollRefresh,2000);return;}
    b.disabled=false;b.textContent="更新数据";const L=s.last;
    if(L&&L.status==="error"){msg("更新失败："+L.detail);showToast("更新失败："+(L.detail||""),true);}
    else{await refreshResultToast(L);}
    reloadDash();refreshUcBadge();
  }catch(e){b.disabled=false;b.textContent="更新数据";msg("查询更新状态失败:"+e.message);}}
// 设置页
const SRC_MAP=[["下单(智云)","智云在线抓（自动登录，每次更新）"],
  ["回款(智云)","智云在线抓（自动登录，每次更新）"],
  ["项目明细(智云)","智云在线抓（自动登录，每次更新）"],
  ["内部译员·IN-HOUSE(智云)","智云在线抓（当前账号权限不足时自动沿用现有文件·体检黄，待专用账号）"],
  ["收单台账","共享盘自动拉取（部署机内网；不可达沿用本地副本·体检黄）"],
  ["手填与调整","管理员端「数据调整→人工填写」维护，全程留痕"]];
function toggleZyReveal(){const u=document.getElementById("sZyUser"),p=document.getElementById("sZyPwd"),
  e=document.getElementById("sZyEye"),show=u.type==="password";
  u.type=p.type=show?"text":"password";e.textContent=show?"🙈 隐藏":"👁 显示";}
async function loadSettings(){try{const s=await jget("/api/settings");
  schedTimes=(s.schedule_times&&s.schedule_times.length)?s.schedule_times.slice():[s.schedule_time||"09:30"];
  renderSchedTimes();
  document.getElementById("sKeep").value=s.backup_keep_days||30;
  document.getElementById("sZyUser").value=s.zhiyun_username||"";
  document.getElementById("sZyPwd").value=s.zhiyun_password||"";
  const lp=document.getElementById("sLedgerPath");if(lp)lp.value=s.ledger_share_path||"";
  const oss=document.getElementById("sOverallSalary");if(oss)oss.checked=!!s.overall_see_salary;
  const zc=s.zhiyun_conn||{},zt=zc.tables||{};  // 服务器地址+四表ID（生效值=内置默认+本地覆盖）
  const zset=(id,v)=>{const el=document.getElementById(id);if(el)el.value=v||"";};
  zset("sZyUrl",zc.base_url);zset("sTblOrders",zt.orders);zset("sTblReceipts",zt.receipts);
  zset("sTblProject",zt.project_detail);zset("sTblInhouse",zt.inhouse);
  const b=s.backup_stats||{};
  document.getElementById("sBakInfo").textContent="当前备份："+(b.count||0)+" 份，共 "+(b.mb||0)+" MB";
  const rows={};(window._health&&window._health.sources||[]).forEach(x=>rows[x.name]=x.rows);
  document.getElementById("sSrcTbl").innerHTML="<tr><th>数据</th><th>从哪来</th><th>当前行数</th></tr>"+
    SRC_MAP.map(([n,src])=>"<tr><td>"+esc(n)+"</td><td>"+esc(src)+"</td><td>"+
      (rows[n]!=null?rows[n]:"—")+"</td></tr>").join("");
  }catch(e){msg("读取设置失败:"+e.message);}}
// 版本摘要 + 更新日志（日志在右侧抽屉，默认折叠）
function openVerDrawer(){const d=document.getElementById("verDrawer");if(!d)return;
  d.classList.add("open");d.setAttribute("aria-hidden","false");}
function closeVerDrawer(){const d=document.getElementById("verDrawer");if(!d)return;
  d.classList.remove("open");d.setAttribute("aria-hidden","true");}
document.addEventListener("keydown",function(e){if(e.key==="Escape")closeVerDrawer();});
async function loadVersion(){try{const v=await jget("/api/version");
  const num="v"+String(v.version||"?").split("-")[0],stage=v.stage||"";  // 去 -beta 预发布后缀只显主号
  const pill=document.getElementById("verPill");if(pill)pill.textContent=num+(stage?" · "+stage:"");
  const nEl=document.getElementById("verNum");if(nEl)nEl.textContent=num;
  const sEl=document.getElementById("verStage");if(sEl){sEl.textContent=stage;sEl.className="stage"+(stage==="正式版"?" live":"");}
  const nx=document.getElementById("verNext");if(nx)nx.textContent=stage==="试运行"?"· 正式上线后升 v1.0":(stage==="公测 Beta"?"· 公测通过后去掉 Beta 升 v1.0 正式版":"");
  const sub=document.getElementById("verSub");if(sub)sub.textContent="按时间倒序（最新在最上面），只讲这版能多干啥；内部开发号另计、不在此显示。";
  const log=document.getElementById("verLog");if(log){const cl=v.changelog||[];
    log.innerHTML=cl.length?cl.map(e=>"<div class='vl'><div class='vl-h'><span class='t'>"+esc(e.title||"")+
      "</span><span class='d'>"+esc(e.date||"")+"</span></div><ul>"+
      (e.items||[]).map(it=>"<li>"+esc(it)+"</li>").join("")+"</ul></div>").join("")
      :"<div class='muted'>暂无更新日志</div>";}
  }catch(e){const pill=document.getElementById("verPill");if(pill)pill.textContent="版本?";}}
// ④一键更新：检查远端有没有新版本 → 一键快进拉取 + 看门狗重启
async function checkUpdate(){const m=document.getElementById("vuMsg"),box=document.getElementById("vuAvail");
  m.textContent="检查中…（联网比对远端）";box.style.display="none";box.innerHTML="";
  try{const d=await jget("/api/update/check");
    if(!d.supported){m.textContent=d.reason||"一键更新不可用";return;}
    if(!d.available){m.textContent="✓ "+(d.reason||"已是最新版本")+(d.local?("（当前 "+esc(d.local)+"）"):"");return;}
    m.textContent="";
    const logs=(d.log||[]).map(s=>"<li>"+esc(s)+"</li>").join("");
    let html="<div class='vu-avail'><div class='vu-h'>🔔 发现新版本 · 落后 "+(d.behind||0)+" 个提交（"+esc(d.local||"")+" → "+esc(d.remote_rev||"")+"）"
      +(d.remote&&d.remote!=="origin"?" <span class='muted'>· 源:"+esc(d.remote)+"</span>":"")+"</div>";
    if(logs)html+="<div class='vu-sub'>更新内容（远端提交）：</div><ul class='vu-log'>"+logs+"</ul>";
    if(d.can_update)html+="<button class='mini' type='button' onclick='applyUpdate()'>一键更新并重启</button>"
      +"<span class='muted' style='margin-left:8px'>拉取新代码后服务自动重启（约 10 秒，页面自动刷新）</span>";
    else html+="<div class='muted' style='color:#fbbf24'>⚠ "+esc(d.reason||"当前不满足自动更新条件，请人工处理")+"</div>";
    html+="</div>";box.innerHTML=html;box.style.display="block";
  }catch(e){m.textContent="检查失败："+e.message;}}
async function applyUpdate(){if(!confirm("确认一键更新？将拉取新代码并重启服务（约 10 秒内不可用）。"))return;
  const box=document.getElementById("vuAvail");
  box.innerHTML="<div class='vu-avail'><div class='vu-h'>更新中…拉取新代码…</div></div>";
  try{const d=await jpost("/api/update/apply",{});
    if(d.ok){box.innerHTML="<div class='vu-avail'><div class='vu-h'>✓ 已拉取 "+esc(d.from||"")+" → "+esc(d.to||"")
      +"，服务重启中…</div><div class='muted'>约 10 秒后自动刷新页面；若没刷新请手动刷新。</div></div>";
      setTimeout(()=>location.reload(),12000);}
    else box.innerHTML="<div class='vu-avail'><div class='muted' style='color:#fbbf24'>未更新："+esc(d.reason||"")+"</div></div>";
  }catch(e){ // 更新成功后服务重启会切断连接→请求可能抛错，按"正在重启"处理
    box.innerHTML="<div class='vu-avail'><div class='vu-h'>更新请求已发出，服务可能正在重启…</div>"
      +"<div class='muted'>约 10 秒后自动刷新页面。</div></div>";
    setTimeout(()=>location.reload(),12000);}}
// ②多次更新时间：可增删多个时间点，各到点各跑一次
let schedTimes=["09:30"];
function renderSchedTimes(){const box=document.getElementById("schedTimes");if(!box)return;
  if(!schedTimes.length)schedTimes=["09:30"];
  box.innerHTML=schedTimes.map((t,i)=>
    "<span class='sched-row'><input type='time' value='"+esc(t)+"' onchange='schedTimes["+i+"]=this.value'>"
    +(schedTimes.length>1?"<button class='ghost mini' type='button' title='删除此时间点' onclick='schedDel("+i+")'>✕</button>":"")
    +"</span>").join("");}
function schedAdd(){const m=document.getElementById("sTimeMsg");
  if(schedTimes.length>=6){m.textContent="最多 6 个时间点";return;}
  m.textContent="";schedTimes.push("12:00");renderSchedTimes();setMark("sched");}
function schedDel(i){if(schedTimes.length<=1)return;schedTimes.splice(i,1);renderSchedTimes();setMark("sched");}
// 设置页统一底部保存：卡片只标脏，保存/放弃都在底部一条（各 save 函数返回 true/false 供汇总）
const setDirty=new Set();
function setMark(k){setDirty.add(k);setBarRender();}
function setBarRender(){const bar=document.getElementById("setSaveBar");if(!bar)return;
  bar.classList.toggle("on",setDirty.size>0);
  const n=document.getElementById("setDirtyN");if(n)n.textContent=setDirty.size;}
function setBindDirty(){if(window._setBound)return;window._setBound=1;
  [["setCardSched","sched"],["setCardBackup","backup"],["setCardZy","zy"],
   ["setCardAcct","acct"],["setCardBu","bu"]].forEach(([id,k])=>{
    const el=document.getElementById(id);if(!el)return;
    ["input","change"].forEach(ev=>el.addEventListener(ev,e=>{
      const t=e.target;// 勾选批量指定/选目标 BU 不是数据改动，不标脏
      if(t&&(t.classList&&t.classList.contains("bu-cb")||t.id==="buPickTo"))return;
      setMark(k);}));});}
async function setSaveAll(){const btn=document.getElementById("btnSetSave");if(!btn)return;
  btn.disabled=true;btn.textContent="保存中…";
  const jobs=[["sched",saveSchedule],["backup",saveBackup],["zy",saveZhiyun],["acct",acctSave],["bu",buSave]];
  let fail=0;
  for(const [k,fn] of jobs){if(!setDirty.has(k))continue;
    let ok=false;try{ok=await fn();}catch(e){ok=false;}
    if(ok!==false)setDirty.delete(k);else fail++;}
  setBarRender();btn.disabled=false;btn.textContent="保存全部设置";
  if(fail)showToast("有 "+fail+" 处设置保存失败，见对应卡片红字",true);
  else showToast("✓ 设置已保存");}
function setDiscard(){setDirty.clear();setBarRender();
  loadSettings();loadAccts();loadBuCfg();showToast("已放弃未保存的设置更改");}
async function saveSchedule(){const m=document.getElementById("sTimeMsg");m.textContent="保存中…";
  const times=schedTimes.map(t=>String(t||"").trim()).filter(Boolean);
  if(!times.length){m.textContent="至少保留一个时间点";return false;}
  try{const d=await jpost("/api/settings",{schedule_times:times});
    if(d.schedule_times&&d.schedule_times.length){schedTimes=d.schedule_times.slice();renderSchedTimes();}
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
async function saveBackup(){const m=document.getElementById("sBakMsg");m.textContent="保存中…";
  try{const d=await jpost("/api/settings",{backup_keep_days:document.getElementById("sKeep").value});
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
async function saveZhiyun(){const m=document.getElementById("sZyMsg");m.textContent="保存中…";
  const p={ledger_share_path:document.getElementById("sLedgerPath").value};  // 台账路径总是提交（含清空）
  const oss=document.getElementById("sOverallSalary");if(oss)p.overall_see_salary=!!oss.checked;
  const u=document.getElementById("sZyUser").value,pw=document.getElementById("sZyPwd").value;
  if(u||pw){p.zhiyun_username=u;p.zhiyun_password=pw;}  // 智云账号两项都填才提交（后端校验不能为空）
  const gv=id=>{const el=document.getElementById(id);return el?el.value.trim():"";};
  if(gv("sZyUrl")){  // 连接配置整组提交（界面预填生效值，没改=后端判无变更不写）
    p.zhiyun_base_url=gv("sZyUrl");
    p.zhiyun_tables={orders:gv("sTblOrders"),receipts:gv("sTblReceipts"),
      project_detail:gv("sTblProject"),inhouse:gv("sTblInhouse")};}
  try{const d=await jpost("/api/settings",p);
    m.textContent=d.note||"已保存";return true;}catch(e){m.textContent="失败："+e.message;return false;}}
// 账号与权限卡
let acctList=[],acctPwShow={};
// 权限类型：管理员 / 整体 / BU（可绑多个）。旧账号权限=单个 BU 名 → 视作 BU 类型、可见BU=[该名]
function _permType(a){const p=a.权限||"";if(p==="管理员")return"管理员";if(p==="整体")return"整体";return"BU";}
function _permCellHtml(i,a){
  const ty=_permType(a);
  const sel='<select onchange="acctSetType('+i+',this.value)">'
    +[["管理员","管理员"],["整体","整体（看全部）"],["BU","按 BU（可多选）"]].map(o=>
      "<option value='"+o[0]+"'"+(o[0]===ty?" selected":"")+">"+esc(o[1])+"</option>").join("")
    +'</select>';
  if(ty!=="BU")return sel;
  const names=buList.map(b=>b.name).filter(Boolean);
  const chosen=new Set(a.可见BU||[]);
  const boxes=names.length?names.map(bn=>
    "<label class='acct-bu'><input type='checkbox'"+(chosen.has(bn)?" checked":"")
    +" data-bn=\""+esc(bn)+"\" onchange=\"acctToggleBu("+i+",this.getAttribute('data-bn'),this.checked)\">"
    +esc(bn)+"</label>").join("")
    :"<span class='muted' style='font-size:11px'>先在下方「BU 数据归属」建 BU</span>";
  const warn=(names.length&&chosen.size===0)?"<span class='muted' style='color:#fbbf24;font-size:11px'>未选=看不到任何页</span>":"";
  return sel+"<div class='acct-bus'>"+boxes+warn+"</div>";}
function acctSetType(i,t){const a=acctList[i];
  if(t==="BU"){a.权限="BU";if(!Array.isArray(a.可见BU))a.可见BU=[];}
  else{a.权限=t;a.可见BU=[];}
  acctRender();}
function acctToggleBu(i,bn,on){const a=acctList[i];a.权限="BU";  // 编辑 BU 集即固化为 BU 类型（旧名迁移）
  const s=new Set(a.可见BU||[]);if(on)s.add(bn);else s.delete(bn);a.可见BU=Array.from(s);}
let ACCT_MASTER="lushasha";  // 服务端 /api/accounts 会回 master_account 覆盖
function _adminCount(){return acctList.filter(a=>(a.权限||"")==="管理员").length;}
/** 总账号：按登录名锁定（与当前权限无关），永久不可删、登录名不可改 */
function _isMaster(a){return String(a.账号||"").trim()===ACCT_MASTER;}
function acctRender(){const t=document.getElementById("acctTbl");
  if(!acctList.length){t.innerHTML="<tr><td class='muted'>暂无账号——点「＋ 加账号」</td></tr>";return;}
  t.innerHTML="<tr><th>账号</th><th>显示名（备注）</th><th>权限</th><th>密码</th><th>最后登录</th><th></th></tr>"+
    acctList.map((a,i)=>{
      const init=!!a.初始密码,show=!!acctPwShow[i],master=_isMaster(a);
      const pw=a.密码==null?"":String(a.密码);
      if(master)a.权限="管理员";
      const delCell=master
        ?"<span class='muted' title='总账号永久不可删除' style='font-size:11px'>总账号</span>"
        :"<button class='ghost mini' type='button' onclick='acctDel("+i+")'>删</button>";
      const acctInput=master
        ?'<input style="width:110px;opacity:.9" value="'+esc(a.账号)+'" readonly title="总账号登录名固定，不可改">'
        :'<input style="width:110px" value="'+esc(a.账号)+'" onchange="acctList['+i+'].账号=this.value">';
      const permCell=master
        ?'<span class="muted" style="display:inline-block;padding:6px 10px;border:1px solid var(--line);border-radius:8px;font-size:12px" title="总账号固定为管理员">管理员</span>'
        :_permCellHtml(i,a);
      return "<tr class='"+(init?"init-pw":"")+"'>"+
        "<td>"+acctInput+"</td>"+
        "<td><input style='width:90px' title='备注：谁用这个号，不影响权限' value=\""+esc(a.显示名||"")+"\" onchange='acctList["+i+"].显示名=this.value'></td>"+
        "<td>"+permCell+"</td>"+
        "<td><input type='"+(show?"text":"password")+"' autocomplete='off' style='width:110px' value=\""+esc(pw)+"\" onchange='acctList["+i+"].密码=this.value;acctList["+i+"].初始密码=false'>"+
        " <button class='ghost mini' type='button' onclick='acctTogglePw("+i+")'>"+(show?"🙈":"👁")+"</button>"+
        (init?" <span title='仍是初始密码' style='color:#fde68a'>⚠初始</span>":"")+"</td>"+
        "<td class='muted'>"+esc(a.最后登录||"—")+"</td>"+
        "<td>"+delCell+"</td></tr>";}).join("");}
function acctTogglePw(i){acctPwShow[i]=!acctPwShow[i];acctRender();}
function acctAdd(){acctList.push({账号:"",显示名:"",权限:"整体",密码:"8888",初始密码:true,最后登录:""});acctRender();setMark("acct");}
function acctDel(i){
  const a=acctList[i];
  if(_isMaster(a)){alert("总账号「"+ACCT_MASTER+"」永久不可删除（即使改成别的权限也不行）。部署机也靠它进管理端。");return;}
  if((a.权限||"")==="管理员"&&_adminCount()<=1){alert("至少保留一个「管理员」权限账号，否则没人能登录管理端");return;}
  if(!confirm("删除该账号？立即失效"))return;
  acctList.splice(i,1);acctRender();}
async function loadAccts(){try{const d=await jget("/api/accounts");acctList=d.accounts||[];
  if(d.master_account)ACCT_MASTER=d.master_account;acctPwShow={};acctRender();}
  catch(e){document.getElementById("acctMsg").textContent="读取失败:"+e.message;}}
async function acctSave(){const m=document.getElementById("acctMsg");m.textContent="保存中…";
  if(!_adminCount()){m.textContent="保存失败：至少保留一个「管理员」权限账号";return false;}
  if(!acctList.some(a=>String(a.账号||"").trim()===ACCT_MASTER)){
    m.textContent="保存失败：总账号「"+ACCT_MASTER+"」不可删除";return false;}
  try{const d=await jpost("/api/accounts",{accounts:acctList});acctList=d.accounts||[];
    if(d.master_account)ACCT_MASTER=d.master_account;acctPwShow={};acctRender();
    m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个）";return true;}
  catch(e){m.textContent="保存失败："+e.message;return false;}}
// BU 数据归属（销售归属·A1）+ 公共费用分摊（迭代17·A2：全空=不分摊，无总开关）
let buList=[], salesPool=[], buPicked=new Set(), buUnassigned={};
function _salesArr(v){if(Array.isArray(v))return v.map(s=>String(s).trim()).filter(Boolean);
  return String(v||"").split(/[、，,;；\n]/).map(s=>s.trim()).filter(Boolean);}
function _claimedSales(){const s=new Set();buList.forEach(b=>_salesArr(b.销售).forEach(x=>s.add(x)));return s;}
function _chipHtml(name,withX){const p=salesPool.find(p=>p.name===name)||{};
  const ref=p.ref_disp?('<span class="c" title="当年下单参考">'+esc(p.ref_disp)+'</span>'):'';
  const x=withX?'<button type="button" class="x" title="移回未归属" data-unassign="1">×</button>':'';
  const ck=buPicked.has(name)?' checked':'';
  return '<span class="bu-chip" draggable="true" data-name="'+esc(name)+'">'
    +'<input type="checkbox" class="bu-cb"'+ck+' data-name="'+esc(name)+'" onchange="buPick(this)" title="勾选后可批量指定 BU">'
    +'<span class="n" title="'+esc(name)+'">'+esc(name)+'</span>'+ref+x+'</span>';}
/** 分摊是否启用：任一比例非空即视为要分摊（保存时全填+合计100%）；全空=不分摊 */
function buAllocEnabledFromList(){
  return buList.some(b=>b.分摊比例!=null&&b.分摊比例!==""&&!isNaN(Number(b.分摊比例)));}
function buRenderAlloc(){const hint=document.getElementById("buAllocLegacy");if(!hint)return;
  // 迭代20：比例改按月（人工填写页）；这里只提示遗留的旧全年比例已停用
  hint.style.display=buAllocEnabledFromList()?"":"none";}
// 批量多选归属（勾选若干人→选目标 BU→应用）
function buPick(cb){const n=cb.getAttribute("data-name");if(cb.checked)buPicked.add(n);else buPicked.delete(n);buRenderBatch();}
function buClearPick(){buPicked.clear();buRender();}
function buRenderBatch(){const bar=document.getElementById("buBatch");if(!bar)return;
  const n=buPicked.size;bar.style.display=n?"flex":"none";
  const c=document.getElementById("buPickN");if(c)c.textContent=n;
  const sel=document.getElementById("buPickTo");if(sel){const cur=sel.value;
    sel.innerHTML='<option value="__pool__">保持未归属</option>'+
      buList.map((b,i)=>'<option value="'+i+'">'+esc(b.name||("BU"+(i+1)))+'</option>').join("");
    if(cur&&Array.from(sel.options).some(o=>o.value===cur))sel.value=cur;}}
function buApplyBatch(){const sel=document.getElementById("buPickTo");if(!sel)return;
  const to=sel.value,names=Array.from(buPicked);if(!names.length)return;
  names.forEach(n=>{buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==n);});   // 先从各 BU 摘掉（一人一 BU）
    if(to!=="__pool__"){const i=+to;if(i>=0&&i<buList.length){const cur=_salesArr(buList[i].销售);
      if(cur.indexOf(n)<0)cur.push(n);buList[i].销售=cur;}}});
  buPicked.clear();buRender();
  const tgt=(to==="__pool__")?"未归属":(buList[+to]&&buList[+to].name)||("BU"+(+to+1));
  document.getElementById("buMsg").textContent="已把 "+names.length+" 人批量指定到「"+tgt+"」——点底部「保存全部设置」生效并重算";}
function buUpdateUnassignedHint(){const el=document.getElementById("buUnassignedHint");if(!el)return;
  const n=(buUnassigned&&buUnassigned.unassigned_count)||0;
  if(!n){el.style.display="none";return;}el.style.display="";
  el.innerHTML="⚠ 未归属销售 <b>"+n+"</b> 人，当年下单合计 <b>"+esc(buUnassigned.unassigned_orders_disp||"")+
    "</b> —— 这部分业务不进任何 BU 页（各 BU 合计小于全公司）。归属后点保存即计入。<span class='muted'>（金额=上次保存后快照，保存后刷新）</span>";}
// 迭代21：台账「利润归属中心」未知名（服务端 warnings 已算好显示串；前端 esc 后展示，零运算）
function buUpdateUnknownPcHint(){const el=document.getElementById("buUnknownPcHint");if(!el)return;
  const warns=((window._health&&window._health.warnings)||[]).filter(function(w){
    return typeof w==="string"&&w.indexOf("利润归属中心")>=0&&w.indexOf("不在 BU 名单")>=0;});
  if(!warns.length){el.style.display="none";el.innerHTML="";return;}
  el.style.display="";
  el.innerHTML="⚠ "+warns.map(function(w){return esc(w);}).join("<br>");}
function _bindDrag(root){if(!root)return;
  root.querySelectorAll(".bu-chip").forEach(ch=>{
    ch.addEventListener("dragstart",e=>{
      if(e.target&&e.target.getAttribute&&e.target.getAttribute("data-unassign")){e.preventDefault();return;}
      e.dataTransfer.setData("text/plain",ch.getAttribute("data-name")||"");
      e.dataTransfer.effectAllowed="move";ch.classList.add("dragging");});
    ch.addEventListener("dragend",()=>ch.classList.remove("dragging"));
    const xb=ch.querySelector("[data-unassign]");
    if(xb)xb.addEventListener("click",e=>{e.preventDefault();e.stopPropagation();
      buMoveToPool(ch.getAttribute("data-name")||"");});});
  root.querySelectorAll("[data-zone]").forEach(z=>{
    z.addEventListener("dragover",e=>{e.preventDefault();e.dataTransfer.dropEffect="move";
      z.classList.add("drag-over");const col=z.closest(".bu-col");if(col)col.classList.add("drag-over");});
    z.addEventListener("dragleave",()=>{z.classList.remove("drag-over");
      const col=z.closest(".bu-col");if(col)col.classList.remove("drag-over");});
    z.addEventListener("drop",e=>{e.preventDefault();z.classList.remove("drag-over");
      const col=z.closest(".bu-col");if(col)col.classList.remove("drag-over");
      const name=(e.dataTransfer.getData("text/plain")||"").trim();if(!name)return;
      const zone=z.getAttribute("data-zone");
      if(zone==="pool")buMoveToPool(name);else if(zone&&zone.indexOf("bu:")===0)buMoveToBu(+zone.slice(3),name);});});}
function buMoveToPool(name){if(!name)return;buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});buRender();setMark("bu");}
function buMoveToBu(i,name){if(!name||i<0||i>=buList.length)return;
  buList.forEach(b=>{b.销售=_salesArr(b.销售).filter(s=>s!==name);});
  const cur=_salesArr(buList[i].销售);if(cur.indexOf(name)<0)cur.push(name);buList[i].销售=cur;buRender();setMark("bu");}
function buRender(){const claimed=_claimedSales();
  // 池：库里有且未归属 + 配置 orphan 已在 claimed 外
  const poolNames=salesPool.map(p=>p.name).filter(n=>!claimed.has(n));
  claimed.forEach(n=>{if(!salesPool.some(p=>p.name===n)){/* assigned-only names stay in cols */}});
  const pool=document.getElementById("buPool");
  if(pool){pool.innerHTML=poolNames.length?poolNames.map(n=>_chipHtml(n,false)).join("")
    :'<div class="bu-empty">暂无未归属销售（库空或已全部分完）</div>';
    const h=document.getElementById("buPoolHint");
    if(h)h.textContent="共 "+salesPool.length+" 人 · 未归属 "+poolNames.length+" · 勾选批量或拖到下方 BU（一人一 BU）";}
  const cols=document.getElementById("buCols");
  if(cols){if(!buList.length){cols.innerHTML='<div class="muted" style="padding:8px">未配置 BU（功能关闭）——点「＋ 加一个 BU」</div>';}
    else{cols.innerHTML=buList.map((b,i)=>{
      const sales=_salesArr(b.销售);
      const owner=Array.isArray(b.负责人)?b.负责人.join("、"):String(b.负责人||"");
      return '<div class="bu-col"><div class="bu-col-meta">'
        +'<input placeholder="BU 名" value="'+esc(b.name||"")+'" onchange="buList['+i+'].name=this.value;if(acctList.length)acctRender()">'
        +'<input placeholder="负责人备注（顿号分隔）" value="'+esc(owner)+'" onchange="buList['+i+'].负责人=this.value">'
        +'<div style="display:flex;justify-content:space-between;align-items:center">'
        +'<span class="bu-col-title muted">销售 '+(sales.length)+' 人</span>'
        +'<button class="ghost mini" type="button" onclick="buDel('+i+')">删 BU</button></div></div>'
        +'<div class="bu-chips" data-zone="bu:'+i+'">'
        +(sales.length?sales.map(n=>_chipHtml(n,true)).join(""):'<div class="bu-empty">拖销售到这里</div>')
        +'</div></div>';}).join("");}}
  _bindDrag(document.getElementById("buBoard"));
  buRenderBatch();buUpdateUnassignedHint();buUpdateUnknownPcHint();buRenderAlloc();
  if(acctList.length)acctRender();}
function buAdd(){buList.push({name:"",负责人:[],销售:[],分摊比例:null});buRender();setMark("bu");}
function buDel(i){if(!confirm("删除该 BU？对应权限账号将无法看到页面；销售回未归属池"))return;
  buList.splice(i,1);buRender();setMark("bu");}
async function loadBuCfg(){try{
  const [d,pool]=await Promise.all([jget("/api/bu_config"),jget("/api/sales_pool").catch(()=>({sales:[]}))]);
  buList=(d.bus||[]).map(b=>({name:b.name,负责人:b.负责人||[],销售:_salesArr(b.销售),
    分摊比例:(b.分摊比例==null||!d.公共费用分摊启用)?null:Number(b.分摊比例)}));
  // 未启用分摊时界面显示全空（与「全空=不分摊」一致）；启用时回填比例
  salesPool=pool.sales||[];buPicked.clear();
  buUnassigned={unassigned_count:pool.unassigned_count||0,unassigned_orders_disp:pool.unassigned_orders_disp||""};
  buRender();}
  catch(e){document.getElementById("buMsg").textContent="读取失败:"+e.message;}}
async function buSave(){const m=document.getElementById("buMsg");m.textContent="保存并重算中…";
  try{// 规范化：全空比例 → 不分摊；有填 → 启用并校验 100%
    const payload=buList.map(b=>({name:b.name,负责人:b.负责人,销售:_salesArr(b.销售),分摊比例:b.分摊比例}));
    const d=await jpost("/api/bu_config",{bus:payload,公共费用分摊启用:buAllocEnabledFromList()});
    buList=(d.bus||[]).map(b=>({name:b.name,负责人:b.负责人||[],销售:_salesArr(b.销售),
      分摊比例:(b.分摊比例==null||!d.公共费用分摊启用)?null:Number(b.分摊比例)}));
    buRender();m.textContent=(d.note||"已保存")+"（共 "+d.count+" 个 BU）";reloadDash();return true;}
  catch(e){m.textContent="保存失败："+e.message;return false;}}

// ---- 明细编辑（无限滚动加载）----
let curTable="收入明细";
// 任务书37·B7：列筛状态 {列名: {q?,in?,min?,max?,from?,to?}}；后端 SQL，前端只拼参数
let colFilters={};
let colMetaMap={}; // name→kind
function filtersQueryParam(){
  const keys=Object.keys(colFilters||{});
  if(!keys.length)return "";
  try{return "&filters="+encodeURIComponent(JSON.stringify(colFilters));}catch(e){return "";}
}
function detailBaseParams(){
  let u="";const m=ymVal("dY","dM"),q=document.getElementById("dQ").value.trim();
  const yEl=document.getElementById("dY");
  if(m)u+="&month="+encodeURIComponent(m);
  else if(yEl&&yEl.value)u+="&year="+encodeURIComponent(yEl.value);
  if(q)u+="&q="+encodeURIComponent(q);
  u+=filtersQueryParam();
  return u;
}
function colFilterActive(col){
  const s=colFilters[col];if(!s)return false;
  if(s.q&&String(s.q).trim())return true;
  if(s.in&&s.in.length)return true;
  if(s.min!=null&&s.min!=="")return true;
  if(s.max!=null&&s.max!=="")return true;
  if(s.from)return true;if(s.to)return true;
  return false;
}
function clearColFilters(){colFilters={};hideColFilterPop();dQuery();}
function hideColFilterPop(){
  const p=document.getElementById("colFilterPop");if(!p)return;
  p.style.display="none";p.hidden=true;p.innerHTML="";
}
async function openColFilter(col,anchor){
  const kind=(colMetaMap[col]&&colMetaMap[col].kind)||"text";
  const pop=document.getElementById("colFilterPop");if(!pop)return;
  const cur=colFilters[col]||{};
  let body='<div class="cf-h">筛选 · '+esc(col)+'</div>';
  if(kind==="number"){
    body+='<div class="cf-row"><label>最小（元）</label><input type="number" id="cfMin" step="any" value="'+esc(cur.min??"")+'"></div>';
    body+='<div class="cf-row"><label>最大（元）</label><input type="number" id="cfMax" step="any" value="'+esc(cur.max??"")+'"></div>';
  }else if(kind==="date"){
    body+='<div class="cf-row"><label>起</label><input type="date" id="cfFrom" value="'+esc(cur.from||"")+'"></div>';
    body+='<div class="cf-row"><label>止</label><input type="date" id="cfTo" value="'+esc(cur.to||"")+'"></div>';
  }else{
    body+='<div class="cf-row"><label>含关键词</label><input type="text" id="cfQ" value="'+esc(cur.q||"")+'" placeholder="模糊匹配"></div>';
    body+='<div class="cf-row"><label>去重值多选</label><div class="cf-vals" id="cfVals"><span class="muted">加载中…</span></div></div>';
  }
  body+='<div class="cf-acts"><button type="button" class="ghost mini" id="cfClear">本列清除</button>'+
    '<button type="button" class="mini" id="cfApply">应用</button></div>';
  pop.innerHTML=body;pop.hidden=false;pop.style.display="block";
  const r=anchor.getBoundingClientRect();
  let left=r.left, top=r.bottom+4;
  if(left+260>window.innerWidth)left=Math.max(8,window.innerWidth-280);
  if(top+280>window.innerHeight)top=Math.max(8,r.top-280);
  pop.style.left=left+"px";pop.style.top=top+"px";
  if(kind==="text"){
    try{
      const u="/api/detail/values?table="+encodeURIComponent(curTable)+"&column="+encodeURIComponent(col)+detailBaseParams();
      // 拉去重时去掉本列 in（服务端已做），避免空
      const d=await jget(u);
      const box=document.getElementById("cfVals");
      const picked=new Set((cur.in||[]).map(String));
      if(!d.values||!d.values.length){box.innerHTML='<span class="muted">无候选</span>';}
      else box.innerHTML=d.values.map(v=>{
        const id="cfv_"+Math.random().toString(36).slice(2);
        return '<label><input type="checkbox" value="'+esc(v)+'" '+(picked.has(String(v))?"checked":"")+'> '+
          (v===""?'<i class="muted">(空)</i>':esc(v))+'</label>';
      }).join("");
    }catch(e){const box=document.getElementById("cfVals");if(box)box.innerHTML='<span class="muted">加载失败</span>';}
  }
  document.getElementById("cfClear").onclick=()=>{delete colFilters[col];hideColFilterPop();dQuery();};
  document.getElementById("cfApply").onclick=()=>{
    const next={};
    if(kind==="number"){
      const a=document.getElementById("cfMin").value,b=document.getElementById("cfMax").value;
      if(a!=="")next.min=a;if(b!=="")next.max=b;
    }else if(kind==="date"){
      const a=document.getElementById("cfFrom").value,b=document.getElementById("cfTo").value;
      if(a)next.from=a;if(b)next.to=b;
    }else{
      const qv=(document.getElementById("cfQ").value||"").trim();if(qv)next.q=qv;
      const ins=[...document.querySelectorAll("#cfVals input:checked")].map(el=>el.value);
      if(ins.length)next.in=ins;
    }
    if(Object.keys(next).length)colFilters[col]=next;else delete colFilters[col];
    hideColFilterPop();dQuery();
  };
}
document.addEventListener("click",function(ev){
  const pop=document.getElementById("colFilterPop");
  if(!pop||pop.hidden)return;
  if(pop.contains(ev.target))return;
  if(ev.target.closest&&ev.target.closest("th.col-f"))return;
  hideColFilterPop();
});
const detail={page:0,pages:1,loading:false,loaded:0,
  url(p){return "/api/detail?table="+encodeURIComponent(curTable)+"&page="+p+"&page_size=50"+detailBaseParams();},
  reset(){this.page=0;this.pages=1;this.loaded=0;document.getElementById("dTbl").innerHTML="";
    document.getElementById("dWrap").scrollTop=0;this.next();},
  async next(){if(this.loading||this.page>=this.pages)return;this.loading=true;
    try{const d=await jget(this.url(this.page+1));this.page=d.page;this.pages=d.pages;
      const cols=d.columns,tbl=document.getElementById("dTbl");
      (d.column_meta||[]).forEach(m=>{colMetaMap[m.name]=m;});
      if(this.page===1){
        tbl.innerHTML="<tr>"+cols.map(c=>{
          const on=colFilterActive(c)?" on":"";
          return '<th class="col-f'+on+'" data-col="'+esc(c)+'">'+esc(c)+'<span class="cf-ico">▼</span></th>';
        }).join("")+"<th>操作</th></tr>";
        tbl.querySelectorAll("th.col-f").forEach(th=>{
          th.addEventListener("click",function(e){e.stopPropagation();openColFilter(th.getAttribute("data-col"),th);});
        });
      }
      let h="";d.rows.forEach(r=>{const key=r["定位键"];h+="<tr>"+cols.map(c=>"<td>"+esc(r[c])+"</td>").join("")+
        '<td><button class="mini" onclick=\'editRow("'+STD[curTable]+'","'+encodeURIComponent(key)+'","'+curTable+'")\'>改</button> '+
        '<button class="mini ghost" onclick=\'removeRow("'+STD[curTable]+'","'+encodeURIComponent(key)+'")\'>剔除</button></td></tr>';});
      tbl.insertAdjacentHTML("beforeend",h);this.loaded+=d.rows.length;
      const nF=Object.keys(colFilters).filter(k=>colFilterActive(k)).length;
      document.getElementById("dInfo").textContent="共"+d.total+"行（已载入"+this.loaded+"）"+(nF?" · 列筛"+nF:"");
    }catch(e){msg("查询失败:"+e.message);}this.loading=false;}};
function pickTable(t){if(!confirmLeave())return;curTable=t;colFilters={};colMetaMap={};hideColFilterPop();
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  document.getElementById("dTableName").textContent=t;showSec("detail");detail.reset();}
function showManual(){
  if(document.getElementById("manual")&&!document.getElementById("manual").classList.contains("on")&&!confirmLeave())return;
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on", b.dataset.t==="人工填写"));
  showSec("manual");mLoad();}
function showBudget(){
  if(document.getElementById("budget")&&!document.getElementById("budget").classList.contains("on")&&!confirmLeave())return;
  document.querySelectorAll("#sub-edit .stab").forEach(b=>b.classList.toggle("on", b.dataset.t==="业绩目标"));
  showSec("budget");bLoad();}
function mLoadSafe(){if(!confirmLeave())return;mLoad();}
function bLoadSafe(){if(!confirmLeave())return;bLoad();}
// 千分位：输入过程中即显示 1,234,567；提交时 parseAmount 去逗号
function fmtThousands(v){if(v==null||v==="")return"";const n=String(v).replace(/,/g,"");
  if(n===""||isNaN(Number(n)))return String(v);const parts=n.split(".");
  parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,",");return parts.join(".");}
function parseAmount(v){const s=String(v==null?"":v).replace(/,/g,"").trim();
  if(s===""||isNaN(Number(s)))return NaN;return Number(s);}
function bindThousands(el){if(!el||el._thou)return;el._thou=true;
  // 输入即格式化：保留光标相对「数字位数」的位置，避免跳到末尾
  const reformat=()=>{
    const raw=el.value, caret=el.selectionStart||0;
    const digitsBefore=(raw.slice(0,caret).match(/\d/g)||[]).length;
    const n=parseAmount(raw);
    if(raw.trim()===""||isNaN(n))return;
    // 末尾正在输小数点时暂不格式化，避免 1000. 被吃掉
    if(/[.,]$/.test(raw.replace(/,/g,""))&&!/\.\d+$/.test(raw.replace(/,/g,"")))return;
    const next=fmtThousands(n);
    if(next===raw)return;
    el.value=next;
    let pos=0,seen=0;
    for(let i=0;i<next.length;i++){
      if(/\d/.test(next[i])){seen++;if(seen>=digitsBefore){pos=i+1;break;}}
      pos=i+1;
    }
    try{el.setSelectionRange(pos,pos);}catch(e){}
  };
  el.addEventListener("input",reformat);
  el.addEventListener("blur",()=>{const n=parseAmount(el.value);if(!isNaN(n))el.value=fmtThousands(n);});
}function dQuery(){detail.reset();hideEditDock();}
function hideEditDock(){const d=document.getElementById("editDock");if(d){d.style.display="none";d.innerHTML="";}}
function editRow(std,keyEnc,tkey){const key=decodeURIComponent(keyEnc);
  const fields=ADJ_FIELDS[tkey]||[];
  if(!fields.length){showToast("可调字段未加载，请刷新页面后重试",true);return;}
  // 金额类字段优先排前，方便改交付额/下单额
  const prefer=["交付额","下单预估额","到账金额","结算金额","含税金额","项目成本"];
  const sorted=[...fields].sort((a,b)=>(prefer.indexOf(a)<0?99:prefer.indexOf(a))-(prefer.indexOf(b)<0?99:prefer.indexOf(b)));
  const opts=sorted.map(f=>"<option value='"+esc(f)+"'>"+esc(f)+"</option>").join("");
  const id="ef_"+Math.random().toString(36).slice(2);
  const dock=document.getElementById("editDock");
  dock.style.display="block";
  dock.innerHTML="<b style='color:var(--accent,#a78bfa)'>改数</b> 定位键 <code>"+esc(key)+"</code> ｜ "
    +"字段 <select id='"+id+"_f'>"+opts+"</select> "
    +"新值 <input id='"+id+"_v' size='14' placeholder='数字或文本' autofocus> "
    +"原因 <input id='"+id+"_r' size='14' placeholder='可选'> "
    +"<button class='mini' id='"+id+"_s'>保存</button> "
    +"<button class='mini ghost' id='"+id+"_c'>取消</button>";
  dock.scrollIntoView({behavior:"smooth",block:"nearest"});
  document.getElementById(id+"_c").onclick=()=>hideEditDock();
  document.getElementById(id+"_s").onclick=async()=>{
    const f=document.getElementById(id+"_f").value,v=document.getElementById(id+"_v").value;
    if(v===""){showToast("请填写新值",true);return;}
    const btn=document.getElementById(id+"_s");btn.disabled=true;btn.textContent="保存中…";
    try{
      await jpost("/api/adjust",{目标表:std,定位键:key,字段:f,新值:v,
        原因:document.getElementById(id+"_r").value||"管理端改数",类型:"改值"});
      hideEditDock();showToast("✓ 已保存并重算");msg("已保存调整（秒级重算）");
      reloadDash();loadHealth();refreshUcBadge();dQuery();
    }catch(e){btn.disabled=false;btn.textContent="保存";showToast("保存失败："+e.message,true);alert("保存失败："+e.message);}
  };
  document.getElementById(id+"_v").onkeydown=e=>{if(e.key==="Enter")document.getElementById(id+"_s").click();};
}
async function removeRow(std,keyEnc){const key=decodeURIComponent(keyEnc);if(!confirm("剔除该行？（软删，可撤销）"))return;
  try{await jpost("/api/adjust",{目标表:std,定位键:key,字段:"",新值:"",原因:"剔除",类型:"剔除"});
    showToast("✓ 已剔除");msg("已剔除");reloadDash();loadHealth();refreshUcBadge();dQuery();}catch(e){alert("失败："+e.message);}}
async function exportDetail(){
  try{
    let u="/api/detail_export?table="+encodeURIComponent(curTable)+detailBaseParams();
    const r=await fetch(u);if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||("HTTP "+r.status));
    const blob=await r.blob();const a=document.createElement("a");
    const cd=r.headers.get("Content-Disposition")||"";
    const mfn=cd.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
    const fn=mfn?decodeURIComponent(mfn[1].replace(/"/g,"")):(curTable+"_"+new Date().toISOString().slice(0,10)+".xlsx");
    a.href=URL.createObjectURL(blob);a.download=fn;
    a.click();URL.revokeObjectURL(a.href);showToast("✓ 已导出 Excel（当前筛选，最多 5000 行）");
  }catch(e){showToast("导出失败："+e.message,true);}
}

// ---- 手填 + 业绩目标（批量编辑，底部一次保存）----
// 业绩目标金额：库内存「元」，界面按「万元」编辑（×10000）
function yuanToWan(y){if(y==null||y==="")return"";return Number(y)/10000;}
function wanToYuan(w){return Number(w)*10000;}
async function mFillScopes(){
  const sel=document.getElementById("mScope");if(!sel)return;
  let bus=[];try{const d=await jget("/api/bu_config");bus=(d.bus||[]).map(b=>b.name);}catch(e){}
  const cur=sel.value||"全公司";
  sel.innerHTML='<option value="全公司">全公司</option>'+bus.map(n=>'<option value="'+esc(n)+'">BU · '+esc(n)+'</option>').join("");
  sel.value=[...sel.options].some(o=>o.value===cur)?cur:"全公司";
  sel.onchange=async()=>{if(!confirmLeave()){await mFillScopes();return;}await mLoad();};
}
async function mLoad(){const m=ymVal("mY","mM");if(!m){return;}
  await mFillScopes();
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  const cur=await jget("/api/manual?month="+encodeURIComponent(m)+"&scope="+encodeURIComponent(scope));
  const map={};cur.forEach(x=>map[x["项目"]]=x["金额"]);
  let h="<tr><th>项目</th><th>当前金额(元)</th><th>新值(元)</th></tr>";
  MANUAL_ITEMS.forEach(it=>{const id="mi_"+MANUAL_ITEMS.indexOf(it);
    const disp=map[it]!=null?fmtThousands(map[it]):"";
    const orig=map[it]!=null?String(map[it]):"";
    h+="<tr><td>"+esc(it)+"</td><td>"+esc(map[it]!=null?fmtThousands(map[it]):"（空=0）")+"</td>"+
    "<td><input id='"+id+"' class='amt' data-kind='manual' data-item='"+esc(it)+"' data-orig='"+esc(orig)+"' size='16' value='"+esc(disp)+"' placeholder='如 1,000,000'></td></tr>";});
  document.getElementById("mTbl").innerHTML=h;
  document.querySelectorAll("#mTbl input.amt").forEach(el=>{bindThousands(el);el.addEventListener("input",refreshDirtyUI);el.addEventListener("blur",refreshDirtyUI);});
  await aLoad();await dLoad();refreshDirtyUI();}
// 公共费用分摊比例（按月·迭代20）：范围=全公司才显示；比例%纯前端加总（非金额运算），金额串后端下发
let ALLOC_DATA=null;
async function aLoad(){const blk=document.getElementById("allocBlock");if(!blk)return;
  const m=ymVal("mY","mM");
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  if(scope!=="全公司"||!m){blk.style.display="none";ALLOC_DATA=null;return;}
  try{ALLOC_DATA=await jget("/api/alloc_ratios?month="+encodeURIComponent(m));}
  catch(e){blk.style.display="none";ALLOC_DATA=null;return;}
  const d=ALLOC_DATA;
  if(!d.bus||!d.bus.length){blk.style.display="none";return;}
  blk.style.display="";
  document.getElementById("allocTotal").textContent=d.month_total_disp||"0.00";
  var inh=document.getElementById("allocInherit");
  if(inh)inh.textContent=d.inherited_from?("本月未单独填写，当前沿用 "+d.inherited_from+" 的比例（改动保存后从本月起生效）"):"";
  let h="<tr><th>BU</th><th>本月分摊比例(%)</th></tr>";
  d.bus.forEach((bn,i)=>{const v=(d.ratios&&d.ratios[bn]!=null)?String(d.ratios[bn]):"";
    h+="<tr><td>"+esc(bn)+"</td><td><input id='al_"+i+"' class='amt' data-kind='alloc' data-bu='"+esc(bn)+
      "' data-orig='"+esc(v)+"' size='8' value='"+esc(v)+"' placeholder='未填=沿用上次'></td></tr>";});
  document.getElementById("aTbl").innerHTML=h;
  document.querySelectorAll("#aTbl input.amt").forEach(el=>{
    el.addEventListener("input",()=>{refreshDirtyUI();aSum();});
    el.addEventListener("blur",()=>{refreshDirtyUI();aSum();});});
  aSum();}
function aSum(){const el=document.getElementById("allocSum");if(!el||!ALLOC_DATA)return;
  let sum=0,dirty=false,bad=false;
  document.querySelectorAll("#aTbl input[data-kind=alloc]").forEach(inp=>{
    const cur=String(inp.value).trim();
    if(cur!==String(inp.dataset.orig||"").trim())dirty=true;
    if(cur==="")return;
    const n=Number(cur);if(isNaN(n)||n<0||n>100){bad=true;return;}
    sum+=n;});
  sum=Math.round(sum*10)/10;
  if(bad){el.innerHTML='<span style="color:#fecaca">有比例不是 0~100 的数字</span>';return;}
  if(sum>100.05){el.innerHTML='<span style="color:#fecaca">本月合计 '+sum+'%，超过 100%——保存会被拒绝，请调整（可以小于 100%）</span>';return;}
  const remain=Math.round((100-sum)*10)/10;
  const amt=dirty?"（保存后更新金额）":("约 ¥"+(ALLOC_DATA.remain_amt_disp||"0.00")+" 未分摊");
  el.innerHTML="本月合计 <b>"+sum+"%</b> · 剩余 <b>"+remain+"%</b> 留公司层 "+amt+
    (ALLOC_DATA.orphans&&ALLOC_DATA.orphans.length?('　<span style="color:#fbbf24">另有历史比例含未知 BU：'+esc(ALLOC_DATA.orphans.join("、"))+'（未生效）</span>'):"");}
// 费用去税率（按类别·全局一套·陆总0714）：范围=全公司才显示；税率%纯录入，不做金额运算（铁律2）
let DETAX_DATA=null;
async function dLoad(){const blk=document.getElementById("detaxBlock");if(!blk)return;
  const scope=(document.getElementById("mScope")||{}).value||"全公司";
  if(scope!=="全公司"){blk.style.display="none";DETAX_DATA=null;return;}
  try{DETAX_DATA=await jget("/api/detax_rates");}
  catch(e){blk.style.display="none";DETAX_DATA=null;return;}
  const d=DETAX_DATA;
  if(!d.categories||!d.categories.length){blk.style.display="none";return;}
  blk.style.display="";
  let h="<tr><th>费用类别</th><th>全年含税金额</th><th>去税率(%)</th></tr>";
  d.categories.forEach((c,i)=>{const cat=c.category;
    const v=(d.rates&&d.rates[cat]!=null)?String(d.rates[cat]):"";
    h+="<tr><td>"+esc(cat)+"</td><td class='muted'>"+esc(c.amount_disp||"")+"</td>"+
      "<td><input id='dx_"+i+"' class='amt' data-kind='detax' data-cat='"+esc(cat)+
      "' data-orig='"+esc(v)+"' size='8' value='"+esc(v)+"' placeholder='留空=不去税'></td></tr>";});
  document.getElementById("dxTbl").innerHTML=h;
  document.querySelectorAll("#dxTbl input.amt").forEach(el=>{
    el.addEventListener("input",refreshDirtyUI);el.addEventListener("blur",refreshDirtyUI);});}
// 业绩目标矩阵（金额界面=万元 / 毛利率=百分数；存储键 下单年预算/回款年预算 不变，界面显示「年目标」）
// 矩阵渲染逻辑：bLoad() 写 #bMatrix；列=全公司+ /api/bu_config 业务 BU
/* 任务书37·A6：展示顺序 H1 组在上、年目标在下；存储键 k 不变 */
const BUDGET_METRICS=[
  {k:"下单H1目标",label:"下单H1目标",tip:"万元 · 上半年下单",thou:true,pct:false,wan:true,sumBu:false},
  {k:"回款H1目标",label:"回款H1目标",tip:"万元 · 上半年回款",thou:true,pct:false,wan:true,sumBu:false},
  {k:"毛利率H1目标",label:"毛利率H1目标",tip:"百分数 · 上半年毛利率",thou:false,pct:true,wan:false,sumBu:false},
  {k:"税前利润率H1目标",label:"税前利润率H1目标",tip:"百分数 · 上半年税前利润率",thou:false,pct:true,wan:false,sumBu:false},
  {k:"下单年预算",label:"下单年目标",tip:"万元 · 全年下单",thou:true,pct:false,wan:true,sumBu:true},
  {k:"回款年预算",label:"回款年目标",tip:"万元 · 全年回款",thou:true,pct:false,wan:true,sumBu:true},
  {k:"毛利率年目标",label:"毛利率年目标",tip:"百分数 · 如 35=35%",thou:false,pct:true,wan:false,sumBu:false},
  {k:"税前利润率年目标",label:"税前利润率年目标",tip:"百分数 · 税前利润÷收入",thou:false,pct:true,wan:false,sumBu:false},
];
function bScopesFromBus(bus){return ["全公司"].concat((bus||[]).map(b=>b.name).filter(Boolean));}
function bCellHtml(it,scope,old){
  let curDisp="（未填）",inpDisp="",orig="";
  if(old!=null&&old!==""){
    if(it.pct){curDisp=String(old)+"%";inpDisp=String(old);orig=String(old);}
    else if(it.wan){const w=yuanToWan(old);curDisp=fmtThousands(w)+" 万";inpDisp=fmtThousands(w);orig=String(w);}
    else{curDisp=fmtThousands(old);inpDisp=fmtThousands(old);orig=String(old);}
  }
  const suffix=it.pct?'<span class="pct-suffix">%</span>':(it.wan?'<span class="pct-suffix">万</span>':"");
  return '<div class="b-cur muted">'+esc(curDisp)+'</div>'+
    '<div class="b-edit"><input class="'+(it.thou?"amt":"")+'" data-kind="budget" data-item="'+esc(it.k)+
    '" data-scope="'+esc(scope)+'" data-orig="'+esc(orig)+'" data-pct="'+(it.pct?1:0)+'" data-wan="'+(it.wan?1:0)+
    '" size="10" value="'+esc(inpDisp)+'" placeholder="'+(it.wan?"如 8,000":"如 35")+'">'+suffix+'</div>';
}
async function bLoad(){
  const yEl=document.getElementById("tgY");if(!yEl)return;
  const y=yEl.value;if(!y)return;
  let bus=[];try{const d=await jget("/api/bu_config");bus=d.bus||[];}catch(e){}
  const scopes=bScopesFromBus(bus);
  const cur=await jget("/api/budget?year="+encodeURIComponent(y));
  const map={};
  (cur||[]).forEach(x=>{
    const k=x["指标"];if(!k||k==="费用年预算")return;
    const sc=x["范围"]||"全公司";
    if(!map[k])map[k]={};map[k][sc]=x["金额"];
  });
  let h="<tr><th class='b-metric'>指标</th>";
  scopes.forEach(sc=>{h+="<th>"+esc(sc==="全公司"?"全公司":("BU · "+sc))+"</th>";});
  h+="</tr>";
  BUDGET_METRICS.forEach(it=>{
    h+="<tr data-metric='"+esc(it.k)+"' data-sumbu='"+(it.sumBu?1:0)+"'>";
    h+="<td class='b-metric'><div class='b-lab'>"+esc(it.label)+"</div><div class='muted b-tip'>"+esc(it.tip)+"</div></td>";
    scopes.forEach(sc=>{
      const old=(map[it.k]||{})[sc];
      const sumTip=(it.sumBu&&sc==="全公司")?'<div class="b-sum-tip muted" data-metric="'+esc(it.k)+'"></div>':"";
      h+="<td data-scope='"+esc(sc)+"'>"+bCellHtml(it,sc,old)+sumTip+"</td>";
    });
    h+="</tr>";
  });
  document.getElementById("bMatrix").innerHTML=h;
  document.querySelectorAll("#bMatrix input").forEach(el=>{
    if(el.classList.contains("amt"))bindThousands(el);
    el.addEventListener("input",()=>{refreshBudgetDirtyUI();});
    el.addEventListener("blur",()=>{refreshBudgetDirtyUI();});
  });
  refreshBudgetDirtyUI();}
function bUpdateSumTips(){
  document.querySelectorAll("#bMatrix tr[data-sumbu='1']").forEach(tr=>{
    let buSum=0,has=false;
    tr.querySelectorAll("input[data-kind=budget]").forEach(inp=>{
      if(inp.dataset.scope==="全公司")return;
      const cur=String(inp.value).replace(/,/g,"").trim();
      if(cur==="")return;
      const n=Number(cur);if(isNaN(n))return;
      buSum+=n;has=true;
    });
    const tip=tr.querySelector(".b-sum-tip");if(!tip)return;
    if(!has){tip.textContent="";tip.classList.remove("warn");return;}
    const coInp=tr.querySelector('input[data-scope="全公司"]');
    const coRaw=coInp?String(coInp.value).replace(/,/g,"").trim():"";
    const co=coRaw===""?null:Number(coRaw);
    tip.textContent="各 BU 合计 "+fmtThousands(Math.round(buSum*100)/100)+" 万";
    const over=co!=null&&!isNaN(co)&&buSum>co+1e-9;
    tip.classList.toggle("warn",!!over);
  });}
function discardDirty(){if(!_formDirty)return;if(!confirm("放弃全部未保存修改？"))return;mLoad();}
function bDiscardDirty(){if(!_budgetDirty)return;if(!confirm("放弃业绩目标未保存修改？"))return;bLoad();}
async function budgetSave(){
  const y=(document.getElementById("tgY")||{}).value;
  if(!y){alert("请先选年份");return;}
  const budgets=[];
  document.querySelectorAll("#bMatrix input[data-kind=budget]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim(),orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    if(cur===orig)return;
    if(cur==="")return;
    let n=parseAmount(el.value);if(isNaN(n)){alert("「"+el.dataset.item+" · "+el.dataset.scope+"」数值无效");throw new Error("bad");}
    if(el.dataset.pct==="1"){if(n<0||n>100){alert("「"+el.dataset.item+" · "+el.dataset.scope+"」请填 0~100 的百分数");throw new Error("bad");}}
    else if(n<0){alert("「"+el.dataset.item+" · "+el.dataset.scope+"」不能为负");throw new Error("bad");}
    if(el.dataset.wan==="1"){
      if(n>0&&n<10){if(!confirm("「"+el.dataset.item+" · "+el.dataset.scope+"」="+n+" 万，目标似乎过小（是否单位填错）？仍保存？"))throw new Error("bad");}
      n=wanToYuan(n);
    }
    budgets.push({指标:el.dataset.item,金额:n,范围:el.dataset.scope||"全公司",年份:y});
  });
  if(!budgets.length){showToast("没有需要保存的更改");return;}
  const btn=document.getElementById("btnBudgetSave");btn.disabled=true;btn.textContent="保存中…";
  try{
    await jpost("/api/budget_batch",{items:budgets});
    setBudgetDirtyCount(0);
    showToast("✓ 已保存 "+budgets.length+" 项业绩目标并重算");
    msg("业绩目标已保存（留痕·看板已重算）");
    reloadDash();loadHealth();await bLoad();
  }catch(e){if(e.message!=="bad")alert("保存失败："+e.message);}
  finally{btn.disabled=false;btn.textContent="保存业绩目标";}
}
async function batchSaveAll(){
  const m=ymVal("mY","mM");
  const mScope=(document.getElementById("mScope")||{}).value||"全公司";
  const manuals=[];
  document.querySelectorAll("#mTbl input[data-kind=manual]").forEach(el=>{
    const cur=String(el.value).replace(/,/g,"").trim(),orig=String(el.dataset.orig||"").replace(/,/g,"").trim();
    if(cur===orig)return;
    if(cur==="")return;
    const n=parseAmount(el.value);if(isNaN(n)){alert("「"+el.dataset.item+"」金额无效");throw new Error("bad");}
    if(n<0){alert("「"+el.dataset.item+"」不能为负");throw new Error("bad");}
    manuals.push({项目:el.dataset.item,金额:n,范围:mScope});
  });
  const allocs={};let allocSum=0,allocChanged=0;
  document.querySelectorAll("#aTbl input[data-kind=alloc]").forEach(el=>{
    const cur=String(el.value).trim(),orig=String(el.dataset.orig||"").trim();
    if(cur!==""){const n=Number(cur);
      if(isNaN(n)||n<0||n>100){alert("BU「"+el.dataset.bu+"」比例须为 0~100 的数字");throw new Error("bad");}
      allocSum+=n;}
    if(cur===orig)return;
    allocs[el.dataset.bu]=cur===""?null:Number(cur);allocChanged++;});
  if(allocChanged&&allocSum>100.05){alert("本月各 BU 比例合计 "+Math.round(allocSum*10)/10+"% 超过 100%，请调整（可以小于 100%，剩余留公司层）");throw new Error("bad");}
  const detax={};let detaxChanged=0;
  document.querySelectorAll("#dxTbl input[data-kind=detax]").forEach(el=>{
    const cur=String(el.value).trim(),orig=String(el.dataset.orig||"").trim();
    if(cur!==""){const n=Number(cur);
      if(isNaN(n)||n<0||n>100){alert("费用类别「"+el.dataset.cat+"」去税率须为 0~100 的数字");throw new Error("bad");}}
    if(cur===orig)return;
    detax[el.dataset.cat]=cur===""?null:Number(cur);detaxChanged++;});
  if(!manuals.length&&!allocChanged&&!detaxChanged){showToast("没有需要保存的更改");return;}
  const btn=document.getElementById("btnBatchSave");btn.disabled=true;btn.textContent="保存中…";
  try{
    if(manuals.length)await jpost("/api/manual_batch",{归属月:m,范围:mScope,items:manuals});
    if(allocChanged)await jpost("/api/alloc_rates",{归属月:m,rates:allocs});
    if(detaxChanged)await jpost("/api/detax_rates",{rates:detax});
    setDirtyCount(0);
    showToast("✓ 已保存 "+(manuals.length+allocChanged+detaxChanged)+" 项并重算");
    msg("批量保存完成（留痕·看板已重算）");
    reloadDash();loadHealth();await mLoad();
  }catch(e){if(e.message!=="bad")alert("保存失败："+e.message);}
  finally{btn.disabled=false;btn.textContent="保存全部更改";}
}

// ---- 异常处理（总览 / 调整台账 / 下单未填部门 / 费用未分类 / 历史快照）----
function showReview(which){if(!confirmLeave())return;
  document.querySelectorAll("#sub-review .stab").forEach(b=>b.classList.toggle("on",b.dataset.t===which));
  showSec(which);if(which==="overview")ovLoad();if(which==="ledger")lLoad();
  if(which==="orderdept")odLoad();if(which==="unclassified")ucLoad();if(which==="history")hisLoad();
  if(which==="audit")auLoad();}

// 操作记录（C3 配置变更留痕）：倒序、可按类别筛、最近200
let AU_CATS_FILLED=false;
async function auLoad(){const info=document.getElementById("auInfo"),tbl=document.getElementById("auTbl");
  const cat=document.getElementById("auCat").value;
  try{const d=await jget("/api/config_changes"+(cat?("?category="+encodeURIComponent(cat)):""));
    if(!AU_CATS_FILLED&&d.categories){const sel=document.getElementById("auCat");
      sel.innerHTML='<option value="">全部</option>'+d.categories.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join("");
      sel.value=cat;AU_CATS_FILLED=true;}
    const rows=d.changes||[];info.textContent="共 "+rows.length+" 条"+(cat?("（"+cat+"）"):"");
    if(!rows.length){tbl.innerHTML="<tr><td class='muted'>暂无记录（发生配置变更后自动出现）</td></tr>";return;}
    tbl.innerHTML="<tr><th>时间</th><th>操作账号</th><th>类别</th><th>变更摘要</th></tr>"+
      rows.map(r=>"<tr><td class='muted'>"+esc(r["时间"])+"</td><td>"+esc(r["操作账号"])+
        "</td><td>"+esc(r["类别"])+"</td><td>"+esc(r["摘要"])+"</td></tr>").join("");
  }catch(e){info.textContent="加载失败："+e.message;}}

// 总览：异常计数卡（新增一类异常=EXC_CARDS 注册一条 + /api/exceptions 加一个键；R4 冲突待确认已留位）
const EXC_CARDS=[
  {key:"order_unfilled_dept",label:"下单未填部门",desc:"智云源头没填部门，排名灰显待归类",go:()=>showReview("orderdept")},
  {key:"expense_unclassified",label:"费用未分类（台账）",desc:"收单台账没填对应报表大类，暂未计入费用",go:()=>showReview("unclassified")},
  {key:"adjust_expired",label:"过期疑似调整",desc:"源头已改、我的调整未套用，需拍板听谁的",go:()=>showReview("ledger")},
  {key:"adjust_missing",label:"调整失配",desc:"调整定位键在源头找不到了（行删了/键变了）",go:()=>showReview("ledger")},
  {key:"__conflict",label:"冲突待确认",desc:"智云改了 vs 这里改了（R4 上线后启用）",disabled:true},
];
async function ovLoad(){const el=document.getElementById("ovCards");
  let ex={};try{ex=await jget("/api/exceptions");}catch(e){el.innerHTML="<div class='muted'>加载失败："+esc(e.message)+"</div>";return;}
  setBadges(ex);
  const h=(window._health||{});const hHtml=(h.result&&h.result!=="绿")||((h.warnings||[]).length)
    ?"<div class='muted' style='margin-top:6px'>另：顶栏体检 "+esc(h.result||"?")+((h.warnings||[]).length?("·"+h.warnings.length+"警"):"")+"（抓数/运行信号，点顶栏「体检」看）</div>":"";
  el.innerHTML=EXC_CARDS.map(c=>{
    if(c.disabled)return "<div class='row-form' style='margin:0;padding:14px 16px;opacity:.45'>"+
      "<div style='font-weight:700'>"+esc(c.label)+"</div><div class='muted' style='margin-top:4px'>"+esc(c.desc)+"</div></div>";
    const n=ex[c.key]||0,ok=!n;
    return "<div class='row-form ovcard' data-k='"+esc(c.key)+"' style='margin:0;padding:14px 16px;cursor:pointer;border:1px solid "+(ok?"#14532d":"#7c2d12")+"'>"+
      "<div style='display:flex;align-items:center;gap:8px'><span style='font-size:22px;font-weight:800;color:"+(ok?"#4ade80":"#fb923c")+"'>"+n+"</span>"+
      "<span style='font-weight:700'>"+esc(c.label)+"</span></div>"+
      "<div class='muted' style='margin-top:4px'>"+(ok?"✓ 无待处理":esc(c.desc))+"</div></div>";}).join("")+hHtml;
  el.querySelectorAll(".ovcard").forEach(d=>{d.onclick=()=>{const c=EXC_CARDS.find(x=>x.key===d.dataset.k);if(c&&c.go)c.go();};});}

// 下单未填部门：清单 + 按销售筛选 + 批量归类 + 行内选部门
let OD_DEPTS=[],OD_ROWS=[];
function odUrl(p){return "/api/detail?table="+encodeURIComponent("下单")+"&unfilled_dept=1&page="+p+"&page_size=200";}
async function odLoad(){const tbl=document.getElementById("odTbl");tbl.innerHTML="";OD_ROWS=[];
  try{OD_DEPTS=await jget("/api/order_depts");}catch(e){}
  const dsel=document.getElementById("odBatchDept");
  if(dsel)dsel.innerHTML="<option value=''>选部门…</option>"+OD_DEPTS.map(x=>"<option>"+esc(x)+"</option>").join("");
  let page=1,pages=1,total=0;
  try{do{const d=await jget(odUrl(page));pages=d.pages;total=d.total;
    OD_ROWS=OD_ROWS.concat(d.rows||[]);page++;
  }while(page<=pages&&page<=50);}catch(e){msg("查询失败:"+e.message);}
  const sales=[...new Set(OD_ROWS.map(r=>(r["销售"]||"").trim()).filter(Boolean))].sort();
  const ssel=document.getElementById("odSales");
  const prev=ssel?ssel.value:"";
  if(ssel){ssel.innerHTML='<option value="">全部销售</option>'+sales.map(s=>'<option>'+esc(s)+'</option>').join("");
    ssel.value=sales.includes(prev)?prev:"";ssel.onchange=odRender;}
  document.getElementById("odInfo").textContent="待归类 "+total+" 笔";
  const b=document.getElementById("odBadge");b.textContent=total;b.className="badge"+(total?"":" zero");
  odRender();}
function odRender(){const tbl=document.getElementById("odTbl");
  const sf=(document.getElementById("odSales")||{}).value||"";
  const rows=sf?OD_ROWS.filter(r=>(r["销售"]||"").trim()===sf):OD_ROWS;
  const opts="<option value=''>选部门…</option>"+OD_DEPTS.map(x=>"<option>"+esc(x)+"</option>").join("");
  let h="<tr><th>下单日期</th><th>订单号</th><th>销售</th><th>金额</th><th>归到哪个部门</th><th></th></tr>";
  rows.forEach(r=>{const key=r["定位键"];
    h+="<tr data-key='"+esc(encodeURIComponent(key))+"'><td>"+esc(r["下单日期"])+"</td><td>"+esc(r["订单号"])+
      "</td><td>"+esc(r["销售"])+"</td><td>"+esc(r["下单预估额"])+
      "</td><td><select data-key='"+esc(encodeURIComponent(key))+"'>"+opts+"</select></td>"+
      "<td><button class='mini' onclick='odSave(this)'>保存</button></td></tr>";});
  tbl.innerHTML=h||"<tr><td class='muted'>无待归类</td></tr>";
  document.getElementById("odInfo").textContent="显示 "+rows.length+" / 共 "+OD_ROWS.length+" 笔"+(sf?"（销售="+sf+"）":"");
}
async function odSave(btn){const tr=btn.closest("tr"),sel=tr.querySelector("select");
  const dept=sel.value;if(!dept){alert("先选部门");return;}
  const key=decodeURIComponent(sel.dataset.key);btn.disabled=true;
  try{await jpost("/api/adjust",{目标表:"std_下单",定位键:key,字段:"部门",新值:dept,原因:"异常处理·归类部门",类型:"改值"});
    showToast("✓ 已归类");OD_ROWS=OD_ROWS.filter(r=>r["定位键"]!==key);
    msg("已归类（写入数据修正·秒级重算）");reloadDash();loadHealth();refreshUcBadge();odRender();
    const b=document.getElementById("odBadge");b.textContent=OD_ROWS.length;b.className="badge"+(OD_ROWS.length?"":" zero");
  }catch(e){btn.disabled=false;alert("保存失败："+e.message);}}
async function odBatchSave(){
  const dept=(document.getElementById("odBatchDept")||{}).value||"";
  if(!dept){alert("先选批量部门");return;}
  const sf=(document.getElementById("odSales")||{}).value||"";
  const rows=sf?OD_ROWS.filter(r=>(r["销售"]||"").trim()===sf):OD_ROWS;
  if(!rows.length){alert("没有可归类的行");return;}
  if(!confirm("将把 "+rows.length+" 笔"+(sf?"（销售="+sf+"）":"")+" 全部归到「"+dept+"」？"))return;
  let ok=0,fail=0;
  for(const r of rows){
    try{await jpost("/api/adjust",{目标表:"std_下单",定位键:r["定位键"],字段:"部门",新值:dept,
      原因:"异常处理·批量归类"+(sf?"·"+sf:""),类型:"改值"});ok++;}
    catch(e){fail++;}
  }
  showToast("✓ 批量完成：成功 "+ok+(fail?"，失败 "+fail:""));
  reloadDash();loadHealth();refreshUcBadge();odLoad();
}
// 历史快照：年→月→日 级联回看（每天最后一次更新的页面原样；快照多了也不乱）
let HIS=[];
function _hisSel(id){return document.getElementById(id);}
async function hisLoad(){const info=_hisSel("hisInfo");
  try{HIS=await jget("/api/history");   // 已按天倒序
    if(!HIS.length){info.textContent="还没有历史快照（每次更新后自动生成，明天起就有了）";
      _hisSel("hisFrame").src="about:blank";["hisY","hisM","hisD"].forEach(i=>_hisSel(i).innerHTML="");return;}
    info.textContent="共 "+HIS.length+" 天";
    const years=[...new Set(HIS.map(x=>x.day.slice(0,4)))];
    _hisSel("hisY").innerHTML=years.map(y=>'<option value="'+y+'">'+y+'年</option>').join("");
    _hisSel("hisY").onchange=()=>hisFillM();
    _hisSel("hisM").onchange=()=>hisFillD();
    _hisSel("hisD").onchange=()=>hisShow(_hisSel("hisD").value);
    hisFillM();
  }catch(e){info.textContent="加载失败:"+e.message;}}
function hisFillM(){const y=_hisSel("hisY").value;
  const months=[...new Set(HIS.filter(x=>x.day.slice(0,4)===y).map(x=>x.day.slice(4,6)))];
  _hisSel("hisM").innerHTML=months.map(m=>'<option value="'+m+'">'+(+m)+'月</option>').join("");
  hisFillD();}
function hisFillD(){const y=_hisSel("hisY").value,m=_hisSel("hisM").value;
  const days=HIS.filter(x=>x.day.slice(0,4)===y&&x.day.slice(4,6)===m);
  _hisSel("hisD").innerHTML=days.map(x=>'<option value="'+x.day+'">'+(+x.day.slice(6))+'日（存于 '+esc(x.saved_at)+'）</option>').join("");
  if(days.length)hisShow(days[0].day);}
function hisShow(day){_hisSel("hisFrame").src="/api/history/"+day;}
let LADJ=[];
async function lLoad(){LADJ=await jget("/api/adjustments");lRender();}
function lRender(){const expOnly=document.getElementById("lExpOnly").checked;
  const d=expOnly?LADJ.filter(a=>a["状态"]==="过期疑似"):LADJ;
  const nExp=LADJ.filter(a=>a["状态"]==="过期疑似").length;
  document.getElementById("lInfo").textContent="共 "+LADJ.length+" 条（过期疑似 "+nExp+"）";
  document.getElementById("lBatchBtn").style.display=nExp?"":"none";
  let h="<tr><th>id</th><th>时间</th><th>操作账号</th><th>目标表</th><th>字段</th><th>原值→新值</th><th>类型</th><th>状态</th><th></th></tr>";
  d.forEach(a=>{const exp=a["状态"]==="过期疑似";
    let ops="";
    if(exp&&a["类型"]==="改值")ops+="<button class='mini' onclick='lRearm("+a.id+")'>坚持我的数</button> ";
    if(a["状态"]!=="已撤销")ops+="<button class='mini ghost' onclick='lRevoke("+a.id+")'>撤销</button>";
    h+="<tr class='"+(exp?"exp":"")+"'><td>"+a.id+"</td><td>"+esc(a["创建时间"])+"</td><td>"+esc(a["经手人"])+
    "</td><td>"+esc(a["目标表"])+"</td><td>"+esc(a["字段"])+"</td><td>"+esc(a["原值"])+" → "+esc(a["新值"])+"</td><td>"+esc(a["类型"])+
    "</td><td>"+esc(a["状态"])+"</td><td>"+ops+"</td></tr>";});
  document.getElementById("lTbl").innerHTML=h;}
async function lRevoke(id){if(!confirm("撤销该调整？（=认可源头新值，页面继续用源头值）"))return;
  try{await jpost("/api/adjust/"+id+"/revoke",{});
  msg("已撤销");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}
async function lRearm(id){const a=LADJ.find(x=>x.id===id)||{};
  if(!confirm("坚持我的数？\n"+(a["目标表"]||"")+" · "+(a["字段"]||"")+"：将继续使用你改的值「"+(a["新值"]||"")+"」，覆盖源头新值。"))return;
  try{await jpost("/api/adjust/"+id+"/rearm",{});
  msg("已重新生效");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}
function lBatchAsk(){const n=LADJ.filter(a=>a["状态"]==="过期疑似").length;if(!n)return;
  const box=document.getElementById("lConfirm");
  box.innerHTML="将批量撤销 <b>"+n+"</b> 条「过期疑似」调整 = 全部认可源头新值（页面本就在用新值，此操作确认事实、清掉黄灯）。"+
    "撤销后如需恢复某条，去明细里重新改即可。 "+
    "<button class='mini' onclick='lBatchDo()'>确认保存</button> <button class='mini ghost' onclick='lBatchCancel()'>取消</button>";
  box.style.display="";}
function lBatchCancel(){const box=document.getElementById("lConfirm");box.style.display="none";box.innerHTML="";}
async function lBatchDo(){lBatchCancel();
  try{const r=await jpost("/api/adjust/expired/revoke_all",{});
  msg("已批量撤销 "+r.revoked+" 条");reloadDash();loadHealth();lLoad();}catch(e){alert("失败："+e.message);}}

// ---- 未填分类：只读清单（不提供当场补；请在源头收单台账补填，下次更新自动计入）----
let ucTotal=0;
function ucUrl(p){return "/api/detail?table="+encodeURIComponent("费用明细")+"&unclassified=1&page="+p+"&page_size=200";}
async function ucLoad(){const tbl=document.getElementById("ucTbl");tbl.innerHTML="";
  let page=1,pages=1;
  try{do{const d=await jget(ucUrl(page));pages=d.pages;ucTotal=d.total;
    if(page===1)tbl.innerHTML="<tr><th>收单日期</th><th>金额</th><th>预算明细费用类型</th></tr>";
    let h="";d.rows.forEach(r=>{
      h+="<tr><td>"+esc(r["收单日期"]||r["收单月份"])+"</td><td>"+esc(r["含税金额"])+
        "</td><td>"+esc(r["预算明细费用类型"])+"</td></tr>";});
    tbl.insertAdjacentHTML("beforeend",h);page++;
  }while(page<=pages&&page<=50);}catch(e){msg("查询失败:"+e.message);}
  document.getElementById("ucInfo").textContent="未分类 "+ucTotal+" 笔";setUcBadge(ucTotal);}
function setUcBadge(n){const b=document.getElementById("ucBadge");b.textContent=n;b.className="badge"+(n?"":" zero");}
function setBadges(ex){setUcBadge(ex.expense_unclassified||0);
  const b=document.getElementById("odBadge"),n=ex.order_unfilled_dept||0;
  b.textContent=n;b.className="badge"+(n?"":" zero");}
async function refreshUcBadge(){try{setBadges(await jget("/api/exceptions"));}catch(e){}}

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
  fillY("dY",true);fillM("dM",true);                                    // 明细筛选：可选、默认全部
  // 业绩目标独立年份（默认当前年；与人工填写月份/范围互不联动）
  if(document.getElementById("tgY")){
    fillY("tgY",false);
    document.getElementById("tgY").value=String(Math.max(d.getFullYear(),2026));
  }}
initYM();
document.getElementById("dWrap").addEventListener("scroll",function(){
  if(this.scrollTop+this.clientHeight>=this.scrollHeight-80)detail.next();});
loadHealth();refreshUcBadge();loadAdjFields();loadVersion();setInterval(loadHealth,30000);
// 打开页面时若更新已在跑（别处/定时触发），按钮跟着进入进度态
jget("/api/refresh_status").then(s=>{if(s.running){document.getElementById("btnRefresh").disabled=true;refT0=Date.now();pollRefresh();}}).catch(()=>{});
