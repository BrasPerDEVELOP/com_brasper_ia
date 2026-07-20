/* ===========================================================
   Cauce — vistas (window.VIEWS) + interacciones (window.VIEW_INIT)
   =========================================================== */
(function(){
  var icon = window.icon;
  function C(){ return window.__cauce; }
  function head(t,d){ return '<div class="sec-head"><h2>'+t+'</h2>'+(d?'<p>'+d+'</p>':'')+'</div>'; }
  var PCOLOR={crm:'#DD6A3C',calendar:'#2C6FB0',payments:'#0E7C66',ecommerce:'#5B51B3',data:'#C98A1E',channels:'#1cae8a',llm:'#16201C',automation:'#B0436B',helpdesk:'#2C6FB0',analytics:'#888780'};
  function initials(n){ var p=n.replace(/[^A-Za-z0-9 ]/g,'').trim().split(' '); return ((p[0]||'')[0]||'')+((p[1]||'')[0]||(p[0]||'')[1]||''); }
  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function catName(D,key){ var c=(D.pluginCategories||[]).filter(function(x){return x.key===key;})[0]; return c?c.name:key; }
  function pluginCard(D,T,p){ var on=D.enabledPlugins.indexOf(p.key)>=0; return '<div class="mkt-card" data-cat="'+p.category+'"><div class="mh"><div class="mkt-logo" style="background:'+(PCOLOR[p.category]||'#888')+'">'+initials(p.name)+'</div><div><div class="mn">'+p.name+'</div><div class="mc">'+catName(D,p.category)+'</div></div></div><div class="md">'+p.desc+'</div><div class="mf">'+(on?'<span class="pill green">'+icon('check','currentColor',13)+' '+T('act_enabled')+'</span>':'<span class="muted" style="font-size:12px">—</span>')+'<button class="btn sm '+(on?'':'primary')+'" data-k="'+p.key+'">'+(on?T('act_configure'):T('act_enable'))+'</button></div></div>'; }
  function fbCopy(t){ var ta=document.createElement('textarea'); ta.value=t; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.select(); try{document.execCommand('copy');}catch(e){} document.body.removeChild(ta); }
  function copyText(t){ try{ if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(t).catch(function(){fbCopy(t);}); } else { fbCopy(t); } }catch(e){ fbCopy(t); } }
  var TINT={blue:'var(--blue)',green:'var(--accent)',amber:'var(--amber)',coral:'var(--coral)'};
  var TINTBG={blue:'var(--blue-soft)',green:'var(--accent-soft)',amber:'var(--amber-soft)',coral:'var(--coral-soft)'};

  var V={}, INIT={};

  /* ===================== AGENCIA (portafolio de clientes) ===================== */
  V.agency=function(ctx){ var T=ctx.T, D=ctx.D;
    var totFee=0, totCost=0, active=0;
    D.tenants.forEach(function(t){ totFee+=t.fee; totCost+=t.cost; if(t.status==='activo') active++; });
    var kpis=[
      {n:D.tenants.length+' <span style="font-size:14px;color:var(--muted)">('+active+' '+T('ag_active')+')</span>', l:T('ag_clients'), ic:'building', tint:'blue'},
      {n:'US$ '+totFee.toLocaleString('es'), l:T('ag_revenue'), ic:'dollar', tint:'green'},
      {n:'US$ '+Math.round(totCost).toLocaleString('es'), l:T('ag_aicost'), ic:'ai', tint:'amber'},
      {n:'US$ '+Math.round(totFee-totCost).toLocaleString('es')+' <span style="font-size:14px;color:var(--accent)">('+Math.round((totFee-totCost)/totFee*100)+'%)</span>', l:T('ag_margin'), ic:'chart', tint:'green'}
    ].map(function(s){return '<div class="card stat"><div class="top"><div class="ic" style="background:'+TINTBG[s.tint]+'">'+icon(s.ic,TINT[s.tint])+'</div></div><div class="num">'+s.n+'</div><div class="lbl">'+s.l+'</div></div>';}).join('');
    var rows=D.tenants.map(function(t,i){
      var ob=[];
      ob.push(t.onboarding.numero==='cliente'?'<span class="tag reuse">'+icon('check','currentColor',12)+' '+T('ag_number')+' '+T('num_client')+'</span>':'<span class="tag warn">'+icon('alert','currentColor',12)+' '+T('ag_number')+' '+T('num_agency')+'</span>');
      ob.push(t.onboarding.contrato?'<span class="tag reuse">'+T('ag_contract')+'</span>':'<span class="tag warn">'+icon('alert','currentColor',12)+' '+T('ag_contract')+'</span>');
      ob.push(t.onboarding.datos?'<span class="tag reuse">'+T('ag_data')+'</span>':'<span class="tag warn">'+icon('alert','currentColor',12)+' '+T('ag_data')+'</span>');
      return '<tr data-i="'+i+'" style="cursor:pointer"><td><span class="av-s" style="background:'+t.color+'">'+t.initial+'</span>'+t.name+'</td>'+
        '<td>'+(t.status==='activo'?'<span class="pill green">'+T('ag_st_active')+'</span>':'<span class="pill gray">'+T('ag_st_paused')+'</span>')+'</td>'+
        '<td class="muted mono" style="font-size:12px">'+t.wa+'</td>'+
        '<td class="mono num">'+t.msgs.toLocaleString('es')+'</td>'+
        '<td class="mono num" style="color:var(--danger)">'+Math.round(t.cost)+'</td>'+
        '<td class="mono num">'+t.fee+'</td>'+
        '<td class="mono num" style="color:var(--accent);font-weight:500">'+Math.round(t.fee-t.cost)+'</td>'+
        '<td><div class="wrap" style="gap:4px">'+ob.join('')+'</div></td>'+
        '<td style="text-align:right;color:var(--faint)">'+icon('arrow','currentColor',15)+'</td></tr>';
    }).join('');
    return head(T('nav_agency'),T('ag_intro'))+
      '<div class="stats stagger mb18">'+kpis+'</div>'+
      '<div class="card pad"><div class="between mb14"><h3>'+T('ag_clients')+'</h3><button class="btn sm primary" id="agNew">'+icon('plus','currentColor',14)+' '+T('create_company')+'</button></div>'+
      '<div class="tblwrap"><table class="tbl"><thead><tr><th>'+T('ag_client')+'</th><th>'+T('ag_status')+'</th><th>'+T('ag_channel')+'</th><th class="num">'+T('ag_usage')+'</th><th class="num">'+T('ag_aicost')+' (US$)</th><th class="num">'+T('bill_fee')+' (US$)</th><th class="num">'+T('ag_margin')+' (US$)</th><th>'+T('ag_onboarding')+'</th><th></th></tr></thead><tbody>'+rows+'</tbody>'+
      '<tfoot><tr style="border-top:2px solid var(--line-2)"><td colspan="3" style="font-weight:600">Total</td><td class="mono num">'+D.tenants.reduce(function(a,t){return a+t.msgs;},0).toLocaleString('es')+'</td><td class="mono num" style="color:var(--danger)">'+Math.round(totCost)+'</td><td class="mono num">'+totFee+'</td><td class="mono num" style="color:var(--accent);font-weight:600">'+Math.round(totFee-totCost)+'</td><td></td><td></td></tr></tfoot></table></div></div>';
  };
  INIT.agency=function(root){
    root.querySelectorAll('tbody tr[data-i]').forEach(function(tr){ tr.onclick=function(){ window.__cauce.setTenant(+tr.dataset.i); window.__cauce.setView('dashboard'); }; });
    var b=root.querySelector('#agNew'); if(b) b.onclick=function(){ window.__cauce.openCreateTenant(); };
  };

  /* ===================== DASHBOARD ===================== */
  V.dashboard=function(ctx){ var T=ctx.T, D=ctx.D;
    var stats=D.stats.map(function(s){return '<div class="card stat"><div class="top"><div class="ic" style="background:'+TINTBG[s.tint]+'">'+icon(s.icon,TINT[s.tint])+'</div><span class="delta '+(s.up?'up':'down')+'">'+s.delta+'<small style="display:block;font-weight:400;color:var(--faint);font-size:9.5px;text-align:right">'+T('vs_prev')+'</small></span></div><div class="num">'+s.num+'</div><div class="lbl">'+T(s.i18n)+'</div></div>';}).join('');
    var focus=(D.managedFocus||[]).map(function(x){return '<div class="focus-item"><div class="focus-check">'+icon('check','currentColor',14)+'</div><div><b>'+x.title+'</b><span>'+x.body+'</span></div></div>';}).join('');
    var plan=D.deliveryPlan||{readiness:[],timeline:[]};
    var readyDone=plan.readiness.filter(function(x){return x.ok;}).length;
    var readyList=plan.readiness.map(function(x){return '<div class="ready-item '+(x.ok?'ok':'todo')+'"><span>'+icon(x.ok?'check':'alert','currentColor',14)+'</span><div><b>'+x.title+'</b><small>'+x.body+'</small></div></div>';}).join('');
    var timeline=plan.timeline.map(function(x){return '<div class="work-step '+x.status+'"><div class="work-dot"></div><div class="work-meta"><span>'+x.phase+' · '+x.date+'</span><b>'+x.title+'</b><small>'+x.body+'</small></div></div>';}).join('');
    var recent=D.recent.map(function(r,ri){return '<tr data-ri="'+ri+'" style="cursor:pointer"><td><span class="av-s" style="background:'+r.color+'">'+r.in+'</span>'+r.name+'</td><td class="muted">'+r.ch+'</td><td>'+r.intent+'</td><td><span class="pill '+r.sc+'">'+T(r.state)+'</span></td><td>'+(r.lead?icon('check','var(--accent)',16):'<span class="muted">—</span>')+'</td><td class="muted mono">'+r.t+'</td></tr>';}).join('');
    return ''+
    '<div class="focus-panel mb18"><div><span class="tag reuse">'+T('managed_tag')+'</span><h2>'+T('managed_title')+'</h2><p>'+T('managed_desc')+'</p></div><div class="focus-list">'+focus+'</div></div>'+
    '<div class="launch-grid mb18">'+
      '<div class="card pad launch-card"><div class="between mb14"><div><span class="sub">'+T('launch_title')+'</span><h3>'+T('launch_start')+' <span class="mono">'+plan.start+'</span></h3></div><span class="pill green">'+readyDone+'/'+plan.readiness.length+' '+T('launch_ready')+'</span></div><div class="ready-list">'+readyList+'</div></div>'+
      '<div class="card pad launch-card"><div class="between mb14"><div><span class="sub">'+T('launch_timeline')+'</span><h3>'+T('launch_finish')+' <span class="mono">'+plan.finish+'</span></h3></div><button class="btn sm" data-go="roadmap">'+T('launch_detail')+' '+icon('arrow','currentColor',14)+'</button></div><div class="workline">'+timeline+'</div></div>'+
    '</div>'+
    '<div class="between mb14"><h2 style="font-size:21px">'+T('nav_dashboard')+'</h2><div class="select" id="dashRange" style="width:auto;cursor:pointer;user-select:none">'+T('rng_7d')+' '+icon('chev','var(--muted)',15)+'</div></div>'+
    '<div class="stats stagger">'+stats+'</div>'+
    '<div class="grid-2 stagger">'+
      '<div class="card pad"><div class="between mb18"><div><h3>'+T('dash_chart_title')+'</h3><span class="muted" style="font-size:12.5px">'+T('dash_chart_sub')+'</span></div><span class="pill green">'+icon('check','currentColor',13)+' '+T('st_online')+'</span></div>'+
        '<div class="chart-cols" id="chart"></div>'+
        '<div class="legend"><span><i style="background:#0E7C66"></i>'+T('legend_bot')+'</span><span><i style="background:#d9c98a"></i>'+T('legend_adv')+'</span></div></div>'+
      '<div class="card pad"><h3 class="mb18">'+T('dash_health')+'</h3><div style="display:flex;flex-direction:column;gap:13px">'+
        '<div class="between"><span class="muted">'+T('lbl_latency')+'</span><b class="mono">1,4 s</b></div>'+
        '<div class="between"><span class="muted">'+T('lbl_understanding')+'</span><b class="mono">94%</b></div>'+
        '<div class="between"><span class="muted">'+T('lbl_langs')+'</span><b>'+T('lang_same_value')+'</b></div>'+
        '<div class="between"><span class="muted">'+T('lbl_model')+'</span><span class="pill green">Claude · DeepSeek</span></div>'+
        '<div class="reuse-note" style="margin-top:4px">'+icon('refresh','currentColor',16)+'<div>'+T('reuse_dash')+'</div></div></div></div>'+
    '</div>'+
    '<div class="card pad mt18"><div class="between mb18"><h3>'+T('dash_recent')+'</h3><button class="btn sm" data-go="conversations">'+T('act_view_all')+' '+icon('arrow','currentColor',14)+'</button></div>'+
      '<div class="tblwrap"><table class="tbl"><thead><tr><th>'+T('th_contact')+'</th><th>'+T('th_channel')+'</th><th>'+T('th_intent')+'</th><th>'+T('th_state')+'</th><th>'+T('th_lead')+'</th><th>'+T('th_time')+'</th></tr></thead><tbody>'+recent+'</tbody></table></div></div>';
  };
  INIT.dashboard=function(root){
    var T=C().T, data=window.DATA.chart, chart=root.querySelector('#chart');
    var max=Math.max.apply(null,data.map(function(r){return r[0]+r[1];}))*1.1;
    window.DATA.days.forEach(function(dk,i){var d=T(dk),bot=Math.round(data[i][0]/max*150),adv=Math.round(data[i][1]/max*150);
      chart.insertAdjacentHTML('beforeend','<div class="col" title="'+d+': '+data[i][0]+' '+T('legend_bot')+' · '+data[i][1]+' '+T('legend_adv')+'"><div class="val">'+(data[i][0]+data[i][1])+'</div><div class="bar lt" data-h="'+adv+'" style="height:0"></div><div class="bar" data-h="'+bot+'" style="height:0"></div><div class="d">'+d+'</div></div>');});
    setTimeout(function(){chart.querySelectorAll('.bar').forEach(function(b){b.style.height=b.dataset.h+'px';});},100);
    root.querySelectorAll('[data-go]').forEach(function(b){b.onclick=function(){C().setView(b.dataset.go);};});
    root.querySelectorAll('tr[data-ri]').forEach(function(tr){tr.onclick=function(){C().setView('conversations');};});
    var rng=root.querySelector('#dashRange');
    if(rng){var rngs=[T('rng_7d'),T('rng_30d'),T('rng_90d')],ri=0;
      rng.onclick=function(){ri=(ri+1)%3;this.innerHTML=rngs[ri]+' '+icon('chev','var(--muted)',15);};}
  };

  /* ===================== FLOW BUILDER ===================== */
  var NODE_PROPS={
    ai:{c:'n-teal',ic:'ai',t:'node_ai',body:function(T){return '<div class="fld"><label>'+T('prop_model')+'</label><div class="select">Claude + DeepSeek (fallback) '+icon('chev','var(--muted)',15)+'</div></div>'+
      '<div class="fld"><label>'+T('prop_prompt')+'</label><textarea class="ta" rows="3">Clasifica la intención y extrae los datos. El backend decide la respuesta. Idioma: es|pt|en.</textarea></div>'+
      '<div class="fld"><label>'+T('prop_tools')+'</label><div class="toolrow"><span>tipo_de_cambio</span><span class="sw"></span></div><div class="toolrow"><span>comisiones</span><span class="sw"></span></div><div class="toolrow"><span>cupones</span><span class="sw"></span></div></div>'+
      '<div class="fld" style="margin-bottom:10px"><label>'+T('prop_outvar')+'</label><div class="input"><span class="mono" style="font-size:12px">intent · extracted_data</span></div></div>'+
      '<div class="reuse-note">'+icon('refresh','currentColor',16)+'<div>'+T('reuse_ai')+'</div></div>';}},
    start:{c:'n-gray',ic:'play',t:'node_start',body:function(T){return '<div class="fld"><label>'+T('prop_trigger')+'</label><div class="input">'+T('trig_first_msg')+'</div></div><div class="fld"><label>'+T('prop_channel')+'</label><div class="select">WhatsApp · Webchat '+icon('chev','var(--muted)',15)+'</div></div>';}},
    msg1:{c:'n-blue',ic:'chat',t:'node_message',body:function(T){return '<div class="fld"><label>'+T('prop_text')+' (ES)</label><textarea class="ta" rows="3">¡Hola! Soy el asistente de Brasper. ¿En qué te ayudo hoy?</textarea></div><div class="fld" style="margin-bottom:0"><label>'+T('prop_multilang')+'</label><div class="chips"><span class="pill green">ES</span><span class="pill green">PT</span><span class="pill green">EN</span></div></div>';}},
    cond:{c:'n-amber',ic:'branch',t:'node_condition',body:function(T){return ''+
      '<div class="fld"><label>'+T('prop_if')+'</label>'+
        '<div class="ifrow"><div class="select" style="font-size:12px">intent '+icon('chev','var(--muted)',14)+'</div><div class="select" style="font-size:12px">es igual a '+icon('chev','var(--muted)',14)+'</div></div>'+
        '<div class="input" style="margin-top:6px"><input value="remittance_quote" style="font-size:12px"></div>'+
        '<button class="btn sm ghost" style="margin-top:7px;width:100%">'+icon('plus','currentColor',14)+' '+T('act_add_rule')+'</button></div>'+
      '<div class="fld" style="margin-bottom:0"><label>'+T('prop_then')+'</label>'+
        '<div class="toolrow"><span>'+icon('arrow','var(--accent)',14)+' '+T('branch_yes')+'</span><span class="tag" style="background:var(--accent-soft);color:var(--accent-d)">true</span></div>'+
        '<div class="toolrow"><span>'+icon('arrow','var(--coral)',14)+' '+T('branch_no')+'</span><span class="tag" style="background:var(--coral-soft);color:var(--coral-d)">false</span></div></div>';}},
    api:{c:'n-pink',ic:'plug',t:'node_api',body:function(T){return '<div class="fld"><label>'+T('prop_method')+'</label><textarea class="ta" rows="2">GET /rates?from={origin}&to={dest}</textarea></div><div class="fld" style="margin-bottom:0"><label>'+T('prop_saveto')+'</label><div class="input"><span class="mono" style="font-size:12px">rate · fee</span></div></div>';}},
    msg2:{c:'n-blue',ic:'chat',t:'node_message',body:function(T){return '<div class="fld" style="margin-bottom:0"><label>'+T('prop_text')+' (ES)</label><textarea class="ta" rows="3">Por {send_amount} {origin} recibes {receive_amount} {dest}. ¿Te conecto con un asesor?</textarea></div>';}},
    hand:{c:'n-coral',ic:'headset',t:'node_handoff',body:function(T){return '<div class="fld"><label>'+T('prop_dest')+'</label><div class="select">'+T('dest_advisor')+' '+icon('chev','var(--muted)',15)+'</div></div><div class="fld"><label>'+T('prop_prereq')+'</label><div class="input">'+T('prereq_name')+'</div></div><div class="reuse-note">'+icon('refresh','currentColor',16)+'<div>'+T('reuse_handoff')+'</div></div>';}}
  };
  function nodeTitle(T,n){ return T(NODE_PROPS[n].t); }
  V.flows=function(ctx){ var T=ctx.T;
    function fnode(n,cls,ic,t,s,style,reuse){return '<div class="fnode '+cls+(n==='ai'?' sel':'')+'" data-n="'+n+'" style="'+style+'"><div class="fi">'+icon(ic,'currentColor')+'</div><div><div class="ft">'+t+(reuse?' <span class="rc">'+icon('refresh','currentColor',13)+'</span>':'')+'</div><div class="fs">'+s+'</div></div></div>';}
    return ''+
    '<div class="fb-bar"><span class="nm">'+icon('flow','var(--accent)',18)+' Cotización de remesas <span class="ver">v3 · '+T('st_published')+'</span></span>'+
      '<div class="langmini"><span class="on">ES</span><span>PT</span><span>EN</span></div>'+
      '<div style="margin-left:auto;display:flex;gap:9px"><button class="btn" id="fbVersions">'+icon('refresh','currentColor',15)+' '+T('flows_versions')+'</button>'+
      '<button class="btn" id="fbSim">'+icon('play','currentColor',15)+' '+T('act_simulate')+'</button>'+
      '<button class="btn" id="fbPrev">'+icon('eye','currentColor',15)+' '+T('act_preview')+'</button>'+
      '<button class="btn primary" id="fbPub">'+icon('rocket','currentColor',15)+' '+T('act_publish')+'</button></div></div>'+
    '<div class="info-note mb14">'+icon('branch','var(--blue)',16)+'<div>'+T('flow_hint')+'</div></div>'+
    '<div class="fb-wrap">'+
      '<div class="palette"><div class="ph">'+T('pal_nodes')+'</div>'+
        '<div class="pnode n-blue">'+icon('chat','currentColor')+' '+T('node_message')+'</div>'+
        '<div class="pnode n-purple">'+icon('form','currentColor')+' '+T('node_capture')+'</div>'+
        '<div class="pnode n-amber">'+icon('branch','currentColor')+' '+T('node_condition')+'</div>'+
        '<div class="pnode n-teal">'+icon('ai','currentColor')+' '+T('node_ai')+'<span class="rc">'+icon('refresh','currentColor',13)+'</span></div>'+
        '<div class="pnode n-pink">'+icon('plug','currentColor')+' '+T('node_api')+'</div>'+
        '<div class="pnode n-coral">'+icon('headset','currentColor')+' '+T('node_handoff')+'<span class="rc">'+icon('refresh','currentColor',13)+'</span></div></div>'+
      '<div class="canvas-wrap"><div class="cv-zoom"><button data-z="-">−</button><span id="zoomLbl">100%</span><button data-z="+">+</button><button data-z="fit" title="Fit">⤢</button></div><div class="canvas" id="canvas">'+
        '<svg class="wires" viewBox="0 0 740 480"><defs><marker id="ar" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#bcc9c2"/></marker></defs>'+
        '<path class="wire" id="w0" d="M365,60 C365,72 365,72 365,84" marker-end="url(#ar)"/>'+
        '<path class="wire" id="w1" d="M365,138 C365,146 365,146 365,150" marker-end="url(#ar)"/>'+
        '<path class="wire" id="w2" d="M365,210 C365,222 365,222 365,236" marker-end="url(#ar)"/>'+
        '<path class="wire" id="w3" d="M445,270 C522,270 560,296 560,322" marker-end="url(#ar)"/>'+
        '<path class="wire" id="w4" d="M285,270 C208,270 170,296 170,322" marker-end="url(#ar)"/>'+
        '<path class="wire" id="w5" d="M560,376 C560,382 560,382 560,392" marker-end="url(#ar)"/>'+
        '<text x="468" y="270" class="wlab">'+T('lbl_yes')+'</text><text x="232" y="270" class="wlab">'+T('lbl_no')+'</text></svg>'+
        '<div class="pulse" id="pulse"></div>'+
        fnode('start','n-gray','play',T('node_start'),T('fsub_first'),'left:290px;top:16px;width:150px')+
        fnode('msg1','n-blue','chat',T('node_message'),T('fsub_welcome'),'left:272px;top:84px;width:186px')+
        fnode('ai','n-teal','ai',T('node_ai'),T('fsub_intent'),'left:258px;top:150px;width:214px',true)+
        fnode('cond','n-amber','branch',T('node_condition'),T('fsub_quote'),'left:285px;top:236px;width:160px')+
        fnode('hand','n-coral','headset',T('node_handoff'),T('fsub_advisor'),'left:80px;top:322px;width:180px',true)+
        fnode('api','n-pink','plug',T('node_api'),T('fsub_rate'),'left:470px;top:322px;width:180px')+
        fnode('msg2','n-blue','chat',T('node_message'),T('fsub_result'),'left:470px;top:392px;width:180px')+
      '</div></div>'+
      '<div class="props" id="props"></div>'+
    '</div>';
  };
  INIT.flows=function(root){
    var T=C().T;
    function sel(id){root.querySelectorAll('.fnode').forEach(function(n){n.classList.toggle('sel',n.dataset.n===id);});var p=NODE_PROPS[id];if(!p)return;
      root.querySelector('#props').innerHTML='<div class="ph2 '+p.c+'"><span class="fi">'+icon(p.ic,'currentColor',16)+'</span> '+T(p.t)+'</div><div class="pbody">'+p.body(T)+'</div>';
      root.querySelectorAll('#props .sw').forEach(function(s){s.onclick=function(){s.classList.toggle('off');};});}
    var TRACE={start:'sim_start',msg1:'sim_msg1',ai:'sim_ai',cond:'sim_cond',api:'sim_api',msg2:'sim_msg2'};
    function showTrace(id){var pb=root.querySelector('#props .pbody');if(pb&&TRACE[id])pb.insertAdjacentHTML('afterbegin','<div class="info-note mb14">'+T(TRACE[id])+'</div>');}
    root.querySelectorAll('.fnode').forEach(function(n){n.onclick=function(){sel(n.dataset.n);};}); sel('ai');
    // simulate
    var centers={start:[365,38],msg1:[365,111],ai:[365,192],cond:[365,276],api:[560,363],msg2:[560,431]};
    var seq=['start','msg1','ai','cond','api','msg2'], pulse=root.querySelector('#pulse'), btn=root.querySelector('#fbSim'), tmr=null;
    function stop(){if(tmr){clearTimeout(tmr);tmr=null;}pulse.style.opacity=0;root.querySelectorAll('.fnode').forEach(function(n){n.classList.remove('lit');});root.querySelectorAll('.wire').forEach(function(w){w.classList.remove('on');});btn.innerHTML=icon('play','currentColor',15)+' '+T('act_simulate');}
    function run(i){if(i>=seq.length){tmr=setTimeout(function(){stop();C().toast(T('flows_sim_done'));},700);return;}var id=seq[i],c=centers[id];pulse.style.opacity=1;pulse.style.left=c[0]+'px';pulse.style.top=c[1]+'px';root.querySelectorAll('.fnode').forEach(function(n){n.classList.toggle('lit',n.dataset.n===id);});root.querySelectorAll('.wire').forEach(function(w){w.classList.remove('on');});var wr=root.querySelector('#w'+i);if(wr)wr.classList.add('on');sel(id);showTrace(id);tmr=setTimeout(function(){run(i+1);},800);}
    btn.onclick=function(){if(tmr){stop();return;}btn.innerHTML=icon('eye','currentColor',15)+' …';run(0);};
    root.querySelector('#fbPrev').onclick=function(){window.openBotPreview();};
    var z=1,cv=root.querySelector('#canvas');
    function setZ(v){z=Math.min(1.5,Math.max(.5,v));cv.style.transform='scale('+z+')';cv.style.transformOrigin='top center';root.querySelector('#zoomLbl').textContent=Math.round(z*100)+'%';}
    root.querySelectorAll('.cv-zoom button').forEach(function(b){b.onclick=function(){if(b.dataset.z==='fit'){var w=root.querySelector('.canvas-wrap').clientWidth;setZ(Math.min(1.4,(w-32)/740));}else setZ(z+(b.dataset.z==='+'?.1:-.1));};});
    root.querySelectorAll('.pnode').forEach(function(pn,idx){pn.onclick=function(){var m=pn.className.match(/n-\w+/);var el=document.createElement('div');el.className='fnode '+(m?m[0]:'n-gray');el.style.cssText='left:'+(40+idx*20)+'px;top:'+(30+idx*24)+'px;width:170px;animation:rise .3s ease both';var sv=pn.querySelector('svg');el.innerHTML='<div class="fi">'+(sv?sv.outerHTML:'')+'</div><div><div class="ft">'+pn.textContent.trim()+'</div><div class="fs">'+T('fb_new_node')+'</div></div>';cv.appendChild(el);C().toast(T('toast_node_added'));};});
    root.querySelectorAll('.langmini span').forEach(function(sp){sp.onclick=function(){root.querySelectorAll('.langmini span').forEach(function(x){x.classList.remove('on');});sp.classList.add('on');C().toast(T('toast_editing_lang')+' '+sp.textContent);};});
    root.querySelector('#fbPub').onclick=function(){C().toast(T('toast_published'));};
    root.querySelector('#fbVersions').onclick=function(){
      var rows=[['v3','30 jun 2026','Alberth C.','published'],['v2','12 jun 2026','Lucía M.','archived'],['v1','03 jun 2026','Lucía M.','archived']].map(function(r){return '<tr><td><b>'+r[0]+'</b></td><td class="muted">'+r[1]+'</td><td class="muted">'+r[2]+'</td><td><span class="pill '+(r[3]==='published'?'green':'gray')+'">'+(r[3]==='published'?T('st_published'):T('st_archived'))+'</span></td></tr>';}).join('');
      C().modal('<div class="modal-head">'+icon('refresh','var(--accent)',20)+'<h3>'+T('flows_versions')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div><div class="modal-body"><table class="tbl"><tbody>'+rows+'</tbody></table><div class="info-note mt14"><span>'+icon('info','var(--blue)',16)+'</span><div>'+T('flows_version_note')+'</div></div></div>');
    };
  };

  /* ===================== TEMPLATES ===================== */
  V.templates=function(ctx){ var T=ctx.T, D=ctx.D;
    var cards=D.verticals.map(function(v){return '<div class="tpl-card" data-v="'+v.key+'"><div class="tpl-top" style="background:'+v.color+'">'+icon(v.icon,'#fff',30)+'</div><div class="tpl-body"><div class="tn">'+v.name+'</div><div class="td"><b>'+T('tpl_flow')+':</b> '+v.flow+'</div><div class="tpl-nodes">'+v.nodes.slice(0,4).map(function(n){return '<span class="tag">'+n.split(':')[0]+'</span>';}).join('')+'<span class="tag">+'+(v.nodes.length-4)+'</span></div><button class="btn sm primary mt14" style="width:100%">'+T('act_use')+'</button></div></div>';}).join('');
    return head(T('tpl_title'),T('tpl_desc'))+'<div class="tpl-grid stagger">'+cards+'</div>';
  };
  INIT.templates=function(root){var T=C().T;root.querySelectorAll('.tpl-card .btn').forEach(function(b){b.onclick=function(e){e.stopPropagation();C().toast(T('toast_template'));C().setView('flows');};});root.querySelectorAll('.tpl-card').forEach(function(c){c.onclick=function(){C().setView('flows');};});};

  /* ===================== CONVERSATIONS (inbox) ===================== */
  V.conversations=function(ctx){ var T=ctx.T, D=ctx.D;
    var ordered=D.conversations.map(function(c,i){return {c:c,i:i};}).sort(function(a,b){return b.c.time.localeCompare(a.c.time);});
    var list=ordered.map(function(item,k){var c=item.c;return '<div class="citem'+(k===0?' on':'')+'" data-i="'+item.i+'"><span class="av-s" style="background:'+c.color+';margin:0">'+c.in+'</span><div class="cm"><div class="cn"'+(c.unread?' style="font-weight:700"':'')+'>'+c.name+' <span class="flag '+c.lang+'">'+c.lang.toUpperCase()+'</span></div><div class="cp">'+c.msgs[c.msgs.length-1].t+'</div></div><div style="text-align:right"><div class="ct">'+c.time+(c.unread?' <span style="width:8px;height:8px;border-radius:50%;background:var(--accent);display:inline-block"></span>':'')+'</div>'+(c.status==='asesor'?'<span class="flag" style="background:var(--coral);color:#fff;margin-top:4px;display:inline-block">'+T('inbox_advisor').toLowerCase()+'</span>':'')+'</div></div>';}).join('');
    var nAdv=D.conversations.filter(function(c){return c.status==='asesor';}).length, nAll=D.conversations.length;
    return '<div class="inbox">'+
      '<div class="clist"><div class="clh"><span class="filter on" data-f="all">'+T('inbox_all')+' <b class="mono" style="font-weight:600">'+nAll+'</b></span><span class="filter" data-f="bot">'+T('inbox_bot')+' <b class="mono" style="font-weight:600">'+(nAll-nAdv)+'</b></span><span class="filter" data-f="asesor">'+T('inbox_advisor')+' <b class="mono" style="font-weight:600">'+nAdv+'</b></span></div><div id="clItems">'+list+'<div id="clEmpty" class="hide" style="padding:30px 16px;text-align:center;color:var(--faint);font-size:12.5px">'+icon('chat','var(--faint)',22)+'<div class="mt8">'+T('inbox_empty_filter')+'</div></div></div></div>'+
      '<div class="thread" id="thread"></div></div>';
  };
  INIT.conversations=function(root){
    var T=C().T, D=window.DATA;
    function render(i){
      var c=D.conversations[i];
      var msgs=c.msgs.map(function(m){
        if(m.r==='sys') return '<div class="sysline">'+icon('refresh','currentColor',14)+' '+m.t+'</div>';
        if(m.r==='tool') return '<div class="tool-call"><div class="tc-head"><span class="tc-ic">🔧</span><span class="mono" style="font-weight:600">'+m.tool+'</span><span class="tc-ep">'+m.endpoint+'</span></div><div class="tc-body"><div class="tc-req">→ '+esc(m.req)+'</div><div class="tc-res">← '+esc(m.res)+'</div></div></div>';
        return '<div class="msg '+m.r+'">'+m.t+(m.m?'<div class="mt">'+m.m+(m.by?' · '+m.by:'')+'</div>':'')+'</div>';
      }).join('');
      var assigned=c.assigned?('<span class="pill coral">'+icon('headset','currentColor',13)+' '+T('conv_assigned')+' '+c.assigned+'</span>'):('<button class="btn sm" id="assignBtn">'+icon('headset','currentColor',14)+' '+T('conv_assign')+'</button>');
      root.querySelector('#thread').innerHTML=
        '<div class="th-head"><span class="av-s" style="background:'+c.color+'">'+c.in+'</span><div style="flex:1"><div style="font-weight:600">'+c.name+'</div><div class="muted" style="font-size:12px">'+c.ch+' · '+c.lang.toUpperCase()+'</div></div>'+assigned+'</div>'+
        '<div class="th-msgs">'+msgs+'</div>'+
        '<div class="th-foot"><input class="fakeinput" id="thInput" placeholder="'+T('conv_input_ph')+'" style="outline:none;color:var(--ink);font-family:inherit"><button class="btn primary" id="thSend">'+icon('send','currentColor',15)+'</button></div>';
      var ab=root.querySelector('#assignBtn'); if(ab) ab.onclick=function(){C().toast(T('toast_assigned'));D.conversations[i].assigned='Raúl Ávila';D.conversations[i].status='asesor';render(i);};
      function sendMsg(){var inp=root.querySelector('#thInput');if(!inp||!inp.value.trim())return;c.msgs.push({r:'b',t:inp.value,m:'ahora',by:c.assigned||'Tú'});render(i);}
      var sb=root.querySelector('#thSend'); if(sb) sb.onclick=sendMsg;
      var ti=root.querySelector('#thInput'); if(ti) ti.onkeydown=function(e){if(e.key==='Enter')sendMsg();};
      if(c.unread){c.unread=false;var it=root.querySelector('#clItems .citem[data-i="'+i+'"] .cn');if(it)it.style.fontWeight='600';}
      var tm=root.querySelector('.th-msgs'); if(tm) tm.scrollTop=tm.scrollHeight;
    }
    root.querySelectorAll('#clItems .citem').forEach(function(it){it.onclick=function(){root.querySelectorAll('#clItems .citem').forEach(function(x){x.classList.remove('on');});it.classList.add('on');render(+it.dataset.i);};});
    root.querySelectorAll('.clh .filter').forEach(function(f){f.onclick=function(){root.querySelectorAll('.clh .filter').forEach(function(x){x.classList.remove('on');});f.classList.add('on');var k=f.dataset.f,vis=0;root.querySelectorAll('#clItems .citem').forEach(function(it){var c=D.conversations[+it.dataset.i];var show=k==='all'||(k==='asesor'&&c.status==='asesor')||(k==='bot'&&c.status!=='asesor');it.style.display=show?'':'none';if(show)vis++;});var em=root.querySelector('#clEmpty');if(em)em.classList.toggle('hide',vis>0);};});
    render(0);
  };

  /* ===================== ANALYTICS ===================== */
  V.analytics=function(ctx){ var T=ctx.T, D=ctx.D;
    var intents=D.intents.map(function(x){return '<div class="br"><div class="between"><span>'+x.n+'</span><b class="mono">'+x.v+'%</b></div><div class="track"><i style="width:'+x.v+'%;background:'+x.c+'"></i></div></div>';}).join('');
    var off=25, segs=D.languages.map(function(l){var s='<circle cx="21" cy="21" r="15.9" fill="none" stroke="'+l.c+'" stroke-width="7" stroke-dasharray="'+l.v+' '+(100-l.v)+'" stroke-dashoffset="'+off+'" stroke-linecap="butt"/>';off-=l.v;return s;}).join('');
    var legend=D.languages.map(function(l){return '<div class="between" style="gap:30px"><span class="legend"><i style="background:'+l.c+'"></i>'+l.n+'</span><b class="mono">'+l.v+'%</b></div>';}).join('');
    var funnel=D.funnel.map(function(f){return '<div class="fstep" style="width:'+f.w+'%"><span>'+f.n+'</span><span class="n">'+f.v.toLocaleString('es')+'</span></div>';}).join('');
    var obs=D.observability.map(function(o){return '<div class="toolrow"><span class="muted">'+o.label+'</span><b class="mono" style="color:'+(o.ok?'var(--accent)':'var(--danger)')+'">'+o.v+'</b></div>';}).join('');
    var kstats=[
      {n:D.funnel[0].v.toLocaleString('es'), l:T('kpi_convs'), ic:'chat', tint:'blue'},
      {n:Math.round(D.funnel[1].v/D.funnel[0].v*100)+'%', l:T('an_intents'), ic:'ai', tint:'green'},
      {n:Math.round(D.funnel[3].v/D.funnel[0].v*100)+'%', l:T('kpi_leads'), ic:'user', tint:'amber'},
      {n:''+D.funnel[4].v, l:T('kpi_handoffs'), ic:'headset', tint:'coral'}
    ].map(function(st){return '<div class="card stat"><div class="top"><div class="ic" style="background:'+TINTBG[st.tint]+'">'+icon(st.ic,TINT[st.tint])+'</div></div><div class="num">'+st.n+'</div><div class="lbl">'+st.l+'</div></div>';}).join('');
    return head(T('nav_analytics'),T('an_desc'))+
    '<div style="display:flex;gap:7px" class="mb18" id="anRange"><span class="filter on">'+T('rng_7d')+'</span><span class="filter">'+T('rng_30d')+'</span><span class="filter">'+T('rng_90d')+'</span></div>'+
    '<div class="stats stagger mb18">'+kstats+'</div>'+
    '<div class="grid-2 stagger mb18">'+
      '<div class="card pad"><h3 class="mb18">'+T('an_intents')+'</h3><div class="barlist">'+intents+'</div></div>'+
      '<div class="card pad"><h3 class="mb18">'+T('an_langs')+'</h3><div class="donut-wrap"><svg width="148" height="148" viewBox="0 0 42 42"><circle cx="21" cy="21" r="15.9" fill="none" stroke="var(--surface-2)" stroke-width="7"/>'+segs+'<text x="21" y="20" text-anchor="middle" style="font:600 6px var(--font-disp);fill:var(--ink)">1.284</text><text x="21" y="26" text-anchor="middle" style="font:400 3px var(--font);fill:var(--muted)">chats</text></svg><div style="display:flex;flex-direction:column;gap:10px">'+legend+'</div></div></div>'+
    '</div>'+
    '<div class="grid-2 stagger"><div class="card pad"><h3 class="mb18">'+T('an_funnel')+'</h3><div class="funnel">'+funnel+'</div></div>'+
      '<div class="card pad"><h3 class="mb18">'+T('an_obs')+'</h3>'+obs+'</div></div>';
  };

  INIT.analytics=function(root){root.querySelectorAll('#anRange .filter').forEach(function(f){f.onclick=function(){root.querySelectorAll('#anRange .filter').forEach(function(x){x.classList.remove('on');});f.classList.add('on');};});};

  /* ===================== KNOWLEDGE (RAG) ===================== */
  V.knowledge=function(ctx){ var T=ctx.T, D=ctx.D;
    var files=D.kbFiles.map(function(f){return '<div class="kb-file"><div class="kfi">'+icon('file','currentColor')+'</div><div style="flex:1"><div style="font-weight:600;font-size:13px">'+f.name+'</div><div class="muted" style="font-size:11.5px">'+f.size+' · '+f.chunks+' '+T('kb_chunks')+'</div></div>'+(f.status==='indexado'?'<span class="pill green">'+icon('check','currentColor',13)+' '+T('kb_indexed')+'</span>':'<span class="pill amber"><span class="typing" style="margin-right:3px"><i></i><i></i><i></i></span>'+T('kb_indexing')+'</span>')+'<span class="btn sm ghost">'+icon('trash','var(--muted)',15)+'</span></div>';}).join('');
    return head(T('kb_title'),T('kb_desc'))+
    '<div class="grid-2 stagger"><div><div class="dropzone mb18" id="kbDrop">'+icon('upload','var(--faint)',30)+'<div>'+T('kb_drop')+'</div><button class="btn sm primary mt14">'+T('kb_upload')+'</button></div>'+
      '<div class="card pad"><h3 class="mb14">'+T('kb_files')+'</h3><div style="display:flex;flex-direction:column;gap:9px">'+files+'</div></div></div>'+
      '<div class="card pad" style="height:fit-content"><h3 class="mb14">RAG</h3><div style="display:flex;flex-direction:column;gap:12px"><div class="between"><span class="muted">Embeddings</span><b>pgvector</b></div><div class="between"><span class="muted">Modelo</span><b class="mono">text-embedding-3</b></div><div class="between"><span class="muted">'+T('kb_total_chunks')+'</span><b class="mono">224</b></div><div class="between"><span class="muted">Top-K</span><b class="mono">5</b></div><div class="reuse-note">'+icon('info','currentColor',16)+'<div>'+T('kb_grounding')+'</div></div></div></div></div>';
  };
  INIT.knowledge=function(root){var T=C().T;var d=root.querySelector('#kbDrop');if(d){d.onclick=function(){C().toast(T('toast_kb'));};d.querySelector('.btn').onclick=function(e){e.stopPropagation();C().toast(T('toast_kb'));};}};

  /* ===================== AI ===================== */
  V.ai=function(ctx){ var T=ctx.T, D=ctx.D, t=D.tenants[ctx.state.tenant];
    var provider = /OpenAI|GPT/i.test(t.llm) ? 'OpenAI · gpt-4o-mini' : (/DeepSeek/i.test(t.llm) && !/Claude/i.test(t.llm) ? 'DeepSeek · deepseek-chat' : 'Claude · claude-3-5-sonnet');
    var fallback = /DeepSeek/i.test(t.llm) && !/^DeepSeek/i.test(t.llm) ? 'DeepSeek · deepseek-chat' : T('ai_no_fallback');
    var keyMode = t.ownKey ? T('ai_key_client') : T('ai_key_agency');
    var ownerPill = t.ownKey ? '<span class="pill blue">'+T('ai_key_client')+'</span>' : '<span class="pill green">'+T('ai_key_agency')+'</span>';
    var secretPrefix = t.name.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
    var secretRows=[
      {name:'OPENAI_API_KEY', provider:'OpenAI', ref:'secret://'+secretPrefix+'/openai_api_key', mask:'sk-proj-•••••••••7c9', active:/OpenAI|GPT/i.test(t.llm), owner:t.ownKey},
      {name:'ANTHROPIC_API_KEY', provider:'Claude', ref:'secret://'+secretPrefix+'/anthropic_api_key', mask:'sk-ant-•••••••••3f2', active:/Claude/i.test(t.llm), owner:false},
      {name:'DEEPSEEK_API_KEY', provider:'DeepSeek', ref:'secret://'+secretPrefix+'/deepseek_api_key', mask:'sk-•••••••••a91', active:/DeepSeek/i.test(t.llm), owner:t.ownKey},
      {name:'WHATSAPP_TOKEN', provider:'WhatsApp', ref:'secret://'+secretPrefix+'/whatsapp_token', mask:'EAAG•••••••••', active:true, owner:true},
      {name:'TELEGRAM_BOT_TOKEN', provider:'Telegram', ref:'secret://'+secretPrefix+'/telegram_bot_token', mask:'bot•••••••••:AAG', active:true, owner:true}
    ];
    var rows=secretRows.map(function(s){return '<div class="secret-row '+(s.active?'on':'off')+'"><div><span class="mono">'+s.name+'</span><small>'+s.ref+'</small></div><span class="tag">'+s.provider+'</span><span class="muted mono">'+s.mask+'</span><span class="pill '+(s.owner?'blue':'gray')+'">'+(s.owner?T('ai_key_client_short'):T('ai_key_agency_short'))+'</span><span class="pill '+(s.active?'green':'gray')+'">'+(s.active?T('st_active'):T('st_paused'))+'</span></div>';}).join('');
    var capabilityCards=[
      {ic:'mic', title:T('cap_audio'), body:T('cap_audio_desc'), tag:T('cap_status_f1'), cls:'green'},
      {ic:'calendar', title:T('cap_booking'), body:T('cap_booking_desc'), tag:T('cap_status_tool'), cls:'blue'},
      {ic:'headset', title:T('cap_assign'), body:T('cap_assign_desc'), tag:T('cap_status_ready'), cls:'coral'},
      {ic:'globe', title:T('cap_language'), body:T('cap_language_desc'), tag:T('cap_status_ready'), cls:'green'}
    ].map(function(ca){return '<div class="cap-card '+ca.cls+'"><div class="cap-ic">'+icon(ca.ic,'currentColor',18)+'</div><div><b>'+ca.title+'</b><span>'+ca.body+'</span><em>'+ca.tag+'</em></div></div>';}).join('');
    // tools vinculadas a APIs externas
    var allTools=[];
    var apis=t.externalApis||{};
    for(var ak in apis){ var a=apis[ak];
      a.endpoints.forEach(function(e){ allTools.push({api:a.name,base:a.baseUrl,method:e.method,path:e.path,tool:e.tool,desc:e.desc}); });
    }
    var toolRows=allTools.map(function(tl){
      var on = tl.tool!=='agendar_cita' && tl.tool!=='crear_operacion';
      return '<div class="tool-card"><div class="tool-card-h"><div class="tool-card-l">'+icon('plug','var(--accent)',16)+'<span><b>'+tl.tool+'</b><span class="muted" style="font-size:11px;display:block">'+tl.desc+'</span></span></div><span class="sw '+(on?'':'off')+'"></span></div><div class="tool-card-b"><span class="mth '+tl.method.toLowerCase()+'">'+tl.method+'</span><span class="mono" style="font-size:11px;color:var(--muted);margin-left:6px">'+esc(tl.path)+'</span><span class="pill gray" style="margin-left:auto;font-size:9.5px">'+tl.api+'</span></div></div>';
    }).join('') || '<div class="info-note" style="margin:0">'+icon('info','var(--blue)',16)+'<div>'+T('ai_no_tools')+'</div></div>';
    var apiCards=[];
    for(var ak2 in apis){ var ap=apis[ak2];
      apiCards.push('<div class="ai-scope"><div style="flex:1"><span>'+ap.name+'</span><b class="mono" style="font-weight:500;font-size:13px;margin-top:2px">'+ap.baseUrl+'</b></div><span class="pill gray" style="font-size:9.5px">'+ap.auth+'</span><span class="mono" style="color:var(--faint);font-size:11px">'+ap.token+'</span></div>');
    }
    return head(T('nav_ai'),T('ai_desc'))+
    '<div class="info-note mb18">'+icon('shield','var(--blue)',16)+'<div>'+T('ai_tenant_note')+' <b>'+t.name+'</b>. <span class="mono">tenant_id</span> → <span class="mono">provider</span> → <span class="mono">secret_ref</span>; '+T('ai_tenant_note_2')+'</div></div>'+
    '<div class="grid-2 stagger">'+
      '<div class="card pad"><h3 class="mb18">'+T('ai_behavior')+'</h3>'+
        '<div class="ai-scope"><div><span>'+T('ai_current_tenant')+'</span><b>'+t.name+'</b></div>'+ownerPill+'</div>'+
        '<div class="fld"><label>'+T('ai_provider')+'</label><div class="select">'+provider+' '+icon('chev','var(--muted)',15)+'</div></div>'+
        '<div class="fld"><label>'+T('ai_fallback')+'</label><div class="select">'+fallback+' '+icon('chev','var(--muted)',15)+'</div></div>'+
        '<div class="fld"><label>'+T('ai_key_mode')+'</label><div class="seg"><button class="'+(!t.ownKey?'on':'')+'">'+T('ai_key_agency')+'</button><button class="'+(t.ownKey?'on':'')+'">'+T('ai_key_client')+'</button></div><div class="help">'+T('ai_key_mode_help')+'</div></div>'+
        '<div class="fld"><label>'+T('ai_temp')+' · 0.7</label><div class="slider"><i></i><b></b></div></div>'+
        '<div class="fld" style="margin-bottom:0"><label>'+T('ai_langs')+'</label><div class="chips"><span class="pill green">'+T('lang_detect_same')+'</span><span class="pill gray">ES</span><span class="pill gray">PT</span><span class="pill gray">EN</span></div></div></div>'+
      '<div class="card pad"><h3 class="mb18">'+T('ai_capabilities')+'</h3><div class="cap-grid">'+capabilityCards+'</div>'+
        '<h4 style="font-size:13px;margin:16px 0 8px">'+T('ai_prompt')+'</h4><textarea class="ta" rows="5">Eres el asistente de Brasper. Si el usuario envía audio, primero transcribe y entiende la intención. Detecta el idioma del usuario y responde en ese mismo idioma. Para citas, consulta disponibilidad antes de confirmar. Si hay riesgo, baja confianza o pedido de humano, asigna a un asesor.</textarea>'+
        '<h4 style="font-size:13px;margin:16px 0 8px">'+T('ai_tools')+' — <span class="muted" style="font-weight:400;font-size:12px">'+T('ai_tools_sub')+'</span></h4>'+
        '<div class="tool-list">'+toolRows+'</div>'+
        '<div class="reuse-note mt14">'+icon('refresh','currentColor',16)+'<div>'+T('reuse_tools')+' — el agente IA decide qué tool llamar según la conversación</div></div></div>'+
    '</div>'+
    '<div class="card pad mt18"><div class="between mb14"><h3>'+icon('plug','var(--ink)',18)+' '+T('ai_apis_title').replace('{name}',t.name)+'</h3><button class="btn sm" id="aiAddApi">'+icon('plus','currentColor',14)+' '+T('ai_add_api')+'</button></div>'+
      apiCards.join('')+
      '<div class="reuse-note mt14">'+icon('info','currentColor',16)+'<div>'+T('ai_discover_note')+'</div></div></div>'+
    '<div class="card pad mt18"><div class="between mb14"><h3>'+icon('lock','var(--ink)',18)+' '+T('ai_secrets')+'</h3><button class="btn sm primary" id="aiRotate">'+icon('key','currentColor',14)+' '+T('ai_add_key')+'</button></div><p class="muted" style="font-size:13px;margin:0 0 14px">'+T('ai_secrets_desc')+'</p>'+
      '<div class="secret-head"><span>'+T('sh_secret')+'</span><span>'+T('sh_provider')+'</span><span>'+T('sh_value')+'</span><span>'+T('sh_owner')+'</span><span>'+T('sh_status')+'</span></div>'+rows+
      '<div class="reuse-note mt14">'+icon('info','currentColor',16)+'<div>'+T('ai_secret_rule')+'</div></div></div>';
  };
  INIT.ai=function(root){var T=C().T;root.querySelectorAll('.sw').forEach(function(s){s.onclick=function(){s.classList.toggle('off');};});var b=root.querySelector('#aiRotate');if(b)b.onclick=function(){C().toast(T('ai_key_toast'));};root.querySelectorAll('.seg button').forEach(function(b){b.onclick=function(){C().toast(T('toast_saved'));};});var ab=root.querySelector('#aiAddApi');if(ab)ab.onclick=function(){C().toast(T('toast_add_api'));};};

  /* ===================== CHANNELS ===================== */
  V.channels=function(ctx){ var T=ctx.T, D=ctx.D, WT=D.waTemplates, tn=D.tenants[ctx.state.tenant], slug=tn.name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
    var secretPrefix = tn.name.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
    var tgBot = tn.tg || '@'+slug+'_bot';
    var tgId = tn.tgid || 'pendiente';
    var tgWebhook = 'https://api.cauce.ai/webhooks/telegram/'+slug;
    var tgSecret = 'secret://'+secretPrefix+'/telegram_bot_token';
    var wtRows=D.waTemplateList.map(function(t){var sc=t.status==='APPROVED'?['green','st_approved']:(t.status==='PENDING'?['amber','st_pending']:(t.status==='REJECTED'?['coral','st_rejected']:['gray','st_paused']));return '<tr><td class="mono" style="font-size:12px">'+t.name+'</td><td><span class="tag">'+t.cat+'</span></td><td class="muted">'+t.lang+'</td><td><span class="pill '+sc[0]+'">'+T(sc[1])+'</span></td></tr>';}).join('');
    var wtEx=WT.example, wtExBody=esc(wtEx.body).replace(/\{\{(\d+)\}\}/g,'<span class="wt-var">{{$1}}</span>');
    var waSection='<div class="card pad mt18"><div class="between mb8"><h3>'+icon('whatsapp','#25D366',18)+' '+T('wt_title')+'</h3><button class="btn sm primary" id="wtNew">'+icon('plus','currentColor',14)+' '+T('wt_new')+'</button></div>'+
      '<div class="info-note mb14">'+icon('info','var(--blue)',16)+'<div>'+WT.why+'</div></div>'+
      '<div class="grid-2 mb14"><div><div class="sub mb8">'+T('wt_title')+'</div><table class="tbl"><thead><tr><th>'+T('th_template')+'</th><th>'+T('th_category')+'</th><th>'+T('th_lang')+'</th><th>'+T('th_status')+'</th></tr></thead><tbody>'+wtRows+'</tbody></table>'+
        '<div style="display:flex;flex-direction:column;gap:7px;margin-top:12px">'+WT.categories.map(function(c){return '<div style="font-size:12px;color:var(--muted)"><b style="color:var(--ink)">'+c.name+':</b> '+c.desc+'</div>';}).join('')+'</div></div>'+
        '<div><div class="sub mb8">'+T('wt_example')+'</div><div class="wt-card"><div class="between"><b class="mono" style="font-size:12px">'+wtEx.name+'</b><span class="tag">'+wtEx.category+' · '+wtEx.language+'</span></div><div class="wt-body">'+wtExBody+'</div><div style="display:flex;flex-direction:column;gap:2px;margin-top:9px">'+wtEx.vars.map(function(v){return '<div class="muted" style="font-size:11.5px">'+esc(v)+'</div>';}).join('')+'</div></div></div></div>'+
      '<div class="grid-2e"><div class="reuse-note" style="background:var(--surface-2);border-color:var(--line);color:var(--ink-2)">'+icon('check','var(--accent)',16)+'<div><b>'+T('wt_approval')+':</b> '+WT.approval+'</div></div>'+
        '<div class="reuse-note" style="background:var(--surface-2);border-color:var(--line);color:var(--ink-2)">'+icon('send','var(--accent)',16)+'<div><b>'+T('wt_sending')+':</b> '+esc(WT.sending)+'</div></div></div></div>';
    return head(T('ch_title'),T('ch_desc'))+
    '<div class="grid-2e stagger">'+
      '<div class="card ch"><div class="chh"><div class="chlogo" style="background:#25D366">'+icon('whatsapp','#fff',26)+'</div><div><h3>'+T('ch_wa')+'</h3><span class="muted" style="font-size:12.5px">'+T('ch_wa_sub')+'</span></div><span class="pill green" style="margin-left:auto">'+icon('check','currentColor',13)+' '+T('st_connected')+'</span></div>'+
        '<div style="display:flex;flex-direction:column;gap:9px;font-size:13px"><div class="between"><span class="muted">'+T('ch_number')+'</span><b class="mono">'+tn.wa+'</b></div><div class="between"><span class="muted">'+T('ch_pnid')+'</span><b class="mono">'+tn.pnid+'</b></div><div class="between"><span class="muted">'+T('ch_flow_assigned')+'</span><span class="pill green">v3 · '+T('st_published')+'</span></div></div>'+
        '<button class="btn mt14" style="width:100%" id="waManage">'+icon('refresh','currentColor',15)+' '+T('ch_connect_wa')+'</button></div>'+
      '<div class="card ch"><div class="chh"><div class="chlogo" style="background:var(--blue)">'+icon('chat','#fff',26)+'</div><div><h3>'+T('ch_webchat')+'</h3><span class="muted" style="font-size:12.5px">'+T('ch_webchat_sub')+'</span></div><span class="pill green" style="margin-left:auto">'+icon('check','currentColor',13)+' '+T('st_active')+'</span></div>'+
        '<div class="muted" style="font-size:12.5px;margin-bottom:8px">'+T('ch_snippet')+'</div><div class="code"><span class="k">&lt;script</span> src=<span class="s">"https://cdn.cauce.ai/widget/v1/loader.js"</span>\n        data-tenant=<span class="s">"'+slug+'"</span><span class="k">&gt;&lt;/script&gt;</span></div></div>'+
      '<div class="card ch"><div class="chh"><div class="chlogo telegram">'+icon('telegram','#fff',26)+'</div><div><h3>'+T('ch_tg')+'</h3><span class="muted" style="font-size:12.5px">'+T('ch_tg_sub')+'</span></div><span class="pill blue" style="margin-left:auto">'+T('st_configured')+'</span></div>'+
        '<div class="channel-fields"><div class="between"><span class="muted">'+T('ch_bot')+'</span><b class="mono">'+tgBot+'</b></div><div class="between"><span class="muted">'+T('ch_bot_id')+'</span><b class="mono">'+tgId+'</b></div><div class="between"><span class="muted">'+T('ch_secret_ref')+'</span><b class="mono">'+tgSecret+'</b></div><div class="between"><span class="muted">'+T('ch_webhook')+'</span><b class="mono">'+tgWebhook.replace('https://api.cauce.ai','')+'</b></div></div>'+
        '<div class="reuse-note mt14">'+icon('refresh','currentColor',16)+'<div>'+T('ch_tg_note')+'</div></div>'+
        '<button class="btn mt14" style="width:100%" id="tgManage">'+icon('telegram','currentColor',15)+' '+T('ch_connect_tg')+'</button></div>'+
      '<div class="card ch" style="border-style:dashed;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--muted);min-height:150px">'+icon('instagram','var(--muted)',26)+'<b>Instagram / Messenger</b><span style="font-size:12px">'+T('st_soon')+'</span></div>'+
    '</div>'+waSection;
  };
  INIT.channels=function(root){ var T=C().T;
    root.querySelector('#waManage').onclick=function(){window.openFacebookWizard();};
    var tg=root.querySelector('#tgManage'); if(tg) tg.onclick=function(){
      var D=window.DATA, tn=D.tenants[C().state.tenant], slug=tn.name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
      var secretPrefix=tn.name.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
      var webhook='https://api.cauce.ai/webhooks/telegram/'+slug;
      C().modal('<div class="modal-head">'+icon('telegram','#229ED9',20)+'<h3>'+T('tg_wizard_title')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div>'+
        '<div class="modal-body"><div class="grid-2e" style="gap:12px"><div class="fld"><label>'+T('tg_username_label')+'</label><div class="input"><input value="'+(tn.tg||('@'+slug+'_bot'))+'"></div></div><div class="fld"><label>'+T('tg_token_label')+'</label><div class="input"><input value="bot•••••••••:AAG"></div></div></div>'+
        '<div class="tg-steps"><div>'+icon('check','var(--accent)',15)+'<span>'+T('tg_step_botfather')+'</span></div><div>'+icon('lock','var(--accent)',15)+'<span>'+T('tg_step_secret')+' <b class="mono">secret://'+secretPrefix+'/telegram_bot_token</b></span></div><div>'+icon('cast','var(--accent)',15)+'<span>'+T('tg_step_webhook')+' <b class="mono">'+webhook+'</b></span></div><div>'+icon('ai','var(--accent)',15)+'<span>'+T('tg_step_test')+'</span></div></div>'+
        '<div class="info-note" style="margin-bottom:0">'+icon('info','var(--blue)',16)+'<div>'+T('tg_backend_note')+'</div></div></div>'+
        '<div class="modal-foot"><button class="btn" onclick="window.__cauce.closeModal()">'+T('act_cancel')+'</button><button class="btn primary" id="tgSave">'+T('act_save')+'</button></div>');
      document.getElementById('tgSave').onclick=function(){ C().closeModal(); C().toast(T('tg_done')); };
    };
    var wn=root.querySelector('#wtNew'); if(wn) wn.onclick=function(){
      C().modal('<div class="modal-head">'+icon('whatsapp','#25D366',20)+'<h3>'+T('wt_new')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div>'+
        '<div class="modal-body"><div class="grid-2e" style="gap:12px"><div class="fld"><label>'+T('th_category')+'</label><div class="select">UTILITY '+icon('chev','var(--muted)',15)+'</div></div><div class="fld"><label>'+T('th_lang')+'</label><div class="select">es '+icon('chev','var(--muted)',15)+'</div></div></div>'+
        '<div class="fld"><label>'+T('wt_name')+'</label><div class="input"><input value="recordatorio_cita"></div></div>'+
        '<div class="fld"><label>'+T('wt_body')+'</label><textarea class="ta" rows="3">Hola {{1}}, te recordamos tu cita el {{2}} a las {{3}}.</textarea></div>'+
        '<div class="info-note" style="margin-bottom:0">'+icon('info','var(--blue)',16)+'<div>'+T('wt_vars_note')+'</div></div></div>'+
        '<div class="modal-foot"><button class="btn" onclick="window.__cauce.closeModal()">'+T('act_cancel')+'</button><button class="btn primary" id="wtSend">'+T('wt_submit')+'</button></div>');
      document.getElementById('wtSend').onclick=function(){ C().closeModal(); C().toast(T('toast_wt_sent')); };
    };
  };

  /* ===================== INTEGRATIONS (esenciales + API genérica + embebidos) ===================== */
  V.integrations=function(ctx){ var T=ctx.T, D=ctx.D;
    var core=D.plugins.filter(function(p){return D.coreKeys.indexOf(p.key)>=0;});
    var coreCards=core.map(function(p){return pluginCard(D,T,p);}).join('');
    var ga=D.genericApi;
    var eps=ga.endpoints.map(function(e){return '<div class="ep-row"><span class="mth '+e.method.toLowerCase()+'">'+e.method+'</span><div style="flex:1;min-width:0"><div class="ep-path">'+esc(e.path)+'</div><div class="ep-purpose">'+e.purpose+'</div></div><span class="ep-var">→ '+e.out+'</span></div>';}).join('');
    var embeds=D.embeds.map(function(em,i){return '<div class="card pad-s"><div class="between mb8"><b style="font-size:13px">'+em.name+'</b><button class="btn sm copy-snip" data-i="'+i+'">'+icon('copy','currentColor',14)+' '+T('embed_copy')+'</button></div><div class="code-wrap"><pre class="code" style="margin:0">'+esc(em.snippet)+'</pre></div></div>';}).join('');
    return head(T('int_title'),T('int_desc'))+
      '<div class="between mb8"><h3>'+T('int_essential')+'</h3><span class="pill green">'+T('managed_tag')+'</span></div>'+
      '<p class="muted" style="font-size:13px;margin:0 0 14px">'+T('int_essential_desc')+'</p>'+
      '<div class="mkt-grid stagger mb24" id="coreGrid">'+coreCards+'</div>'+
      '<div class="card pad mb24"><div class="between mb8"><h3>'+icon('plug','var(--ink)',18)+' '+T('int_api')+'</h3><span class="pill green">JSON · por tenant</span></div>'+
        '<p class="muted" style="font-size:13px;margin:0 0 14px">'+T('int_api_desc')+'</p>'+
        '<div class="api-head"><div style="flex:1;min-width:240px"><label class="sub" style="display:block;margin-bottom:5px">'+T('api_baseurl')+'</label><div class="input"><input value="'+ga.baseUrl+'"></div></div>'+
          '<div style="width:240px"><label class="sub" style="display:block;margin-bottom:5px">'+T('api_auth')+'</label><div class="select">'+ga.auth+' '+icon('chev','var(--muted)',15)+'</div></div></div>'+
        '<div class="between mb8" style="margin-top:4px"><span class="sub">'+T('api_endpoints')+' · '+T('api_purpose')+'</span><button class="btn sm" id="addEp">'+icon('plus','currentColor',14)+' '+T('api_add')+'</button></div>'+
        '<div style="display:flex;flex-direction:column;gap:8px" id="epList">'+eps+'</div>'+
        '<div class="reuse-note mt14">'+icon('info','currentColor',16)+'<div>'+ga.note+'</div></div></div>'+
      '<div class="mb14"><h3>'+T('int_embed')+'</h3><p class="muted" style="font-size:13px;margin:4px 0 0">'+T('int_embed_desc')+'</p></div>'+
      '<div class="grid-3 stagger">'+embeds+'</div>';
  };
  INIT.integrations=function(root){ var T=C().T, D=window.DATA;
    root.querySelectorAll('.copy-snip').forEach(function(b){ b.onclick=function(){ copyText(D.embeds[+b.dataset.i].snippet); C().toast(T('embed_copied')); }; });
    function wireEnable(scope){ scope.querySelectorAll('.mkt-card .btn').forEach(function(b){ b.onclick=function(){ C().toast(T('toast_plugin')); }; }); }
    wireEnable(root);
    root.querySelector('#addEp').onclick=function(){
      C().modal('<div class="modal-head">'+icon('plug','var(--accent)',20)+'<h3>'+T('api_add')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div>'+
        '<div class="modal-body"><div class="grid-2e" style="gap:12px"><div class="fld"><label>'+T('th_method')+'</label><div class="select">GET '+icon('chev','var(--muted)',15)+'</div></div><div class="fld"><label>'+T('api_outvar')+'</label><div class="input"><input placeholder="resultado"></div></div></div>'+
        '<div class="fld"><label>'+T('th_path')+'</label><div class="input"><input placeholder="/recurso/{{id}}"></div></div>'+
        '<div class="fld" style="margin-bottom:0"><label>'+T('api_purpose')+'</label><textarea class="ta" rows="2" placeholder="Para qué sirve este endpoint (también guía al LLM para saber cuándo llamarlo)…"></textarea></div></div>'+
        '<div class="modal-foot"><button class="btn" onclick="window.__cauce.closeModal()">'+T('act_cancel')+'</button><button class="btn primary" id="saveEp">'+T('act_save')+'</button></div>');
      document.getElementById('saveEp').onclick=function(){ C().closeModal(); C().toast(T('toast_endpoint')); };
    };
  };

  /* ===================== BILLING ===================== */
  V.billing=function(ctx){ var T=ctx.T, D=ctx.D, B=D.billing, t=D.tenants[ctx.state.tenant];
    var usage=B.usage.map(function(u){var pct=Math.round(u.used/u.total*100);var cls=pct>85?'over':(pct>65?'warn':'');return '<div class="mb14"><div class="between" style="font-size:13px;margin-bottom:5px"><span class="muted">'+u.label+'</span><b class="mono">'+(u.used.toLocaleString('es'))+u.unit+' / '+(u.total.toLocaleString('es'))+u.unit+'</b></div><div class="ubar"><i class="'+cls+'" style="width:'+pct+'%"></i></div></div>';}).join('');
    var cost=B.costByModel.map(function(c){return '<div class="br"><div class="between" style="font-size:12.5px"><span>'+c.m+'</span><b class="mono">'+c.v+'%</b></div><div class="track"><i style="width:'+c.v+'%;background:'+c.c+'"></i></div></div>';}).join('');
    var inv=B.invoices.map(function(i){return '<tr><td><b>'+i.id+'</b></td><td class="muted">'+i.date+'</td><td class="mono">'+i.amount+'</td><td><span class="pill green">'+i.status+'</span></td></tr>';}).join('');
    return head(T('bill_title'),T('bill_desc'))+
    '<div class="grid-2 stagger mb18"><div class="card pad"><div class="between mb18"><h3>'+T('bill_usage')+'</h3><span class="pill green">'+T('plan_label')+' '+B.plan+'</span></div>'+usage+'<div class="info-note mt14">'+icon('info','var(--blue)',16)+'<div>'+T('meter_note')+'</div></div></div>'+
      '<div class="card pad"><h3 class="mb18">'+T('bill_cost')+'</h3><div class="barlist">'+cost+'</div><div class="between mt18" style="border-top:1px solid var(--line);padding-top:12px"><span class="muted">'+T('bill_month_total')+' · '+t.name+'</span><b class="mono" style="font-size:16px">US$ '+t.cost.toFixed(2).replace('.',',')+'</b></div></div></div>'+
    '<div class="grid-2 mb18"><div class="card pad"><h3 class="mb14">'+T('bill_margin')+' · '+t.name+'</h3>'+
      '<div class="between" style="padding:7px 0"><span class="muted">'+T('bill_fee')+'</span><b class="mono">US$ '+t.fee.toFixed(2)+'</b></div>'+
      '<div class="between" style="padding:7px 0;border-top:1px solid var(--line)"><span class="muted">'+T('ag_aicost')+' (LLM)</span><b class="mono" style="color:var(--coral)">− US$ '+t.cost.toFixed(2)+'</b></div>'+
      '<div class="between" style="padding:9px 0 0;border-top:1px solid var(--line)"><span style="font-weight:600">'+T('ag_margin')+'</span><b class="mono" style="color:var(--accent);font-size:17px">US$ '+(t.fee-t.cost).toFixed(2)+'</b></div></div>'+
      '<div class="card pad"><h3 class="mb8">'+T('bill_manual_t')+'</h3><div class="info-note" style="margin:0">'+icon('info','var(--blue)',16)+'<div>'+T('bill_manual')+'</div></div></div></div>'+
    '<div class="card pad"><h3 class="mb14">'+T('bill_invoices')+'</h3><div class="tblwrap"><table class="tbl"><thead><tr><th>'+T('th_invoice')+'</th><th>'+T('th_date')+'</th><th>'+T('th_amount')+'</th><th>'+T('th_state')+'</th></tr></thead><tbody>'+inv+'</tbody></table></div></div>';
  };

  /* ===================== TEAM & ROLES ===================== */
  V.team=function(ctx){ var T=ctx.T, D=ctx.D;
    var roleName={}; D.roles.forEach(function(r){roleName[r.key]=r.name;});
    var members=D.team.map(function(m){return '<tr><td><span class="av-s" style="background:'+m.color+'">'+m.in+'</span>'+m.name+'</td><td class="muted">'+m.email+'</td><td><span class="pill '+(m.role==='owner'?'green':(m.role==='agent'?'coral':(m.role==='billing'?'purple':'gray')))+'">'+roleName[m.role]+'</span></td><td style="text-align:right">'+icon('dots','var(--muted)',16)+'</td></tr>';}).join('');
    var roleCards=D.roles.map(function(r){return '<div class="role-card"><div class="ri">'+icon(r.icon,'currentColor')+'</div><div><div class="rn">'+r.name+'</div><div class="rd">'+r.desc+'</div></div></div>';}).join('');
    var S=ctx.state;
    var th=D.roles.map(function(r){return '<th'+(r.key===S.role?' class="hl"':'')+' style="white-space:nowrap">'+r.name+'</th>';}).join('');
    var rows=D.permissions.map(function(p){var tds=D.roles.map(function(r){var ok=D.matrix[r.key].indexOf(p.key)>=0;return '<td class="'+(ok?'yes':'no')+(r.key===S.role?' hl':'')+'">'+(ok?icon('check','currentColor',16):icon('x','currentColor',14))+'</td>';}).join('');return '<tr><td>'+p.name+'</td>'+tds+'</tr>';}).join('');
    return head(T('team_title'),T('team_desc'))+
    '<div class="card pad mb18"><div class="between mb14"><h3>'+T('team_members')+'</h3><button class="btn sm primary" id="inviteBtn">'+icon('plus','currentColor',14)+' '+T('act_invite')+'</button></div><div class="tblwrap"><table class="tbl"><thead><tr><th>'+T('th_member')+'</th><th>'+T('th_email')+'</th><th>'+T('th_role')+'</th><th></th></tr></thead><tbody>'+members+'</tbody></table></div></div>'+
    '<div class="card pad mb18"><h3 class="mb14">'+T('nav_team')+'</h3><div class="grid-2e" style="gap:12px">'+roleCards+'</div></div>'+
    '<div class="card pad"><h3 class="mb14">'+T('team_matrix')+' (RBAC)</h3><div class="tblwrap"><table class="matrix"><thead><tr><th>'+T('th_permission')+'</th>'+th+'</tr></thead><tbody>'+rows+'</tbody></table></div></div>';
  };
  INIT.team=function(root){var T=C().T;root.querySelector('#inviteBtn').onclick=function(){C().modal('<div class="modal-head">'+icon('users','var(--accent)',20)+'<h3>'+T('act_invite')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div><div class="modal-body"><div class="fld"><label>'+T('th_email')+'</label><div class="input"><input placeholder="persona@empresa.com"></div></div><div class="fld" style="margin-bottom:0"><label>'+T('th_role')+'</label><div class="select">'+(window.DATA.roles.filter(function(r){return r.key==='builder';})[0]||{}).name+' '+icon('chev','var(--muted)',15)+'</div></div></div><div class="modal-foot"><button class="btn" onclick="window.__cauce.closeModal()">'+T('act_cancel')+'</button><button class="btn primary" onclick="window.__cauce.closeModal();window.__cauce.toast(\''+T('toast_saved')+'\')">'+T('act_invite')+'</button></div>');};};

  /* ===================== SETTINGS ===================== */
  V.settings=function(ctx){ var T=ctx.T, D=ctx.D; var t=D.tenants[ctx.state.tenant];
    return head(T('nav_settings'),T('set_desc'))+
    '<div class="card pad mb18" style="max-width:700px"><h3 class="mb18">'+T('set_company')+'</h3>'+
      '<div class="fld"><label>'+T('set_name')+'</label><div class="input"><input value="'+t.name+'"></div></div>'+
      '<div class="fld"><label>'+T('set_subdomain')+'</label><div class="input"><input value="'+t.name.toLowerCase().replace(/ /g,'-')+'" style="text-align:right"><span class="pre">.cauce.ai</span></div></div>'+
      '<div class="fld" style="margin-bottom:0"><label>'+T('set_tz')+'</label><div class="select">America/Lima (GMT-5) '+icon('chev','var(--muted)',15)+'</div></div></div>'+
    '<div class="card pad mb18" style="max-width:700px"><div class="between mb14"><h3>'+icon('gear','var(--ink)',18)+' '+T('set_tech')+'</h3><span class="pill green">'+T('set_per_tenant')+'</span></div>'+
      '<div class="toolrow"><span class="muted">'+T('set_pnid')+'</span><b class="mono" style="font-size:12px">'+t.pnid+'</b></div>'+
      '<div class="toolrow"><span class="muted">'+T('set_watoken')+'</span><span class="muted mono" style="font-size:12px">EAAG•••••••</span></div>'+
      '<div class="toolrow"><span class="muted">'+T('set_llm')+'</span><b>'+t.llm+'</b></div>'+
      '<div class="toolrow"><span class="muted">'+T('set_llmkey')+'</span>'+(t.ownKey?'<span class="pill blue">'+T('set_ownkey')+'</span>':'<span class="muted mono" style="font-size:12px">sk-•••••••</span>')+'</div>'+
      '<div class="toolrow"><span class="muted">'+T('set_handoff')+'</span><b class="mono" style="font-size:12px">'+t.handoff+'</b></div>'+
      '<div class="toolrow"><span class="muted">'+T('set_redis')+'</span><b class="mono" style="font-size:12px">'+t.name.toLowerCase().replace(/ /g,'_')+':</b></div>'+
      '<div class="reuse-note mt14">'+icon('refresh','currentColor',16)+'<div>'+T('set_handoff_note')+'</div></div></div>'+
    '<div class="card pad mb18" style="max-width:700px"><div class="between mb14"><h3>'+icon('shield','var(--ink)',18)+' '+T('set_security')+'</h3><span class="pill green">RLS</span></div><p class="muted" style="font-size:13px;margin:0">'+T('set_rls_desc')+'</p></div>'+
    '<div class="card pad mb18" style="max-width:700px"><h3 class="mb8">'+T('set_pii')+'</h3><p class="muted" style="font-size:13px;margin:0 0 14px">'+T('set_pii_desc')+'</p><div class="fld" style="margin-bottom:0"><label>'+T('set_retention')+'</label><div class="select">180 días '+icon('chev','var(--muted)',15)+'</div></div></div>'+
    '<div class="card pad" style="max-width:700px;border-color:#e7c4be"><h3 class="mb8" style="color:var(--danger)">'+T('set_danger')+'</h3><div class="between"><span class="muted" style="font-size:13px">'+T('set_delete')+'</span><button class="btn danger">'+icon('trash','var(--danger)',15)+' '+T('set_delete')+'</button></div></div>';
  };
  INIT.settings=function(root){root.querySelectorAll('.card .btn.primary, .card .btn').forEach(function(b){});};

  /* ===================== ARCHITECTURE ===================== */
  V.architecture=function(ctx){ var T=ctx.T, D=ctx.D;
    var TAG=['',' reuse',' new']; // 0 normal, 1 reuse, 2 new
    var containers=(D.deploymentContainers||[]).map(function(c){return '<div class="arch-card"><div class="arch-card-head"><div><b class="mono">'+c.name+'</b><span>'+c.tech+'</span></div><em>'+c.status+'</em></div><p>'+c.body+'</p></div>';}).join('');
    var flow=(D.tenantApiFlow||[]).map(function(s){return '<div class="api-step"><b>'+s.title+'</b><span>'+s.body+'</span></div>';}).join('');
    var ai=(D.aiStack||[]).map(function(s){return '<div class="ai-piece"><b>'+icon('ai','var(--accent)',16)+' '+s.name+'</b><span>'+s.body+'</span></div>';}).join('');
    var layers=D.archLayers.map(function(L,idx){
      var items=L.items.map(function(it){var k=it[1];var cls='pill '+(k===1?'green':'gray');var rec=k===1?icon('refresh','currentColor',13)+' ':'';var add=k===2?' <span class="tag new" style="padding:0 5px">'+T('leg_added').split(' ')[0]+'</span>':'';return '<span class="'+cls+'">'+rec+it[0]+add+'</span>';}).join(' ');
      var box='<div class="card pad-s" style="'+(L.heart?'border:2px solid var(--border-accent);background:linear-gradient(90deg,var(--teal-soft),var(--surface) 55%);':'')+'display:flex;align-items:center;gap:14px;flex-wrap:wrap"><div style="min-width:150px"><div style="font-weight:600;display:flex;align-items:center;gap:7px">'+icon(L.ic,'var(--accent)',17)+L.l1+(L.heart?' <span class="pill green" style="font-size:10px">'+icon('refresh','currentColor',11)+' núcleo</span>':'')+'</div><div class="muted" style="font-size:11.5px">'+L.l2+'</div></div><div style="display:flex;gap:7px;flex-wrap:wrap;flex:1">'+items+'</div></div>';
      return box+(idx<D.archLayers.length-1?'<div style="text-align:center;color:var(--line-3);font-size:15px;line-height:16px">↓</div>':'');
    }).join('');
    return head(T('arch_title'),T('arch_desc'))+
    '<div class="legend mb18"><span><i style="background:var(--surface-3);border:1px solid var(--line-2)"></i>'+T('leg_new')+'</span><span><i style="background:#9FE1CB"></i>'+T('leg_reuse')+'</span><span><i style="background:#ecd49a"></i>'+T('leg_added')+'</span></div>'+
    '<div class="card pad mb18"><div class="between mb14"><div><span class="sub">Despliegue</span><h3>Contenedores del MVP</h3></div><span class="pill green">Docker Compose</span></div><div class="arch-card-grid">'+containers+'</div></div>'+
    '<div class="grid-2 mb18">'+
      '<div class="card pad"><div class="between mb14"><div><span class="sub">Multi-tenant</span><h3>Una API, varios clientes</h3></div><span class="pill green">FastAPI</span></div><div class="api-flow">'+flow+'</div></div>'+
      '<div class="card pad"><div class="between mb14"><div><span class="sub">Motor IA</span><h3>LangGraph como orquestador</h3></div><span class="pill green">Python</span></div><div class="ai-stack">'+ai+'</div></div>'+
    '</div>'+
    '<div style="display:flex;flex-direction:column;gap:0" class="stagger">'+layers+'</div>';
  };

  /* ===================== ROADMAP ===================== */
  V.roadmap=function(ctx){ var T=ctx.T, D=ctx.D;
    var lbl={now:T('rm_now'),build:T('rm_build'),later:T('rm_later')}, col={now:'coral',build:'green',later:'gray'};
    var cards=D.roadmap.map(function(p,i){return '<div class="rm-item '+p.type+'"><span class="rm-dot">'+i+'</span><div class="card pad"><div class="between mb8"><h3><span class="mono" style="color:var(--accent)">'+p.ph+'</span> · '+p.name+'</h3><span class="pill '+col[p.type]+'">'+lbl[p.type]+'</span></div>'+
      '<div class="muted" style="font-size:13px;line-height:1.55"><b style="color:var(--ink)">'+T('rm_deliver')+':</b> '+p.deliver+'</div>'+
      (p.gate&&p.gate!=='—'?'<div class="info-note mt14" style="margin-bottom:0">'+icon('shield','var(--blue)',16)+'<div><b>'+T('rm_gate')+':</b> '+p.gate+'</div></div>':'')+'</div></div>';}).join('');
    return head(T('rm_title'),T('rm_desc'))+'<div class="rm-rail stagger">'+cards+'</div>';
  };

  window.VIEWS=V; window.VIEW_INIT=INIT;

  /* ===================== BOT PREVIEW (drawer) — con modo REAL =====================
     Si el backend real (app/ · FastAPI) está corriendo en localhost:8001,
     el chat responde DESDE EL BOT REAL vía POST /consulta-webchat.
     Si no, cae a la simulación y lo dice honestamente. */
  var BP_BASE='http://localhost:8001';
  window.openBotPreview=function(){
    var T=C().T, real=false, sessionId='maqueta-'+Math.random().toString(36).slice(2,9);
    C().drawer(
      '<div class="drawer-head">'+icon('eye','var(--accent)',18)+'<b>'+T('act_preview')+'</b><span class="x" id="bpClose">'+icon('x','var(--muted)',18)+'</span></div>'+
      '<div class="bp-status demo" id="bpStatus"><span class="bdot"></span><b id="bpStTitle">'+T('bp_demo')+'</b><span class="mono" id="bpStNote"></span></div>'+
      '<div class="botprev"><div class="bp-bar"><div class="ava">'+icon('chat','#fff',16)+'</div><div><div>Brasper</div><div style="font-size:11px;opacity:.8;font-weight:400">'+T('st_online')+' · Agente IA</div></div></div>'+
      '<div class="bp-msgs" id="bpMsgs"><div class="bp-bubble b">'+T('bp_hello')+'</div></div>'+
      '<div class="bp-quick" id="bpQuick"><button data-q="Quiero enviar 500 soles a Brasil">'+T('bp_quote')+'</button><button data-q="¿Cuáles son los requisitos?">'+T('bp_reqs')+'</button><button data-q="Quiero hablar con un asesor">'+T('bp_advisor')+'</button></div>'+
      '<div class="bp-input"><input id="bpInput" placeholder="'+T('conv_input_ph')+'"><button class="bp-send" id="bpSend">'+icon('send','#fff',18)+'</button></div></div>');
    var msgs=document.getElementById('bpMsgs');
    function setStatus(isReal){
      real=isReal;
      var st=document.getElementById('bpStatus'); if(!st)return;
      st.className='bp-status '+(isReal?'real':'demo');
      document.getElementById('bpStTitle').textContent=isReal?T('bp_real'):T('bp_demo');
      document.getElementById('bpStNote').textContent=isReal?T('bp_real_note'):T('bp_demo_note');
    }
    setStatus(false);
    // sonda: ¿está el backend real encendido?
    try{
      var probeCtl=new AbortController(); setTimeout(function(){probeCtl.abort();},2500);
      fetch(BP_BASE+'/openapi.json',{signal:probeCtl.signal}).then(function(r){ if(r.ok) setStatus(true); }).catch(function(){});
    }catch(e){}
    function add(cls,html){var b=document.createElement('div');b.className='bp-bubble '+cls;b.innerHTML=html;msgs.appendChild(b);msgs.scrollTop=msgs.scrollHeight;return b;}
    function simReply(text){
      var t=text.toLowerCase(), r;
      var isEn=/\b(hello|hi|what|fees|requirements|advisor|agent|appointment|book|schedule|audio|voice)\b/.test(t);
      var isPt=/\b(olá|ola|quais|requisitos|assessor|atendente|agendar|marcar|áudio|audio|voz)\b/.test(t);
      if(/audio|áudio|voz|voice/.test(t)) r=isEn?'I can understand voice notes: first I transcribe the audio, then I detect the intent and answer in English.':(isPt?'Posso entender áudios: primeiro transcrevo, depois detecto a intenção e respondo em português.':'Puedo entender audios: primero transcribo, luego detecto la intención y respondo en el mismo idioma.');
      else if(/cita|agendar|reserv|appointment|book|schedule|marcar/.test(t)) r=isEn?'Sure. I can check available slots and book an appointment. What day works for you?':(isPt?'Claro. Posso consultar horários disponíveis e marcar uma consulta. Qual dia funciona para você?':'Claro. Puedo consultar disponibilidad y reservar una cita. ¿Qué día te conviene?');
      else if(/asesor|persona|humano|agente|advisor|agent|assessor|atendente/.test(t)) r=isEn?'Of course. I can assign this conversation to a human advisor. Could you confirm your full name?':(isPt?'Claro. Posso atribuir esta conversa a um assessor humano. Pode confirmar seu nome completo?':'Con gusto. Puedo asignar esta conversación a un asesor humano. ¿Me confirmas tu nombre completo?');
      else if(/requisit|documento|requirements/.test(t)) r=isEn?'You need your identity document and the recipient details. Would you like the step-by-step guide?':(isPt?'Você precisa do documento de identidade e dos dados do destinatário. Quer o passo a passo?':'Necesitas tu documento de identidad y los datos del destinatario. ¿Te envío el paso a paso?');
      else if(/cupon|descuento|coupon|discount/.test(t)) r=isEn?'Yes. You can use <b>BIENVENIDA10</b> on your first transfer. Want a quote?':(isPt?'Sim. Use <b>BIENVENIDA10</b> na sua primeira operação. Quer cotar?':'Sí. Usa <b>BIENVENIDA10</b> en tu primer envío. ¿Cotizamos?');
      else if(/(\d+).*(brasil|brl|real)|brasil|brazil|enviar|send|cotiz|quote|soles|pen/.test(t)) r=isEn?'For <b>500 PEN to BRL</b> today: 1 PEN = 1.42 BRL. You would receive around <b>R$ 710</b>. Continue?':(isPt?'Para <b>500 PEN para BRL</b> hoje: 1 PEN = 1,42 BRL. Você receberia aprox. <b>R$ 710</b>. Deseja continuar?':'Para <b>500 PEN a BRL</b> hoy: 1 PEN = 1,42 BRL. Recibirías aprox. <b>R$ 710</b>. ¿Deseas continuar?');
      else r=isEn?'I detected your message. Do you want to <b>get a quote</b>, see <b>requirements</b>, book an <b>appointment</b>, or talk to an <b>advisor</b>?':(isPt?'Detectei sua mensagem. Você quer <b>cotar</b>, ver <b>requisitos</b>, marcar uma <b>consulta</b> ou falar com um <b>assessor</b>?':'Detecté tu mensaje. ¿Quieres <b>cotizar</b>, ver <b>requisitos</b>, reservar una <b>cita</b> o hablar con un <b>asesor</b>?');
      return r;
    }
    function reply(text){
      var typing=add('b','<span class="typing"><i></i><i></i><i></i></span>');
      if(real){
        var ctl=new AbortController(); var tmo=setTimeout(function(){ctl.abort();},45000);
        fetch(BP_BASE+'/consulta-webchat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,session_id:sessionId}),signal:ctl.signal})
          .then(function(r){clearTimeout(tmo);if(!r.ok)throw new Error(r.status);return r.json();})
          .then(function(d){var out=(d&&d.response)?String(d.response):'…';typing.innerHTML=esc(out).replace(/\n/g,'<br>');msgs.scrollTop=msgs.scrollHeight;})
          .catch(function(){setStatus(false);typing.innerHTML=simReply(text);msgs.scrollTop=msgs.scrollHeight;});
      } else {
        setTimeout(function(){typing.innerHTML=simReply(text);msgs.scrollTop=msgs.scrollHeight;},750);
      }
    }
    function send(text){if(!text.trim())return;add('u',esc(text));reply(text);}
    document.getElementById('bpClose').onclick=function(){C().closeDrawer();};
    document.getElementById('bpSend').onclick=function(){var i=document.getElementById('bpInput');send(i.value);i.value='';};
    document.getElementById('bpInput').addEventListener('keydown',function(e){if(e.key==='Enter'){send(this.value);this.value='';}});
    document.querySelectorAll('#bpQuick button').forEach(function(b){b.onclick=function(){send(b.dataset.q);};});
  };

  /* ===================== FACEBOOK / WHATSAPP WIZARD ===================== */
  window.openFacebookWizard=function(){
    var T=C().T, D=window.DATA, steps=D.facebookWizard, i=0;
    function render(){
      var dots=steps.map(function(s,idx){return '<div class="stp '+(idx===i?'active':(idx<i?'done':''))+'"><div class="num">'+(idx<i?'✓':(idx+1))+'</div>'+(idx===i?'<div class="lab">'+s.title+'</div>':'')+(idx<steps.length-1?'<div class="line"></div>':'')+'</div>';}).join('');
      var s=steps[i], last=i===steps.length-1;
      var fbLook = i<=1 ? '<div class="fb-popup mb18"><div class="fbh">'+icon('facebook','#fff',22)+' Facebook</div><div class="fbb">'+(i===0?'<div class="muted" style="font-size:12.5px">Se abrirá un popup de <b>facebook.com</b> servido por Meta. La plataforma actúa como Tech Provider.</div>':'<div class="fb-perm">'+icon('check','var(--accent)',18)+'<div>Continuar como <b>Tu Negocio</b> — conceder acceso a WhatsApp Business.</div></div><div class="fb-perm">'+icon('check','var(--accent)',18)+'<div>whatsapp_business_management · whatsapp_business_messaging</div></div>')+'</div></div>' : '';
      var prereq = i===0 ? '<div class="card pad-s mb18"><div class="sub mb8">'+T('ch_prereqs')+'</div>'+D.facebookPrereqs.slice(0,4).map(function(p){return '<div style="font-size:12px;color:var(--muted);padding:3px 0;display:flex;gap:7px">'+icon('check','var(--accent)',14)+p+'</div>';}).join('')+'</div>' : '';
      var done = last ? '<div class="reuse-note mt14">'+icon('check','currentColor',16)+'<div><b>'+T('fb_done_title')+'</b> '+T('fb_done_desc')+'</div></div>' : '';
      var tokens = last ? '<div class="card pad-s mt14"><div class="sub mb8">'+T('fb_tokens')+'</div><div class="muted" style="font-size:12px;line-height:1.6">'+D.facebookTokensWebhook+'</div></div>' : '';
      C().modal(
        '<div class="modal-head">'+icon('whatsapp','#25D366',20)+'<h3>'+T('fb_wizard_title')+'</h3><span class="x">'+icon('x','var(--muted)',18)+'</span></div>'+
        '<div class="modal-body"><div class="steps">'+dots+'</div>'+prereq+fbLook+
          '<h3 style="margin-bottom:6px">'+(i+1)+'. '+s.title+'</h3><p class="muted" style="font-size:13.5px">'+s.description+'</p>'+
          '<div class="info-note mt14">'+icon('info','var(--blue)',16)+'<div><b>'+T('fb_meta_concept')+':</b> '+s.meta_concept+'</div></div>'+done+tokens+'</div>'+
        '<div class="modal-foot">'+(i>0?'<button class="btn" id="fbBack">'+T('back')+'</button>':'<span></span>')+'<button class="btn primary" id="fbNext">'+(last?T('finish'):T('next'))+' '+icon('arrow','currentColor',15)+'</button></div>','lg');
      var bk=document.getElementById('fbBack'); if(bk) bk.onclick=function(){i--;render();};
      document.getElementById('fbNext').onclick=function(){if(!last){i++;render();}else{C().closeModal();C().toast(T('toast_connected'));}};
    }
    render();
  };
})();
