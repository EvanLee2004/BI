
(function(){
 var root=document.documentElement, btn=document.getElementById('themeBtn');
 function setL(l){root.classList.toggle('theme-light',!!l);document.body.classList.toggle('theme-light',!!l);
   if(btn) btn.innerHTML=l?'<span>◐</span> 深色':'<span>◑</span> 浅色';}
 try{setL(localStorage.getItem('cockpit-theme')==='light');}catch(e){}
 if(btn) btn.addEventListener('click',function(){var l=!root.classList.contains('theme-light');setL(l);
   try{localStorage.setItem('cockpit-theme',l?'light':'dark');}catch(e){}});
 // 跨页/管理端 iframe 同步（同源 localStorage + postMessage）
 window.addEventListener('storage',function(e){if(e.key==='cockpit-theme')setL(e.newValue==='light');});
 window.addEventListener('message',function(e){
   if(e.origin!==location.origin)return;
   if(e.data&&e.data.type==='cockpit-theme')setL(e.data.theme==='light');
 });
 // 周期选择：日历面板。所有周期块已预渲染，这里只切显示、不算任何数。
 var pbtn=document.getElementById('periodBtn'),ppanel=document.getElementById('ppanel');
 if(pbtn&&ppanel){
  var pYear=pbtn.getAttribute('data-year'),pCur=+pbtn.getAttribute('data-cur'),pStart=null;
  window._curBlk=pYear+'年';
  // 切周期：整区 periodSync 统一淡出→切 .pv→淡入（与基本情况同观感；零金额运算）
  var _periodT=null;
  // 迭代21+：全年视角 · 选中周期月份高亮（回款卡+经营利润趋势图共用；映射由服务端 data-rm-map 下发，前端只读写 class）
  window._syncRmHighlight=function(key){
    document.querySelectorAll('[data-rm-map]').forEach(function(card){
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
      });
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


(function(){
 var lo=document.getElementById('logoutBtn');
 if(lo)lo.addEventListener('click',function(){
  fetch('/api/v1/logout',{method:'POST',credentials:'same-origin'})
   .then(function(){location.replace('/login');})
   .catch(function(){location.replace('/login');});
 });
})();

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


(function(){
 var modal=document.getElementById('rkModal'); if(!modal) return;
 if(modal.parentElement!==document.body)document.body.appendChild(modal);
 function openFull(title, tag, html){
  document.getElementById('rkmTitle').textContent=title||'完整排名';
  document.getElementById('rkmTag').textContent=tag||'';
  document.getElementById('rkmList').innerHTML=html||'<div class="ev-empty">本期无数据</div>';
  modal.style.display='';}
 document.addEventListener('click',function(ev){
  var row=ev.target.closest?ev.target.closest('.rk-more'):null;
  if(row){
   var card=row.closest('.card'); if(!card)return;
   var full=card.querySelector('.rk-full'); if(!full)return;
   var h=card.querySelector('.card-h');
   var title=(h?h.textContent:'').replace(/\s+/g,' ').trim();
   openFull(title+' · 完整排名','',full.innerHTML); return;}
  // 陆总#8 / 任务书34：排名主体行 → data-mkey 查页面级月度字典（零金额运算）
  var ent=ev.target.closest?ev.target.closest('.rk-entity'):null;
  if(ent && !ent.classList.contains('dual-month') && ent.getAttribute('data-mkey')){
   var nm=(ent.querySelector('.ev-name')||{}).textContent||'';
   var html=typeof paintRankingMonthly==='function'
     ? paintRankingMonthly(ent)
     : '<div class="ev-empty">月度组装器未加载</div>';
   openFull(nm+' · 1~12 月下单/回款','',html); return;}
  row=ev.target.closest?ev.target.closest('.pr-more'):null;
  if(row){
   var card=row.closest('[data-dim]'); if(!card)return;
   var full=card.querySelector('.pr-full'); if(!full)return;
   var h=card.querySelector('.card-h');
   var title=(h?h.textContent:'').replace(/\s+/g,' ').trim();
   openFull(title+' · 完整排名','',full.innerHTML);}
 });
 var xc=document.getElementById('rkmClose');
 if(xc)xc.addEventListener('click',function(){modal.style.display='none';});
 modal.addEventListener('click',function(ev){if(ev.target===modal)modal.style.display='none';});
 document.addEventListener('keydown',function(e){if(e.key==='Escape')modal.style.display='none';});
})();


/* 任务书39·B/C：BU 页「按时间段看」— 走 /api/bu_daily（本 BU 过滤，零跨界 /api/daily） */
(function(){
  var panel=document.getElementById('dailyPanel');
  if(!panel)return;
  var card=document.getElementById("buLedgerCard");
  var bu=(card&&card.getAttribute("data-bu"))||"";
  var iS=document.getElementById('dailyS'),iE=document.getElementById('dailyE'),sum=document.getElementById('dailySum');
  var rkGlobal=document.getElementById('rankViews'),rkCustom=document.getElementById('rkCustom');
  var range=null;
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c];});};
  function yearStr(){var b=document.getElementById('periodBtn');return b?b.getAttribute('data-year'):'';}
  function yearKey(){return yearStr()+'年';}
  function yearRange(){var y=yearStr();return {s:y+'-01-01',e:y+'-12-31'};}
  function datesForKey(key){
    var el=document.querySelector('#rankViews .pv[data-blk="'+key+'"] [data-start]');
    if(el){var s=el.getAttribute('data-start')||'',e=el.getAttribute('data-end')||'';
      if(s&&e)return {s:s,e:e};}
    return yearRange();}
  function fillDates(se){if(!se)return;iS.value=se.s;iE.value=se.e;}
  function dualBarRow(it){
    // 宽度%后端已算好，前端只拼 CSS（铁律2）
    var wo=(it.wo!=null?it.wo:0),wr=(it.wr!=null?it.wr:0);
    return '<div class="ev-row dual-row"><span class="rk-no">'+it.i+'</span>'+
      '<span class="ev-name" title="'+esc(it.name)+'">'+esc(it.name)+'</span>'+
      '<div class="dual-bars">'+
      '<span class="dual-bar dual-o" title="下单"><i style="width:'+wo+'%"></i><em>'+esc(it.order_disp)+'</em></span>'+
      '<span class="dual-bar dual-r" title="回款"><i style="width:'+wr+'%"></i><em>'+esc(it.receipt_disp)+'</em></span>'+
      '</div></div>';}
  function dualCard(blk){
    var body;
    if(!blk||blk.empty||!(blk.items&&blk.items.length))body='<div class="ev-empty">本期无数据</div>';
    else{
      var more='';
      if(blk.others)more='<div class="ev-row rk-row rk-others rk-more" title="点开看完整明细">'+
        '<span class="rk-no">…</span><span class="ev-name">其余 '+blk.others.names+
        ' 个 <span class="rk-open">点开看明细 ›</span></span><span class="ev-track"></span>'+
        '<span class="ev-amt">'+esc(blk.others.amt)+'</span><span class="rk-meta">'+blk.others.count+'笔</span></div>';
      var full='';
      if(blk.full_items&&blk.full_items.length){
        full='<div class="rk-full" hidden><div class="ev-list">'+blk.full_items.map(dualBarRow).join('')+'</div></div>';}
      body='<div class="ev-list rk-list">'+blk.items.map(dualBarRow).join('')+more+'</div>'+full;}
    var leg='<span class="dual-legend" title="双血条读法"><span class="dual-leg dual-o">上·紫=下单</span>'+
      '<span class="dual-leg dual-r">下·青=回款</span></span>';
    return '<div class="card" data-dim="'+esc(blk.dim||'')+'"><div class="card-h">'+esc(blk.title||'')+leg+'</div>'+body+'</div>';}
  function runQuery(){
    var s=iS.value,e=iE.value;
    if(!s||!e){sum.textContent='请选起止日期';return;}
    if(!bu){sum.textContent='缺少 BU';return;}
    sum.textContent='查询中…';
    var u='/api/bu_daily?bu='+encodeURIComponent(bu)+'&start='+encodeURIComponent(s)+'&end='+encodeURIComponent(e);
    fetch(u,{credentials:'same-origin'}).then(function(r){
      if(!r.ok)return r.json().then(function(d){throw new Error(d.detail||('HTTP '+r.status));});
      return r.json();
    }).then(function(d){
      range={s:s,e:e};
      var dual=d.dual_rankings||{};
      var tag=(s===e)?('只看 '+s):(s+' ~ '+e);
      rkCustom.innerHTML='<div class="grid-2e dual-grid" data-start="'+esc(s)+'" data-end="'+esc(e)+'" data-daily="1">'+
        dualCard(dual.sales||{title:'下单/回款 · 按销售',dim:'sales',empty:true})+
        dualCard(dual.customer||{title:'下单/回款 · 按客户',dim:'customer',empty:true})+'</div>';
      if(rkGlobal)rkGlobal.style.display='none';
      rkCustom.style.display='';
      sum.innerHTML='这段合计：下单 <b>'+esc(d.totals.orders_disp)+'</b>·'+d.totals.orders_count+
        '笔 ｜ 回款 <b>'+esc(d.totals.receipts_disp)+'</b>·'+d.totals.receipts_count+'笔 <span class="daily-note">'+esc(tag)+'</span>';
    }).catch(function(err){sum.textContent='查询失败：'+err.message;});
  }
  window._syncDailyDates=function(key){
    fillDates(datesForKey(key||window._curBlk||yearKey()));
    runQuery();
  };
  fillDates(yearRange());
  iS.addEventListener('change',function(){if(iE.value&&iE.value<iS.value)iE.value=iS.value;});
  function restoreYear(){
    range=null;sum.textContent='';
    if(rkCustom){rkCustom.style.display='none';rkCustom.innerHTML='';}
    if(rkGlobal)rkGlobal.style.display='';
    var yk=yearKey(),yl=yearStr()+'年';
    if(window.applyPeriod)window.applyPeriod(yk,yl);
    else{window._curBlk=yk;fillDates(yearRange());}
  }
  var dc=document.getElementById('dailyClose');if(dc)dc.addEventListener('click',restoreYear);
  function isoToday(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
  function monthRange(){var d=new Date(),y=d.getFullYear(),m=d.getMonth()+1;
    var last=new Date(y,m,0).getDate();
    return {s:y+'-'+String(m).padStart(2,'0')+'-01',e:y+'-'+String(m).padStart(2,'0')+'-'+String(last).padStart(2,'0')};}
  var btnToday=document.getElementById('dailyToday'),btnMonth=document.getElementById('dailyMonth');
  if(btnToday)btnToday.addEventListener('click',function(){var t=isoToday();iS.value=t;iE.value=t;runQuery();});
  if(btnMonth)btnMonth.addEventListener('click',function(){var r=monthRange();iS.value=r.s;iE.value=r.e;runQuery();});
  var go=document.getElementById('dailyGo');if(go)go.addEventListener('click',runQuery);
  // 其余弹窗：本地 .rk-full
  document.addEventListener('click',function(ev){
    var row=ev.target.closest?ev.target.closest('.rk-more'):null;
    if(!row)return;
    var cardEl=row.closest('.card'); if(!cardEl)return;
    var localFull=cardEl.querySelector('.rk-full'); if(!localFull)return;
    var modal=document.getElementById('rkModal'); if(!modal)return;
    if(modal.parentElement!==document.body)document.body.appendChild(modal);
    var h=cardEl.querySelector('.card-h');
    var title=(h?h.textContent:'').replace(/\s+/g,' ').trim();
    document.getElementById('rkmTitle').textContent=title+' · 完整排名';
    document.getElementById('rkmTag').textContent='';
    document.getElementById('rkmList').innerHTML=localFull.innerHTML;
    modal.style.display='';
  });
})();

/* A5 + 任务书39·D：本 BU 费用明细（只读；后端强制 BU 隔离；胶囊控件/sticky/分页/周期联动） */
(function(){
  var card=document.getElementById("buLedgerCard");
  if(!card)return;
  var bu=card.getAttribute("data-bu")||"";
  var yEl=document.getElementById("blY"), mEl=document.getElementById("blM");
  var qEl=document.getElementById("blQ"), info=document.getElementById("blInfo"), tbl=document.getElementById("blTbl");
  var pager=document.getElementById("blPager");
  var page=1, pageSize=200, total=0, handYm=false;
  var y0=new Date().getFullYear();
  for(var y=y0;y>=2026;y--){var o=document.createElement("option");o.value=String(y);o.textContent=y+"年";yEl.appendChild(o);}
  yEl.value=String(Math.max(y0,2026));
  for(var m=1;m<=12;m++){var o=document.createElement("option");o.value=String(m);o.textContent=m+"月";mEl.appendChild(o);}
  function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];});}
  function isAmtCol(c){return /金额|含税|未税|价税/.test(c||"");}
  function isFlexCol(c){return /事项|摘要|备注|说明/.test(c||"");}
  function paintPager(){
    if(!pager)return;
    var pages=Math.max(1,Math.ceil((total||0)/pageSize));
    if(page>pages)page=pages;
    pager.innerHTML='<button type="button" class="toggle" id="blPrev" '+(page<=1?"disabled":"")+'>上一页</button>'+
      '<span>第 '+page+' / '+pages+' 页 · 每页 '+pageSize+'</span>'+
      '<button type="button" class="toggle" id="blNext" '+(page>=pages?"disabled":"")+'>下一页</button>';
    var prev=document.getElementById("blPrev"),next=document.getElementById("blNext");
    if(prev)prev.onclick=function(){if(page>1){page--;load();}};
    if(next)next.onclick=function(){if(page<pages){page++;load();}};
  }
  function load(){
    var u="/api/detail?table="+encodeURIComponent("费用明细")+"&page="+page+"&page_size="+pageSize+"&bu="+encodeURIComponent(bu);
    if(yEl.value&&mEl.value){var mm=("0"+mEl.value).slice(-2);u+="&month="+encodeURIComponent(yEl.value+"-"+mm);}
    else if(yEl.value)u+="&year="+encodeURIComponent(yEl.value);
    var q=(qEl.value||"").trim();if(q)u+="&q="+encodeURIComponent(q);
    info.textContent="加载中…";
    fetch(u,{credentials:"same-origin"}).then(function(r){
      if(r.status===401||r.status===403){info.textContent="无权限";return null;}
      return r.json();
    }).then(function(d){
      if(!d)return;
      total=d.total||0;
      info.textContent="共 "+total+" 行（本页 "+(d.rows||[]).length+"）";
      var cols=d.columns||[];
      var h="<tr>"+cols.map(function(c){
        var cls=(isAmtCol(c)?"num":"")+(isFlexCol(c)?" col-flex":"");
        return "<th class=\""+cls+"\">"+esc(c)+"</th>";
      }).join("")+"</tr>";
      (d.rows||[]).forEach(function(row){
        h+="<tr>"+cols.map(function(c){
          var cls=(isAmtCol(c)?"num":"")+(isFlexCol(c)?" col-flex":"");
          return "<td class=\""+cls+"\">"+esc(row[c])+"</td>";
        }).join("")+"</tr>";
      });
      tbl.innerHTML=h||"<tr><td class='muted'>无数据</td></tr>";
      paintPager();
    }).catch(function(e){info.textContent="失败："+e.message;});
  }
  window._syncLedgerYm=function(key){
    if(handYm)return;
    var k=key||window._curBlk||"";
    var yMatch=k.match(/^(\d{4})年/);
    if(yMatch)yEl.value=yMatch[1];
    var mSingle=k.match(/年(\d{1,2})月$/);
    if(mSingle)mEl.value=String(parseInt(mSingle[1],10));
    else mEl.value="";
    page=1;load();
  };
  var _prev=window._syncDailyDates;
  window._syncDailyDates=function(key){
    if(typeof _prev==="function")_prev(key);
    if(window._syncLedgerYm)window._syncLedgerYm(key);
  };
  document.getElementById("blGo").onclick=function(){handYm=true;page=1;load();};
  yEl.addEventListener("change",function(){handYm=true;});
  mEl.addEventListener("change",function(){handYm=true;});
  load();
})();
