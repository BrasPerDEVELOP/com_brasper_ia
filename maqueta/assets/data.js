/* ===========================================================
   Cauce — datos demo + estructura (window.DATA)
   =========================================================== */
window.DATA = {

  /* ---------- viabilidad por pantalla: qué es real, qué es plan, qué es visión ---------- */
  viability: {
    flows:        {lv:'real'},
    channels:     {lv:'real'},
    ai:           {lv:'real'},
    conversations:{lv:'f1'},
    settings:     {lv:'f1'},
    agency:       {lv:'f2'},
    dashboard:    {lv:'f2'},
    integrations: {lv:'f2'},
    analytics:    {lv:'f3'},
    knowledge:    {lv:'f3'},
    team:         {lv:'f3'},
    architecture: {lv:'doc'},
    roadmap:      {lv:'doc'}
  },

  /* ---------- navegación ---------- */
  nav: [
    {sec:'sec_agency'},
    {view:'agency',        icon:'building',   i18n:'nav_agency'},
    {sec:'sec_op'},
    {view:'dashboard',     icon:'gauge',      i18n:'nav_dashboard'},
    {view:'conversations', icon:'inbox',      i18n:'nav_conversations', badge:'7'},
    {view:'analytics',     icon:'chart',      i18n:'nav_analytics'},
    {sec:'sec_ai'},
    {view:'ai',            icon:'ai',         i18n:'nav_ai'},
    {view:'flows',         icon:'flow',       i18n:'nav_logic'},
    {view:'knowledge',     icon:'book',       i18n:'nav_knowledge'},
    {sec:'sec_conn'},
    {view:'channels',      icon:'cast',       i18n:'nav_channels'},
    {view:'integrations',  icon:'puzzle',     i18n:'nav_integrations'},
    {sec:'sec_acct'},
    {view:'team',          icon:'users',      i18n:'nav_team'},
    {view:'settings',      icon:'gear',       i18n:'nav_settings'},
    {sec:'sec_platform'},
    {view:'architecture',  icon:'layers',     i18n:'nav_architecture'},
    {view:'roadmap',       icon:'rocket',     i18n:'nav_roadmap'}
  ],

  /* ---------- empresas (tenants) — demuestra multi-tenant y multi-rubro ---------- */
  tenants: [
    {name:'Brasper',       initial:'B', color:'#DD6A3C', vertical:'Remesas / Fintech', plan:'Pro',      status:'activo',  wa:'+51 966 991 933', tg:'@brasper_agent_bot', tgid:'7832…4401', msgs:62000, cost:412.80, fee:900, ownKey:false, handoff:'+51 987 654 321', pnid:'1098…4721', llm:'OpenAI + DeepSeek', onboarding:{numero:'cliente', contrato:true,  datos:true,  retencion:'180 días'},
      externalApis:{
        brasper_api:{name:'API Brasper',baseUrl:'https://api.brasper.com/v1',auth:'Bearer',token:'sk_brasper_live_•••••••••3f9',
          endpoints:[
            {tool:'tipo_de_cambio',  method:'GET', path:'/tipo-de-cambio?from={{from}}&to={{to}}',                  desc:'Tasa de cambio actual entre monedas'},
            {tool:'comisiones',      method:'GET', path:'/comisiones?monto={{monto}}&corredor={{corredor}}',        desc:'Comisión aplicada a la operación'},
            {tool:'cupones',         method:'GET', path:'/cupones/validar',                                        desc:'Valida un cupón y devuelve descuento'},
            {tool:'get_cliente',     method:'GET', path:'/clientes?telefono={{telefono}}',                          desc:'Identifica cliente por teléfono'},
            {tool:'buscar_promociones',method:'GET',path:'/promociones?segmento={{segmento}}',                      desc:'Promociones activas por segmento'},
            {tool:'crear_operacion', method:'POST',path:'/operaciones',                                             desc:'Registra una nueva operación de envío'}
          ]}}},
    {name:'Zefiron',       initial:'Z', color:'#2C6FB0', vertical:'E-commerce',         plan:'Business', status:'activo',  wa:'+51 998 210 340', tg:'@zefiron_shop_bot', tgid:'5410…1188', msgs:38000, cost:255.10, fee:700, ownKey:true,  handoff:'+51 987 111 222', pnid:'2264…8830', llm:'DeepSeek',         onboarding:{numero:'cliente', contrato:true,  datos:false, retencion:'90 días'},
      externalApis:{
        zefiron_api:{name:'API Zefiron',baseUrl:'https://api.zefiron.com/v2',auth:'Bearer',token:'zef_live_•••••••••7a2',
          endpoints:[
            {tool:'buscar_productos',method:'GET', path:'/productos?q={{texto}}',      desc:'Busca productos del catálogo'},
            {tool:'estado_pedido',   method:'GET', path:'/pedidos/{{pedido_id}}/estado',desc:'Estado de un pedido'},
            {tool:'crear_pedido',    method:'POST',path:'/pedidos',                     desc:'Crea un pedido nuevo'},
            {tool:'get_cliente',     method:'GET', path:'/clientes?email={{email}}',    desc:'Identifica cliente por email'}
          ]}}},
    {name:'Clínica Vida',  initial:'C', color:'#0E7C66', vertical:'Salud',              plan:'Starter',  status:'pausado', wa:'+51 1 640 5050', tg:'@clinicavida_citas_bot', tgid:'9302…7740', msgs:5400,  cost:41.20,  fee:400, ownKey:false, handoff:'+51 999 555 111', pnid:'3391…1002', llm:'Claude',           onboarding:{numero:'agencia', contrato:false, datos:false, retencion:'sin definir'}}
  ],

  /* ---------- RBAC ---------- */
  roles: [
    {key:'owner',   icon:'shield', name:'Propietario',  desc:'Control total: empresa, facturación, roles y usuarios. Único que puede transferir o eliminar la cuenta.'},
    {key:'admin',   icon:'gear',   name:'Administrador', desc:'Administra toda la operación salvo eliminar la empresa o transferir propiedad.'},
    {key:'builder', icon:'flow',   name:'Operador técnico', desc:'Configura prompts, herramientas, canales e integraciones. No toca facturación ni usuarios.'},
    {key:'analyst', icon:'chart',  name:'Analista',      desc:'Solo lectura de analítica, reportes y conversaciones (para contexto). No edita nada.'},
    {key:'agent',   icon:'headset',name:'Agente / Asesor',desc:'Atiende la bandeja: ve y responde chats asignados y gestiona el handoff humano.'},
    {key:'billing', icon:'creditcard',name:'Finanzas', desc:'Lee consumo, costos y margen por cliente. Las facturas se emiten fuera de la plataforma.'},
    {key:'viewer',  icon:'eye',    name:'Invitado',      desc:'Solo lectura general (flujos, analítica, conversaciones). Ideal para stakeholders o auditores.'}
  ],
  permissions: [
    {key:'company.manage',      name:'Gestionar empresa'},
    {key:'users.invite',        name:'Invitar usuarios'},
    {key:'roles.manage',        name:'Gestionar roles'},
    {key:'flows.edit',          name:'Configurar automatizaciones'},
    {key:'flows.publish',       name:'Publicar cambios del bot'},
    {key:'conversations.handle',name:'Atender chats'},
    {key:'analytics.view',      name:'Ver analítica'},
    {key:'channels.manage',     name:'Gestionar canales'},
    {key:'ai.manage',           name:'Gestionar IA'},
    {key:'integrations.manage', name:'Integraciones'},
    {key:'billing.manage',      name:'Ver consumo y margen'}
  ],
  matrix: {
    owner:  ['company.manage','users.invite','roles.manage','flows.edit','flows.publish','conversations.handle','analytics.view','channels.manage','ai.manage','integrations.manage','billing.manage'],
    admin:  ['users.invite','roles.manage','flows.edit','flows.publish','conversations.handle','analytics.view','channels.manage','ai.manage','integrations.manage','billing.manage'],
    builder:['flows.edit','flows.publish','conversations.handle','analytics.view','channels.manage','ai.manage','integrations.manage'],
    analyst:['analytics.view'],
    agent:  ['conversations.handle','analytics.view'],
    billing:['billing.manage'],
    viewer: ['analytics.view']
  },

  /* ---------- integraciones esenciales (no marketplace masivo) ---------- */
  pluginCategories: [
    {key:'all',name:'Todos'},{key:'crm',name:'CRM'},{key:'calendar',name:'Calendario'},{key:'payments',name:'Pagos'},
    {key:'ecommerce',name:'E-commerce'},{key:'data',name:'Datos'},{key:'channels',name:'Canales'},
    {key:'llm',name:'Proveedores LLM'},{key:'automation',name:'Automatización'},{key:'helpdesk',name:'Helpdesk'},{key:'analytics',name:'Analítica'}
  ],
  plugins: [
    {key:'hubspot',name:'HubSpot',category:'crm',desc:'Sincroniza contactos, leads y deals con tu CRM HubSpot.'},
    {key:'salesforce',name:'Salesforce',category:'crm',desc:'Crea y actualiza Leads, Contactos y Oportunidades en Salesforce.'},
    {key:'zoho_crm',name:'Zoho CRM',category:'crm',desc:'Registra leads y actividades del agente en Zoho CRM.'},
    {key:'pipedrive',name:'Pipedrive',category:'crm',desc:'Empuja personas y tratos al pipeline de Pipedrive en tiempo real.'},
    {key:'google_calendar',name:'Google Calendar',category:'calendar',desc:'Consulta disponibilidad y reserva citas desde la conversación.'},
    {key:'calendly',name:'Calendly',category:'calendar',desc:'Comparte enlaces de reserva y confirma citas vía Calendly.'},
    {key:'microsoft_bookings',name:'Microsoft Bookings',category:'calendar',desc:'Gestiona reservas sobre calendarios de Microsoft 365.'},
    {key:'stripe',name:'Stripe',category:'payments',desc:'Genera links de pago, cobros y suscripciones.'},
    {key:'mercadopago',name:'MercadoPago',category:'payments',desc:'Crea links de cobro para LatAm desde el chat.'},
    {key:'culqi',name:'Culqi',category:'payments',desc:'Procesa cobros con tarjeta para el mercado peruano.'},
    {key:'paypal',name:'PayPal',category:'payments',desc:'Emite órdenes de pago y checkout de PayPal.'},
    {key:'shopify',name:'Shopify',category:'ecommerce',desc:'Consulta productos, stock y pedidos de tu tienda Shopify.'},
    {key:'woocommerce',name:'WooCommerce',category:'ecommerce',desc:'Lee catálogo y estado de pedidos de WooCommerce.'},
    {key:'vtex',name:'VTEX',category:'ecommerce',desc:'Integra catálogo, precios y seguimiento de pedidos VTEX.'},
    {key:'google_sheets',name:'Google Sheets',category:'data',desc:'Lee y escribe filas en hojas de cálculo.'},
    {key:'airtable',name:'Airtable',category:'data',desc:'Consulta y crea registros en bases de Airtable.'},
    {key:'notion',name:'Notion',category:'data',desc:'Lee bases de datos y páginas de Notion.'},
    {key:'whatsapp_cloud',name:'WhatsApp Cloud API',category:'channels',desc:'Conecta el agente al canal oficial de WhatsApp Business.'},
    {key:'telegram',name:'Telegram',category:'channels',desc:'Expone el agente como un bot de Telegram.'},
    {key:'instagram_messenger',name:'Instagram / Messenger',category:'channels',desc:'Atiende DMs de Instagram y Messenger vía Meta.'},
    {key:'slack',name:'Slack',category:'channels',desc:'Notifica equipos y publica mensajes en canales de Slack.'},
    {key:'anthropic_claude',name:'Anthropic Claude',category:'llm',desc:'Modelos Claude (Opus, Sonnet, Haiku) como motor del agente.'},
    {key:'openai',name:'OpenAI',category:'llm',desc:'Motoriza al agente con modelos GPT de OpenAI.'},
    {key:'deepseek',name:'DeepSeek',category:'llm',desc:'Alternativa de bajo costo con modelos DeepSeek.'},
    {key:'google_gemini',name:'Google Gemini',category:'llm',desc:'Usa modelos Gemini de Google como proveedor LLM.'},
    {key:'zapier',name:'Zapier',category:'automation',desc:'Dispara Zaps para conectar con miles de apps sin código.'},
    {key:'make',name:'Make',category:'automation',desc:'Activa escenarios de Make ante eventos del agente.'},
    {key:'generic_webhook',name:'Webhook Genérico',category:'automation',desc:'Envía payloads JSON a cualquier endpoint propio.'},
    {key:'n8n',name:'n8n',category:'automation',desc:'Conecta a flujos de automatización auto-hospedados en n8n.'},
    {key:'zendesk',name:'Zendesk',category:'helpdesk',desc:'Crea, actualiza y escala tickets de soporte en Zendesk.'},
    {key:'freshdesk',name:'Freshdesk',category:'helpdesk',desc:'Abre y gestiona tickets de soporte en Freshdesk.'},
    {key:'intercom',name:'Intercom',category:'helpdesk',desc:'Sincroniza conversaciones y crea tickets en Intercom.'},
    {key:'google_analytics',name:'Google Analytics (GA4)',category:'analytics',desc:'Envía eventos de conversación y conversiones a GA4.'},
    {key:'meta_pixel',name:'Meta Pixel / CAPI',category:'analytics',desc:'Reporta conversiones a Meta vía Pixel y Conversions API.'},
    {key:'mixpanel',name:'Mixpanel',category:'analytics',desc:'Registra eventos y embudos de las conversaciones en Mixpanel.'}
  ],
  enabledPlugins: ['whatsapp_cloud','telegram','openai','deepseek','google_calendar','culqi','google_sheets'],

  managedFocus: [
    {title:'Operación de clientes reales', body:'Tenants, estado del canal, consumo y margen en una sola vista.'},
    {title:'Configuración probada en producción', body:'La lógica se parametriza con prompts, herramientas y políticas ya operando con clientes reales.'},
    {title:'Integraciones a medida', body:'Conectamos la API de tu cliente y sus herramientas esenciales sin código adicional.'}
  ],

  deliveryPlan: {
    start:'02 jul 2026',
    mvp:'16 jul 2026',
    pilot:'23 jul 2026',
    finish:'30 jul 2026',
    readiness:[
      {ok:true, title:'Maqueta comercial enfocada', body:'Ya no promete builder visual, billing automático ni marketplace grande.'},
      {ok:true, title:'Modelo técnico claro', body:'Tenant activo, proveedor IA, secret_ref y costos separados por cliente.'},
      {ok:false, title:'Backend tenant-aware', body:'Falta implementar resolución por phone_number_id, config por tenant y prefijos Redis.'},
      {ok:false, title:'Persistencia y medición real', body:'Falta guardar conversaciones y registrar tokens/costo por tenant.'}
    ],
    timeline:[
      {phase:'Día 0', date:'02 jul', title:'Arranque', body:'Congelar alcance y empezar config de tenants.', status:'ready'},
      {phase:'Semana 1', date:'03-09 jul', title:'Núcleo multi-tenant', body:'Tenant resolver, Redis namespacing, prompts/API keys por cliente.', status:'build'},
      {phase:'Semana 2', date:'10-16 jul', title:'MVP operativo', body:'WhatsApp por tenant, handoff correcto, logs de tokens y persistencia mínima.', status:'build'},
      {phase:'Semana 3-4', date:'17-30 jul', title:'Piloto controlado', body:'Pruebas con Brasper, segundo cliente y ajustes antes de cobrar/escala.', status:'later'}
    ]
  },

  /* ---------- verticales / plantillas (todo tipo de negocio) ---------- */
  verticals: [
    {key:'remesas_fintech',name:'Remesas / Fintech',icon:'dollar',color:'#DD6A3C',flow:'Cotización y envío de remesa',nodes:['Inicio','Detectar idioma y responder igual','Agente IA: monto/origen/destino','API: GET /rates','Condición: ¿cotización?','Handoff: asesor']},
    {key:'salud_clinica',name:'Clínica / Salud',icon:'shield',color:'#0E7C66',flow:'Agendamiento de cita médica',nodes:['Inicio','Mensaje: especialidades','Agente IA: especialidad/urgencia','Capturar: paciente','API: POST /citas','Handoff: triaje urgente']},
    {key:'restaurante',name:'Restaurante',icon:'sparkles',color:'#C98A1E',flow:'Pedido y reserva de mesa',nodes:['Inicio','Mensaje: carta/pedido/reserva','Agente IA: arma el pedido','Capturar: dirección y pago','API: POST /orders','Mensaje: confirmación + ETA']},
    {key:'inmobiliaria',name:'Inmobiliaria',icon:'building',color:'#5B51B3',flow:'Calificación de lead y visita',nodes:['Inicio','Agente IA: tipo/zona/presupuesto','API: GET /propiedades','Condición: ¿coincidencias?','Capturar: contacto y horario','Handoff: agente de zona']},
    {key:'ecommerce_retail',name:'E-commerce / Retail',icon:'creditcard',color:'#2C6FB0',flow:'Seguimiento de pedido y postventa',nodes:['Inicio','Mensaje: menú','Capturar: nº pedido','API: GET /orders/{id}/status','Agente IA: dudas de producto','Handoff: reclamos']},
  ],

  /* ---------- wizard crear empresa (multi-tenant) ---------- */
  tenantWizard: [
    {title:'Datos de la empresa', description:'Identidad del tenant. Validamos el subdominio en tiempo real y aprovisionamos un espacio aislado (RLS) para la empresa.',
      body:'<div class="fld"><label>Nombre de la empresa</label><div class="input"><input value="Mi Empresa"></div></div>'+
           '<div class="fld"><label>Subdominio</label><div class="input"><input value="mi-empresa" style="text-align:right"><span class="pre">.cauce.ai</span></div></div>'+
           '<div class="info-note"><span></span><div>Cada empresa queda aislada por <b>tenant_id</b> con Row-Level Security en Postgres.</div></div>'},
    {title:'Rubro / plantilla', description:'Elige el rubro. Cada vertical precarga una plantilla de flujo lista para publicar (nodos, prompts del Agente IA y herramientas típicas del sector).',
      body:'<div class="chips" id="wzVerticals"></div>'},
    {title:'Conectar canal', description:'Conecta el primer punto de contacto. Puedes empezar solo con el webchat (snippet embebible) y conectar WhatsApp más tarde.',
      body:'<div class="grid-2e"><div class="card pad-s" style="text-align:center"><div style="margin-bottom:6px">__WA__</div><b>WhatsApp Business</b><div class="muted" style="font-size:12px">vía Facebook/Meta</div></div>'+
           '<div class="card pad-s" style="text-align:center"><div style="margin-bottom:6px">__TG__</div><b>Telegram</b><div class="muted" style="font-size:12px">BotFather + webhook</div></div>'+
           '<div class="card pad-s" style="text-align:center"><div style="margin-bottom:6px">__WC__</div><b>Webchat</b><div class="muted" style="font-size:12px">widget embebible</div></div></div>'},
    {title:'Invitar al equipo', description:'Da de alta a los primeros miembros con su rol. Define quién construye flujos, quién atiende el inbox y quién administra. Puedes omitirlo.',
      body:'<div class="fld"><label>Correo</label><div class="input"><input placeholder="persona@empresa.com"></div></div>'+
           '<div class="fld"><label>Rol</label><div class="select">Constructor __CH__</div></div>'},
    {title:'Listo', description:'Resumen del tenant: subdominio, plantilla, canal y miembros. Simula el flujo una vez y publica la primera versión del agente.',
      body:'<div class="reuse-note"><span></span><div>Tu agente queda operativo de inmediato. La plantilla del rubro reutiliza el orquestador y el policy engine del bot Brasper.</div></div>'}
  ],

  /* ---------- WhatsApp vía Facebook/Meta (Embedded Signup) — verificado ---------- */
  facebookPrereqs: [
    'Cuenta de Meta Business / Business Portfolio con datos reales del negocio.',
    'Verificación de negocio (Business Verification) completada (2–5 días hábiles).',
    'App de Meta tipo Business (categoría Messaging) — el nombre no puede contener "WhatsApp".',
    'Producto WhatsApp añadido + Terms de WhatsApp Business y Meta Hosting aceptados.',
    'App Review aprobado para whatsapp_business_management y whatsapp_business_messaging.',
    'Facebook Login for Business con Configuration de Embedded Signup (config_id) y dominios HTTPS permitidos.'
  ],
  facebookWizard: [
    {title:'Iniciar desde la plataforma', description:'El dueño hace clic en "Conectar con WhatsApp Business". Se invoca FB.login() con el config_id de Embedded Signup y el solutionID del proveedor; se abre el popup de Facebook.', meta_concept:'Facebook Login for Business + Embedded Signup. La plataforma actúa como Tech Provider; el popup lo sirve Meta.'},
    {title:'Autenticarse con Meta', description:'Dentro del popup el dueño inicia sesión con sus credenciales de Facebook / Meta Business y acepta continuar con la app del proveedor.', meta_concept:'Pantalla OAuth nativa de Facebook Login for Business.'},
    {title:'Business Portfolio', description:'Elige un Meta Business Portfolio existente o crea uno nuevo (nombre, dirección, web, email del negocio).', meta_concept:'Business Portfolio (antes Business Manager): contenedor de identidad bajo el que vivirá el WABA.'},
    {title:'WhatsApp Business Account (WABA)', description:'Selecciona o crea el WABA dentro del portfolio y concede al proveedor acceso a ese activo. El waba_id se devuelve al finalizar.', meta_concept:'WABA: activo padre que agrupa números, plantillas y configuración.'},
    {title:'Permisos y Términos', description:'Meta muestra los accesos que el negocio concede al proveedor y los enlaces a los Términos (Cloud API, WhatsApp Business, Meta). El dueño confirma.', meta_concept:'Scopes OAuth (definidos en la Configuration) + asignación de tasks/roles del activo al system user del proveedor.'},
    {title:'Número de teléfono', description:'El dueño introduce/selecciona el número en formato E.164. (Se omite solo si el partner aprovisiona el número con la variante only_waba_sharing.)', meta_concept:'Business phone number ligado al WABA, registrable para Cloud API.'},
    {title:'Verificar por OTP', description:'Meta envía un código de un solo uso por SMS o llamada; el dueño lo introduce en el popup. La plataforma nunca ve el OTP.', meta_concept:'Verificación de propiedad del número (prerrequisito para registrarlo).'},
    {title:'Perfil del número', description:'Define el display name (sujeto a revisión de Meta) y la categoría del negocio. Al finalizar, el popup se cierra.', meta_concept:'Perfil / display name del número y categoría del negocio.'},
    {title:'Resultado y activación (backend)', description:'El listener recibe WA_EMBEDDED_SIGNUP con { waba_id, phone_number_id } y el callback entrega un authorization code. El backend lo intercambia por un token (con el App Secret), SUSCRIBE el webhook (subscribed_apps) y luego REGISTRA el número (PIN de 6 dígitos que fija el proveedor).', meta_concept:'Embedded Signup devuelve ids + un code (no un token). Suscribir webhooks ANTES de registrar el número. Usar la versión vigente del Graph API.'}
  ],
  facebookTokensWebhook: 'Embedded Signup no entrega un token directo: devuelve waba_id y phone_number_id (evento WA_EMBEDDED_SIGNUP) y un authorization code. El backend lo intercambia por un Business Integration System User token (scopeado al WABA del cliente), suscribe la app al WABA y registra el número. Cada tenant queda aislado por su waba_id/phone_number_id y token scopeado; Meta firma cada webhook con X-Hub-Signature-256.',

  /* ---------- dashboard ---------- */
  stats: [
    {icon:'chat',     tint:'blue',  num:'1.284', delta:'▲ 12%', up:true,  i18n:'kpi_convs'},
    {icon:'user',     tint:'green', num:'342',   delta:'▲ 8%',  up:true,  i18n:'kpi_leads'},
    {icon:'check',    tint:'amber', num:'87%',   delta:'▲ 3%',  up:true,  i18n:'kpi_resolved'},
    {icon:'headset',  tint:'coral', num:'48',    delta:'▼ 5%',  up:false, i18n:'kpi_handoffs'}
  ],
  chart: [[60,14],[78,18],[52,9],[91,22],[74,12],[40,6],[83,16]],
  days: ['d_mon','d_tue','d_wed','d_thu','d_fri','d_sat','d_sun'],
  recent: [
    {in:'MS',color:'#2C6FB0',name:'María Salazar',ch:'WhatsApp',intent:'Cotización',state:'st_active',sc:'green',lead:true,t:'10:04'},
    {in:'JF',color:'#0E7C66',name:'João Ferreira',ch:'Webchat',intent:'Requisitos',state:'st_resolved',sc:'gray',lead:false,t:'09:51'},
    {in:'CL',color:'#C98A1E',name:'Carla López',ch:'WhatsApp',intent:'Hablar con asesor',state:'inbox_advisor',sc:'coral',lead:true,t:'09:40'},
    {in:'DR',color:'#5B51B3',name:'Diego Ramos',ch:'WhatsApp',intent:'Promoções',state:'st_resolved',sc:'gray',lead:false,t:'09:02'},
    {in:'AN',color:'#B0436B',name:'Ana Nunes',ch:'Webchat',intent:'Cotización',state:'st_active',sc:'green',lead:true,t:'09:15'},
    {in:'VR',color:'#229ED9',name:'Valeria Rojas',ch:'Telegram',intent:'Reservar cita',state:'st_active',sc:'green',lead:true,t:'08:56'}
  ],

  /* ---------- inbox ---------- */
  conversations: [
    {in:'MS',color:'#2C6FB0',name:'María Salazar',ch:'WhatsApp',lang:'es',time:'10:04',assigned:'Raúl Ávila',status:'asesor',
      msgs:[{r:'u',t:'Hola, quiero enviar 500 soles a Brasil',m:'10:02'},{r:'b',t:'¡Hola María! Para 500 PEN → BRL hoy: 1 PEN = 1,42 BRL. Recibirías aprox. R$ 710. ¿Deseas continuar?',m:'10:02',by:'Agente IA'},{r:'u',t:'Sí, ¿cómo hago?',m:'10:03'},{r:'b',t:'¿Me confirmas tu nombre completo para registrar la operación?',m:'10:03',by:'Agente IA'},{r:'u',t:'María Salazar Ríos',m:'10:04'},{r:'sys',t:'Handoff: prerequisito de nombre cumplido → transferido a asesor'},{r:'b',t:'Perfecto, María. Te conecto con un asesor para finalizar. 🙌',m:'10:04',by:'Sistema'}]},
    {in:'JF',color:'#0E7C66',name:'João Ferreira',ch:'Webchat',lang:'pt',time:'09:51',assigned:null,status:'bot',unread:true,
      msgs:[{r:'u',t:'Quais são os requisitos para enviar?',m:'09:50'},{r:'b',t:'Você precisa de documento de identidade e os dados do destinatário. Quer que eu te envie o passo a passo?',m:'09:51',by:'Agente IA'}]},
    {in:'CL',color:'#C98A1E',name:'Carla López',ch:'WhatsApp',lang:'es',time:'09:40',assigned:'Raúl Ávila',status:'asesor',
      msgs:[{r:'u',t:'Quiero hablar con una persona',m:'09:39'},{r:'sys',t:'Handoff solicitado → asignado a Raúl Ávila'},{r:'b',t:'Te conecto con un asesor ahora mismo.',m:'09:40',by:'Sistema'}]},
    {in:'AN',color:'#B0436B',name:'Ana Nunes',ch:'Webchat',lang:'es',time:'09:15',assigned:null,status:'bot',unread:true,
      msgs:[{r:'u',t:'¿Tienen cupón de bienvenida?',m:'09:15'},
        {r:'tool',t:'',tool:'cupones',endpoint:'GET https://api.brasper.com/v1/cupones/validar',req:'{codigo: "BIENVENIDA10"}',res:'{valido: true, descuento: 10, tipo: "porcentaje", vigencia: "30 días"}',m:'09:15'},
        {r:'b',t:'¡Sí! Usa el cupón BIENVENIDA10 y obtén un **10% de descuento** en tu primer envío. ¿Te ayudo a cotizar?',m:'09:15',by:'Agente IA'}]},
    {in:'SW',color:'#1cae8a',name:'Sarah Whitmore',ch:'WhatsApp',lang:'en',time:'08:48',assigned:null,status:'bot',
      msgs:[{r:'u',t:'What are your fees?',m:'08:48'},{r:'b',t:'Fees depend on the corridor. For PEN → BRL it is 1.5%. Want a full quote?',m:'08:48',by:'Agente IA'}]},
    {in:'DR',color:'#5B51B3',name:'Diego Ramos',ch:'WhatsApp',lang:'pt',time:'09:02',assigned:null,status:'bot',
      msgs:[{r:'u',t:'Sou novo por aqui, tem promoção para o primeiro envio?',m:'08:58'},
        {r:'tool',t:'',tool:'get_cliente',endpoint:'GET https://api.brasper.com/v1/clientes?telefono=51999000001',req:'{telefono: "51999000001"}',res:'{cliente_id: null, nombre: null, segmento: null, compras: 0}',m:'08:58'},
        {r:'tool',t:'',tool:'buscar_promociones',endpoint:'GET https://api.brasper.com/v1/promociones?segmento=nuevo',req:'{segmento: "nuevo"}',res:'[{codigo: "BIENVENIDA20", descuento: 20, tipo: "porcentaje", max: 50}]',m:'08:58'},
        {r:'b',t:'Bienvenido Diego! 🎉 Como nuevo cliente tienes **20% de descuento** en tu primer envío (máx. US$ 50). Usa el cupón **BIENVENIDA20**. ¿Quieres usarlo ahora?',m:'08:59',by:'Agente IA'},
        {r:'u',t:'Si, quiero enviar 200 soles',m:'09:00'},
        {r:'tool',t:'',tool:'tipo_de_cambio',endpoint:'GET https://api.brasper.com/v1/tipo-de-cambio?from=PEN&to=BRL',req:'{from: "PEN", to: "BRL"}',res:'{tasa: 1.42, comision: 1.5, vigencia: "hoy"}',m:'09:00'},
        {r:'b',t:'¡Claro! 200 PEN → BRL hoy: 1 PEN = 1,42 BRL. Recibirías **R$ 284** menos la comisión del 1,5%. Con tu cupón **BIENVENIDA20**, la comisión se reduce al 0%. ¿Confirmas?',m:'09:01',by:'Agente IA'},
        {r:'u',t:'Obrigado!',m:'09:02'},{r:'b',t:'De nada, Diego! 👋 Vuelve cuando quieras.',m:'09:02',by:'Agente IA'}]},
    {in:'VR',color:'#229ED9',name:'Valeria Rojas',ch:'Telegram',lang:'es',time:'08:56',assigned:null,status:'bot',
      msgs:[{r:'u',t:'Hola, ¿puedo reservar una cita para mañana?',m:'08:55'},
        {r:'tool',t:'',tool:'agenda_disponibilidad',endpoint:'GET https://api.cauce.ai/calendar/slots?tenant=brasper&day=mañana',req:'{servicio: "asesoria", canal: "telegram"}',res:'[{hora: "10:00"}, {hora: "16:30"}]',m:'08:55'},
        {r:'b',t:'Sí, tengo disponible mañana a las 10:00 o 16:30. ¿Cuál prefieres?',m:'08:56',by:'Agente IA'}]},
    {in:'LP',color:'#DD6A3C',name:'Luis Paredes',ch:'WhatsApp',lang:'es',time:'08:30',assigned:null,status:'bot',
      msgs:[{r:'u',t:'500 a Brasil',m:'08:30'},
        {r:'tool',t:'',tool:'get_cliente',endpoint:'GET https://api.brasper.com/v1/clientes?telefono=51966000002',req:'{telefono: "51966000002"}',res:'{cliente_id: 4921, nombre: "Luis Paredes", segmento: "frecuente", compras: 12, ultima: "2026-06-20"}',m:'08:30'},
        {r:'b',t:'¡Hola Luis! Cliente frecuente por aquí 😊. Para 500 PEN a Brasil recibes **R$ 710 aprox.**, con tu tarifa preferencial de **1,2%** (vs 1,5% general). ¿Continuamos?',m:'08:30',by:'Agente IA'}]}
  ],

  /* ---------- knowledge base / RAG ---------- */
  kbFiles: [
    {name:'Politicas_de_remesas_2026.pdf',size:'2,4 MB',chunks:142,status:'indexado'},
    {name:'Preguntas_frecuentes.docx',size:'380 KB',chunks:58,status:'indexado'},
    {name:'Tarifas_y_corredores.xlsx',size:'120 KB',chunks:24,status:'indexado'},
    {name:'Manual_de_cumplimiento.pdf',size:'5,1 MB',chunks:0,status:'indexando'}
  ],

  /* ---------- billing / uso ---------- */
  billing: {
    plan:'Pro', price:'US$ 149/mes',
    usage:[
      {label:'Mensajes IA',  used:62000, total:100000, unit:''},
      {label:'Tokens LLM',   used:8.4,  total:15,     unit:'M'},
      {label:'Conversaciones',used:1284, total:5000,   unit:''},
      {label:'Asientos de equipo',used:6, total:10,   unit:''}
    ],
    costByModel:[{m:'Claude',v:54,c:'#0E7C66'},{m:'DeepSeek',v:33,c:'#2C6FB0'},{m:'GPT-4o',v:13,c:'#C98A1E'}],
    invoices:[{id:'INV-2026-06',date:'01 jun 2026',amount:'US$ 149,00',status:'Pagada'},{id:'INV-2026-05',date:'01 may 2026',amount:'US$ 149,00',status:'Pagada'},{id:'INV-2026-04',date:'01 abr 2026',amount:'US$ 149,00',status:'Pagada'}],
    plans:[
      {name:'Starter',price:'US$ 49',feats:['10k mensajes IA','1 canal','2 asientos','Webchat']},
      {name:'Pro',price:'US$ 149',feats:['100k mensajes IA','WhatsApp + Webchat + Telegram','10 asientos','RAG + analítica'],current:true},
      {name:'Business',price:'US$ 399',feats:['500k mensajes IA','Canales ilimitados','Asientos ilimitados','SSO + observabilidad']}
    ]
  },

  /* ---------- analítica ---------- */
  intents:[{n:'Cotización de remesa',v:54,c:'#0E7C66'},{n:'Requisitos',v:19,c:'#2C6FB0'},{n:'Hablar con asesor',v:14,c:'#DD6A3C'},{n:'Cupones',v:8,c:'#C98A1E'},{n:'Saludo / otros',v:5,c:'#5B51B3'}],
  languages:[{n:'Español',v:68,c:'#0E7C66'},{n:'Português',v:24,c:'#2C6FB0'},{n:'English',v:8,c:'#C98A1E'}],
  funnel:[{n:'Conversaciones iniciadas',v:1284,w:100},{n:'Intención detectada',v:1052,w:82},{n:'Cotización entregada',v:744,w:58},{n:'Lead capturado',v:398,w:31},{n:'Handoff / conversión',v:48,w:7}],
  observability:[{label:'Latencia media (p50)',v:'1,4 s',ok:true},{label:'Latencia p95',v:'3,8 s',ok:true},{label:'Errores LLM (24h)',v:'0,3%',ok:true},{label:'Uptime (30d)',v:'99,95%',ok:true},{label:'Webhooks fallidos',v:'2',ok:false},{label:'Costo IA hoy',v:'US$ 18,40',ok:true}],

  /* ---------- equipo ---------- */
  team:[
    {in:'AC',color:'#0E7C66',name:'Alberth Castillo',email:'gestion@navia.com.pe',role:'owner'},
    {in:'LM',color:'#2C6FB0',name:'Lucía Mendoza',email:'lucia@brasper.com',role:'builder'},
    {in:'RA',color:'#C98A1E',name:'Raúl Ávila',email:'raul@brasper.com',role:'agent'},
    {in:'PT',color:'#5B51B3',name:'Pedro Torres',email:'pedro@brasper.com',role:'analyst'},
    {in:'SV',color:'#B0436B',name:'Sofía Vega',email:'sofia@brasper.com',role:'billing'}
  ],

  /* ---------- arquitectura ---------- */
  archLayers:[
    {l1:'Frontend interno',l2:'Maqueta hoy · Next.js/React si duele',ic:'template',items:[['Dashboard',0],['Settings',0],['Agent Inbox',2],['Sin builder visual',1]]},
    {l1:'Contenedores',l2:'Docker Compose primero',ic:'layers',items:[['api',2],['worker',2],['redis',1],['postgres',2],['reverse-proxy',2]]},
    {l1:'API multi-tenant',l2:'FastAPI + Uvicorn',ic:'shield',items:[['Tenant Resolver',1],['Admin/Tenant API',2],['Webhook router',0],['Rate limiter',2]]},
    {l1:'Servicios',l2:'Python',ic:'layers',items:[['tenant',0],['channel',1],['ai',1],['usage logs',2],['billing manual',1]]},
    {l1:'Motor IA',l2:'LangGraph + adapters propios',ic:'flow',heart:true,items:[['Agente IA',1],['Tool Router',1],['Handoff',1],['OpenAI/DeepSeek/Claude',2],['LangChain auxiliar',2]]},
    {l1:'Datos',l2:'aislados por tenant',ic:'layers',items:[['Redis · {tenant}:',1],['PostgreSQL · logs/conversaciones',2],['RLS cuando haya escala',2]]},
    {l1:'Canales',l2:'entrada',ic:'cast',items:[['WhatsApp Cloud API',1],['Webchat widget',0],['Telegram Bot API',2],['Instagram / Messenger',2]]}
  ],
  deploymentContainers:[
    {name:'api', tech:'FastAPI + Uvicorn', status:'Fase 1', body:'Recibe webhooks, resuelve tenant, llama a LangGraph y responde por el adapter del canal.'},
    {name:'worker', tech:'Python', status:'Fase 1', body:'Procesa reintentos, audios, plantillas, tareas programadas y agregación de consumo.'},
    {name:'redis', tech:'Redis', status:'Reutiliza', body:'Memoria corta, locks y estado temporal con prefijo {tenant}: para no mezclar clientes.'},
    {name:'postgres', tech:'Postgres', status:'Fase 1/2', body:'Conversaciones, logs de tokens, costos y auditoría. RLS solo cuando haya varios clientes reales.'},
    {name:'reverse-proxy', tech:'Caddy / Nginx / Traefik', status:'Fase 1', body:'TLS, dominios, rutas de webhooks, health checks y límites básicos.'},
    {name:'admin-web', tech:'HTML hoy · Next.js después', status:'Fase 2', body:'Panel interno para operar tenants cuando editar YAML a mano empiece a doler.'}
  ],
  tenantApiFlow:[
    {title:'1. Entrada', body:'WhatsApp usa phone_number_id, Telegram usa bot_id/webhook y Webchat usa header, subdominio o public token.'},
    {title:'2. TenantResolver', body:'Convierte el identificador del canal en tenant_id y carga prompt, proveedor IA, secretos, handoff y límites.'},
    {title:'3. ChatUseCase', body:'Normaliza el mensaje y pasa contexto limpio al orquestador. No mete llaves ni tokens en el prompt.'},
    {title:'4. LangGraph', body:'Decide si responde, llama herramienta, reserva cita, entiende audio o deriva a asesor.'},
    {title:'5. Adapter', body:'Devuelve la respuesta por WhatsApp, Telegram, Webchat o API externa sin cambiar la lógica central.'}
  ],
  aiStack:[
    {name:'LangGraph', body:'Motor principal del agente. Modela estados, rutas, tools, handoff, reintentos y decisiones por conversación.'},
    {name:'LangChain', body:'Capa auxiliar si conviene para prompts/tools, pero no manda la arquitectura ni reemplaza adapters propios.'},
    {name:'Model adapters', body:'OpenAI, DeepSeek y Claude por tenant, con fallback, medición de tokens y secret_ref aislado.'},
    {name:'Tool Router', body:'Convierte APIs del cliente en herramientas: calendario, CRM, pedidos, tasas, citas o cualquier REST.'}
  ],

  /* ---------- roadmap ---------- */
  roadmap:[
    {ph:'Fase 0',name:'Validar (no construir)',type:'now',deliver:'Cerrar 1 piloto pagado con esta maqueta. Definir precio: setup + fee mensual + costo LLM repasado.',gate:'No se construye nada hasta tener un piloto comprometido (o Brasper como cliente cero).'},
    {ph:'Fase 1',name:'Multi-tenant mínimo + contenedores',type:'build',deliver:'Docker Compose con api, worker, redis, postgres opcional y reverse-proxy. Sobre el código real: config de tenants, resolver por phone_number_id/bot_id/header, prefijo Redis por cliente, tokens/keys por tenant, medición de consumo y persistencia real.',gate:'Brasper corre tenant-aware en contenedores sin regresión + aislamiento cruzado probado.'},
    {ph:'Fase 2',name:'Segundo cliente',type:'build',deliver:'Onboardear al tenant #2 y medir el trabajo manual. Conector de API genérico (como tool), Telegram Bot API, plantillas de WhatsApp bajo demanda, panel interno (proveedor IA + keys + consumo).',gate:'El onboarding del 2º cliente es sostenible en tiempo.'},
    {ph:'Fase 3',name:'Con ingresos recurrentes',type:'later',deliver:'Recién aquí: builder visual, RBAC de cliente, RAG, Agent Inbox — solo lo que un cliente concreto pida, no por completitud.',gate:'—'}
  ],

  /* ---------- v2: esenciales + conector API genérico + embebidos + plantillas WhatsApp ---------- */
  coreKeys: ['whatsapp_cloud','telegram','openai','anthropic_claude','deepseek','google_calendar','google_sheets','culqi','mercadopago','generic_webhook'],
  genericApi: {
    baseUrl:'https://api.miempresa.com/v1',
    auth:'Bearer / OAuth2',
    authTypes:['Ninguna','API Key (header)','API Key (query)','Bearer / OAuth2','OAuth2 client credentials','Basic Auth'],
    endpoints:[
      {name:'get_cliente',     method:'GET',    path:'/clientes/{{cliente_id}}',        purpose:'Obtener datos del cliente (nombre, email, segmento) para personalizar o validar que existe.', out:'cliente'},
      {name:'consultar_stock', method:'GET',    path:'/stock?sku={{sku}}',              purpose:'Consultar disponibilidad de un producto antes de ofrecerlo o confirmar el pedido.',          out:'stock'},
      {name:'crear_pedido',    method:'POST',   path:'/pedidos',                        purpose:'Crear un pedido con los productos del chat. Devuelve el número de pedido.',                  out:'pedido'},
      {name:'estado_pedido',   method:'GET',    path:'/pedidos/{{pedido_id}}/estado',   purpose:'Consultar el estado de seguimiento de un pedido cuando el usuario pregunta.',                out:'estado_pedido'},
      {name:'buscar_productos',method:'GET',    path:'/productos?q={{texto}}',          purpose:'Buscar productos del catálogo para responder consultas y recomendar.',                       out:'productos'},
      {name:'cancelar_pedido', method:'DELETE', path:'/pedidos/{{pedido_id}}',          purpose:'Cancelar un pedido a petición del usuario; devuelve confirmación.',                          out:'cancelacion'}
    ],
    note:'Un conector es configuración declarativa (JSON) por tenant: defines base URL, autenticación y endpoints una sola vez, y el nodo API del flujo solo referencia connector_id + endpoint. La interpolación {{variable}} y el mapeo de respuesta por JSONPath cubren cualquier API REST sin programar ni desplegar. Los secretos viven en un vault referenciado por id (nunca en el flujo).'
  },
  embeds: [
    {name:'Webchat (widget)', snippet:'<!-- Pegar antes de </body>. El snippet no cambia: la config vive server-side por tenant -->\n<script async\n  src="https://cdn.cauce.ai/widget/v1/loader.js"\n  data-tenant="brasper"\n  data-token="pub_live_3f9a2c"\n  data-flow="ventas"\n  data-color="#0E7C66"\n  data-position="bottom-right"></script>'},
    {name:'Calendario / agenda (embebible)', snippet:'<!-- Reserva embebida, estilo Calendly -->\n<div id="cauce-calendar"></div>\n<script async\n  src="https://cdn.cauce.ai/calendar/v1/loader.js"\n  data-tenant="brasper"\n  data-token="pub_live_3f9a2c"\n  data-service="asesoria"\n  data-target="#cauce-calendar"></script>'},
    {name:'Webchat (init por JS, para SPA)', snippet:'<script async src="https://cdn.cauce.ai/widget/v1/loader.js"></script>\n<script>\n  window.cauceSettings = { tenant: "brasper", token: "pub_live_3f9a2c", flow: "soporte" };\n  // window.Cauce.open() para abrir el chat desde tu propio botón\n</script>'}
  ],
  waTemplates: {
    why:'Las plantillas son los únicos mensajes que la empresa puede iniciar proactivamente: fuera de la ventana de 24 h (que se abre/refresca cuando el usuario escribe) solo se envían plantillas pre-aprobadas por Meta. Se crean una vez, pasan revisión y se reutilizan sustituyendo solo sus variables.',
    categories:[
      {name:'Marketing',desc:'Promos, ofertas, carrito abandonado, reactivación. La más flexible pero la más cara y vigilada; requiere opt-in y "pacing" en plantillas nuevas.'},
      {name:'Utility',desc:'Transaccionales: confirmación de pedido, envío, recordatorio de cita/pago, factura. Más baratas y GRATIS dentro de la ventana de 24 h.'},
      {name:'Authentication',desc:'Única válida para OTP y verificación. Cuerpo de texto fijo, sin URLs/media/emojis y código ≤ 15 caracteres; se cobra siempre.'}
    ],
    example:{name:'recordatorio_cita',category:'UTILITY',language:'es',body:'Hola {{1}}, te recordamos tu cita en {{2}} el día {{3}} a las {{4}}. Por favor confirma tu asistencia.',vars:['{{1}} nombre','{{2}} sucursal','{{3}} fecha','{{4}} hora']},
    approval:'Estados: PENDING, APPROVED, REJECTED (con motivo), PAUSED (por feedback negativo) y DISABLED. La mayoría se aprueba en ~5–30 min (hasta 24–48 h en cuentas nuevas). Editar una aprobada la vuelve a PENDING.',
    sending:'POST /{PHONE_NUMBER_ID}/messages con Authorization: Bearer, type=template y el objeto template (name + language.code exactos al aprobado; components[] solo si hay variables/media/botones). Devuelve un message id y luego webhooks de estado.'
  },
  waTemplateList: [
    {name:'recordatorio_cita',  cat:'UTILITY',        lang:'es', status:'APPROVED', body:'Hola {{1}}, te recordamos tu cita en {{2}} el día {{3}} a las {{4}}.'},
    {name:'confirmacion_pedido',cat:'UTILITY',        lang:'es',    status:'APPROVED', body:'¡Gracias {{1}}! Tu pedido {{2}} fue confirmado y llega el {{3}}.'},
    {name:'codigo_otp',         cat:'AUTHENTICATION', lang:'es',    status:'APPROVED', body:'Tu código de verificación es {{1}}. No lo compartas con nadie.'},
    {name:'promo_julio',        cat:'MARKETING',      lang:'es',    status:'PENDING',  body:'{{1}}, julio con 20% en envíos a {{2}}. Usa CAUCE20. ¿Aprovechas?'},
    {name:'reactivacion',       cat:'MARKETING',      lang:'pt',    status:'REJECTED', body:'{{1}}, sentimos sua falta! Volte e ganhe um cupom.'}
  ]
};
