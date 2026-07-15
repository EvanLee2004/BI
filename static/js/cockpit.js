
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
 var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
   return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c];});};
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
  // 用户端不展示「（未填）」——未填归类只在管理端异常处理
  var h='',items=(rk&&rk.items)||[];
  if(!items.length)return '<div class="ev-empty">本期无数据</div>';
  items.forEach(function(it,i){h+='<div class="ev-row rk-row"><span class="rk-no">'+(i+1)+'</span>'+
    '<span class="ev-name" title="'+esc(it.name)+'">'+esc(it.name)+'</span><span class="ev-track"></span>'+
    '<span class="ev-amt">'+esc(it.disp)+'</span><span class="rk-meta">'+it.count+'笔</span></div>';});
  if(rk&&rk.others)h+='<div class="ev-row rk-row rk-others rk-more" title="点开看 10 名以后的完整明细"><span class="rk-no">…</span>'+
    '<span class="ev-name">其余 '+rk.others.names+' 个 <span class="rk-open">点开看明细 ›</span></span>'+
    '<span class="ev-track"></span><span class="ev-amt">'+esc(rk.others.disp)+'</span><span class="rk-meta">'+rk.others.count+'笔</span></div>';
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
