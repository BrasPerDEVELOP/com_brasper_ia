/* ===========================================================
   Cauce — motor de la maqueta (router + i18n + UI engine)
   Contratos:
     window.DATA      -> datos demo + nav + roles + plugins + verticales + wizards
     window.I18N      -> { lang, dict:{es,pt,en}, t(key) }
     window.VIEWS     -> { key: ctx => htmlString }   ctx = {T, D, state}
     window.VIEW_INIT -> { key: rootEl => void }       (interacciones por vista)
   =========================================================== */
(function(){
  var D = window.DATA, I = window.I18N, VIEWS = window.VIEWS||{}, VINIT = window.VIEW_INIT||{};
  var state = { lang: (localStorage.getItem('cauce_lang')||'es'), tenant: 0, view: 'dashboard', role: 'owner' };
  I.lang = state.lang;
  function T(k){ return I.t(k); }
  window.__cauce = { state:state, T:T };

  var $ = function(id){ return document.getElementById(id); };
  var host = $('views'), titleEl = $('pageTitle');

  /* ---------- nav (filtrada por rol) ---------- */
  var VIEW_PERM = { agency:'users.invite', flows:'flows.edit', conversations:'conversations.handle', analytics:'analytics.view', knowledge:'ai.manage', ai:'ai.manage', channels:'channels.manage', integrations:'integrations.manage', team:'users.invite', settings:'users.invite', architecture:'flows.edit', roadmap:'flows.edit' };
  function allows(view){ var p = VIEW_PERM[view]; if(!p) return true; return (D.matrix[state.role]||[]).indexOf(p) >= 0; }
  function renderNav(){
    var nav = $('nav'); nav.innerHTML = ''; var pendingSec = null;
    D.nav.forEach(function(item){
      if(item.sec){ pendingSec = item.sec; return; }
      if(!allows(item.view)) return;
      if(pendingSec){ nav.insertAdjacentHTML('beforeend','<div class="nav-sec">'+T(pendingSec)+'</div>'); pendingSec = null; }
      var badge = item.badge ? '<span class="badge">'+item.badge+'</span>' : (item.dot ? '<span class="ndot"></span>' : '');
      var a = document.createElement('a');
      a.className = (item.view===state.view?'active':'');
      a.innerHTML = window.icon(item.icon)+'<span>'+T(item.i18n)+'</span>'+badge;
      a.addEventListener('click', function(){ setView(item.view); });
      nav.appendChild(a);
    });
  }
  function navTitle(){
    var it = D.nav.filter(function(x){return x.view===state.view;})[0];
    return it ? T(it.i18n) : '';
  }

  /* ---------- tenant switcher ---------- */
  function renderTenant(){
    var t = D.tenants[state.tenant];
    $('tenantCurrent').innerHTML =
      '<div class="t-mark" style="background:'+t.color+'">'+t.initial+'</div>'+
      '<div class="grow"><div class="tt">'+t.name+'</div><div class="ts">'+t.vertical+' · '+t.plan+'</div></div>'+
      window.icon('chev','var(--side-muted)',16).replace('<svg','<svg class="caret"');
    $('tbTenant').textContent = t.name;
    var menu = $('tenantMenu'); menu.innerHTML='';
    D.tenants.forEach(function(tt, idx){
      var d = document.createElement('div'); d.className='tm-item';
      d.innerHTML = '<div class="t-mark" style="background:'+tt.color+';width:26px;height:26px;font-size:12px">'+tt.initial+'</div>'+
        '<div class="grow"><div class="nm">'+tt.name+'</div><div class="mt">'+tt.vertical+'</div></div>'+
        (idx===state.tenant?window.icon('check','var(--accent-l)',16).replace('<svg','<svg class="ck"'):'');
      d.addEventListener('click', function(){ state.tenant=idx; closeTenant(); renderTenant(); renderView(); toast(T('toast_tenant')+' '+tt.name); });
      menu.appendChild(d);
    });
    var nuevo = document.createElement('div'); nuevo.className='tm-item tm-new';
    nuevo.innerHTML = window.icon('plus','var(--accent-l)',16)+'<span>'+T('create_company')+'</span>';
    nuevo.addEventListener('click', function(){ closeTenant(); openCreateTenant(); });
    menu.appendChild(nuevo);
  }
  function closeTenant(){ $('tenantSwitcher').classList.remove('open'); }
  $('tenantCurrent').addEventListener('click', function(e){ e.stopPropagation(); $('tenantSwitcher').classList.toggle('open'); });
  document.addEventListener('click', function(e){ if(!$('tenantSwitcher').contains(e.target)) closeTenant(); });
  window.__cauce.setTenant = function(i){ state.tenant = i; renderTenant(); renderView(); };

  /* ---------- views ---------- */
  var VIA_CLS={real:'real',f1:'f1',f2:'f2',f3:'f3',doc:'doc'};
  function viaBanner(){
    var v=(D.viability||{})[state.view]; if(!v) return '';
    var note=T('via_note_'+state.view);
    return '<div class="via-bar '+VIA_CLS[v.lv]+'"><span class="via-tag">'+T('via_'+v.lv)+'</span><span class="via-note">'+note+'</span></div>';
  }
  function renderView(){
    var fn = VIEWS[state.view] || function(){ return '<div class="card pad">Vista no encontrada</div>'; };
    host.innerHTML = '<section class="view active">'+ viaBanner() + fn({T:T, D:D, state:state}) +'</section>';
    titleEl.textContent = navTitle();
    $('scroll').scrollTop = 0;
    if(VINIT[state.view]) try{ VINIT[state.view](host); }catch(err){ console.error('init '+state.view, err); }
    translateStatic();
  }
  function setView(key){ state.view = key; renderNav(); renderView(); var sb=document.querySelector('.sidebar'); if(sb) sb.classList.remove('open'); }
  window.__cauce.setView = setView;

  /* ---------- role switcher ("ver como") — RBAC en vivo ---------- */
  var ROLE_PEOPLE = { owner:{n:'Alberth Castillo',i:'AC',c:'#0E7C66'}, admin:{n:'Daniela Ríos',i:'DR',c:'#2C6FB0'}, builder:{n:'Lucía Mendoza',i:'LM',c:'#5B51B3'}, analyst:{n:'Pedro Torres',i:'PT',c:'#C98A1E'}, agent:{n:'Raúl Ávila',i:'RA',c:'#DD6A3C'}, billing:{n:'Sofía Vega',i:'SV',c:'#B0436B'}, viewer:{n:'Invitado Demo',i:'IN',c:'#888780'} };
  var ROLE_HOME = { agent:'conversations', billing:'dashboard', analyst:'analytics', viewer:'analytics' };
  function roleName(k){ var r=(D.roles||[]).filter(function(x){return x.key===k;})[0]; return r?r.name:k; }
  function renderRole(){
    var p = ROLE_PEOPLE[state.role] || ROLE_PEOPLE.owner;
    $('roleBtn').innerHTML = '<span class="rdot" style="background:'+p.c+'"></span>'+T('view_as')+': <b>'+roleName(state.role)+'</b>'+window.icon('chev','var(--muted)',14);
    $('userAv').textContent = p.i; $('userAv').style.background = p.c; $('userAv').style.color = '#fff';
    $('userName').textContent = p.n; $('userRole').textContent = roleName(state.role);
    var menu = $('roleMenu'); menu.innerHTML = '';
    (D.roles||[]).forEach(function(r){
      var pe = ROLE_PEOPLE[r.key] || {c:'#888',i:'?'};
      var d = document.createElement('div'); d.className = 'rm-i'+(r.key===state.role?' on':'');
      d.innerHTML = '<span class="t-mark" style="width:26px;height:26px;font-size:11px;background:'+pe.c+'">'+pe.i+'</span><div class="grow"><div style="font-weight:600;font-size:13px">'+r.name+'</div><div style="font-size:11px;color:var(--muted)">'+r.desc.slice(0,58)+'…</div></div>'+(r.key===state.role?window.icon('check','var(--accent)',16):'');
      d.addEventListener('click', function(){ $('roleSwitch').classList.remove('open'); setRole(r.key); });
      menu.appendChild(d);
    });
  }
  function setRole(r){
    state.role = r; renderRole();
    var home = ROLE_HOME[r] || 'dashboard'; if(!allows(home)) home = 'dashboard';
    state.view = home; renderNav(); renderView();
    toast(T('toast_role')+': '+roleName(r));
  }
  window.__cauce.setRole = setRole;

  /* ---------- i18n ---------- */
  function translateStatic(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k = el.getAttribute('data-i18n'); var v = T(k); if(v && v!==k) el.textContent = v;
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){
      var k = el.getAttribute('data-i18n-ph'); var v = T(k); if(v && v!==k) el.setAttribute('placeholder', v);
    });
  }
  function setLang(lang){
    state.lang = lang; I.lang = lang; localStorage.setItem('cauce_lang', lang);
    document.documentElement.lang = lang;
    Array.prototype.forEach.call($('langtog').children, function(b){ b.classList.toggle('on', b.dataset.lang===lang); });
    renderNav(); renderTenant(); renderRole(); renderView(); translateStatic();
    var s = $('searchInput'); if(s) s.placeholder = T('search_ph');
    toast(T('toast_lang'));
  }
  Array.prototype.forEach.call($('langtog').children, function(b){
    b.addEventListener('click', function(){ setLang(b.dataset.lang); });
  });
  window.__cauce.setLang = setLang;

  /* ---------- modal / drawer / toast (genéricos, reutilizables por vistas) ---------- */
  function modal(html, cls){
    $('modalHost').className = ''; $('modalHost').innerHTML = '<div class="modal '+(cls||'')+'">'+html+'</div>';
    $('overlay').classList.add('open');
    var m = $('modalHost').querySelector('.x'); if(m) m.addEventListener('click', closeModal);
  }
  function closeModal(){ $('overlay').classList.remove('open'); $('modalHost').innerHTML=''; }
  $('overlay').addEventListener('click', function(e){ if(e.target===$('overlay')) closeModal(); });
  function drawer(html){ $('drawer').innerHTML = html; $('drawer').classList.add('open'); var sc=$('scrim'); if(sc) sc.classList.add('open'); }
  function closeDrawer(){ $('drawer').classList.remove('open'); var sc=$('scrim'); if(sc) sc.classList.remove('open'); setTimeout(function(){ $('drawer').innerHTML=''; }, 300); }
  function toast(msg){
    var t = document.createElement('div'); t.className='toast';
    t.innerHTML = window.icon('check','var(--accent-l)',16)+'<span>'+msg+'</span>';
    $('toasts').appendChild(t);
    setTimeout(function(){ t.classList.add('out'); setTimeout(function(){t.remove();},320); }, 2200);
  }
  window.__cauce.modal = modal; window.__cauce.closeModal = closeModal;
  window.__cauce.drawer = drawer; window.__cauce.closeDrawer = closeDrawer;
  window.__cauce.toast = toast;

  /* ---------- create-tenant wizard (multi-tenant) ---------- */
  function openCreateTenant(){
    var steps = D.tenantWizard, i = 0;
    function render(){
      var stepDots = steps.map(function(s,idx){
        return '<div class="stp '+(idx===i?'active':(idx<i?'done':''))+'">'+
          '<div class="num">'+(idx<i?'✓':(idx+1))+'</div><div class="lab">'+s.title+'</div>'+(idx<steps.length-1?'<div class="line"></div>':'')+'</div>';
      }).join('');
      var s = steps[i];
      var stepBody = (s.body||'')
        .replace(/__WA__/g, window.icon('whatsapp','#25D366',28))
        .replace(/__TG__/g, window.icon('telegram','#229ED9',28))
        .replace(/__WC__/g, window.icon('chat','var(--blue)',28))
        .replace(/__CH__/g, window.icon('chev','var(--muted)',15));
      var body = '<div class="wd">'+s.description+'</div>'+ stepBody;
      modal(
        '<div class="modal-head">'+window.icon('building','var(--accent)',20)+'<h3>'+T('create_company')+'</h3><span class="x">'+window.icon('x','var(--muted)',18)+'</span></div>'+
        '<div class="modal-body"><div class="steps">'+stepDots+'</div><div class="wstep active"><h3 style="margin-bottom:6px">'+s.title+'</h3>'+body+'</div></div>'+
        '<div class="modal-foot">'+(i>0?'<button class="btn" id="wzBack">'+T('back')+'</button>':'<span></span>')+
        '<button class="btn primary" id="wzNext">'+(i===steps.length-1?T('finish'):T('next'))+' '+window.icon('arrow','currentColor',15)+'</button></div>', 'lg');
      var b=$('modalHost').querySelector('#wzBack'); if(b) b.addEventListener('click', function(){ i--; render(); });
      $('modalHost').querySelector('#wzNext').addEventListener('click', function(){ if(i<steps.length-1){ i++; render(); } else { closeModal(); toast(T('toast_company')); } });
      $('modalHost').querySelector('.x').addEventListener('click', closeModal);
    }
    render();
  }
  window.__cauce.openCreateTenant = openCreateTenant;

  /* ---------- boot ---------- */
  document.documentElement.lang = state.lang;
  Array.prototype.forEach.call($('langtog').children, function(b){ b.classList.toggle('on', b.dataset.lang===state.lang); });
  $('searchIcon').innerHTML = window.icon('search','var(--muted)',16);
  $('bellBtn').insertAdjacentHTML('afterbegin', window.icon('bell','currentColor',18));
  var si=$('searchInput'); if(si) si.placeholder = T('search_ph');
  renderNav(); renderTenant(); renderRole(); renderView(); translateStatic();
  $('roleBtn').addEventListener('click', function(e){ e.stopPropagation(); $('roleSwitch').classList.toggle('open'); });
  var sc=$('scrim'); if(sc) sc.addEventListener('click', closeDrawer);
  var mb=$('menuBtn'); if(mb) mb.addEventListener('click', function(){ document.querySelector('.sidebar').classList.toggle('open'); });
  document.addEventListener('click', function(e){ var rs=$('roleSwitch'); if(rs && !rs.contains(e.target)) rs.classList.remove('open'); });
})();
