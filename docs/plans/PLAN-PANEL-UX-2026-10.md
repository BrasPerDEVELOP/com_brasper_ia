# Plan de mejora UX/UI — Panel de operación Brasper

> Fecha: 2026-10-07 · Rama base: `chore/gate-single-tenant-ci` · Alcance: `web/` (Next.js 16 + React 19 + Tailwind 4)
> Complementa el Sprint 4 de [PLAN-MEJORAS-2026-10.md](PLAN-MEJORAS-2026-10.md) (funcionalidad). Este documento cubre **diseño, velocidad percibida, identidad Brasper y responsive**.

> **Estado: ✅ Ejecutado (2026-10-07) en la rama `chore/gate-single-tenant-ci`.** Fases A–E implementadas; ver §9 para el detalle por entregable y §8 para las decisiones que se desviaron del plan original (sin dependencias nuevas, SSE pospuesto). Validado con `run_checks` 46/46, `tsc` y `next build` en verde.

## 1. Diagnóstico

### 1.1 Lo que se ve hoy (Umbler Talk, herramienta externa)

Captura de referencia: bandeja "Conversas" en Umbler Talk, tema oscuro genérico, lista a la izquierda, hilo al centro, compositor abajo.

| Problema percibido | Causa visible |
|---|---|
| "Se siente lento" | Lista y hilo recargan completos; sin estados de carga ni optimismo; scroll del hilo salta al llegar mensajes |
| "Muy minimalista, sin espíritu Brasper" | Paleta gris/azul de la plataforma, logo de Umbler, tipografía por defecto; nada de Brasper salvo el texto |
| "Colores poco agradables" | Fondo negro plano, burbujas con poco contraste, badges verdes que compiten con el acento azul |
| "Scroll malo" | Lista de 66 conversaciones sin virtualización ni agrupación; dos scrolls anidados sin indicación |
| "No responsive" | Tres columnas fijas; en tablet/móvil se corta |

### 1.2 Lo que tenemos en `web/` (panel propio)

Fortalezas: ya existe la bandeja (`app/conversaciones/page.tsx`) con takeover, adjuntos, tarjeta del lead, roles y permisos, y el backend expone todo lo necesario (`/api/conversations`, `/reply`, `/upload`, `/status`, `/assign`, `/advisors`, `/ops/*`).

Debilidades concretas, con archivo:

| Área | Problema | Dónde |
|---|---|---|
| Identidad | Acento cian neón `#00f0ff` + "glassmorphism" no es Brasper. Logo es un trazo genérico. Tipografías cargadas (Bricolage, Hanken) pero `globals.css` fuerza `Inter` y las ignora | `web/app/globals.css:1-57`, `web/app/layout.tsx:6-8`, `web/components/AppFrame.tsx:80-84` |
| Rendimiento percibido | `backdrop-filter: blur(16px)` en sidebar, header, lista, hilo, cards, tabla y chatbar a la vez: caro en GPU, provoca "lag" al hacer scroll | `globals.css` (12 usos de `--glass-blur`) |
| Rendimiento percibido | Animación `rise` en cada burbuja y en toda la página al cambiar ruta; `transform: translateX` en hover de cada ítem | `globals.css` `.rise`, `.msg`, `.citem:hover` |
| Tiempo real | Polling cada 4 s que reemplaza la lista completa y el hilo (`setConvs(d.conversations)`), re-render total; sin diff ni "nuevo mensaje" | `conversaciones/page.tsx:52-66` |
| Scroll | El hilo no hace auto-scroll al último mensaje ni al enviar; no hay botón "ir abajo"; `scroll-behavior: smooth` anima incluso cargas iniciales | `globals.css .msgs`, `page.tsx` (sin `ref` al final) |
| Scroll | Lista sin virtualización ni paginación (`limit=50` fijo en backend) | `backend/core/db.py:628` |
| Layout | `grid2` con alto `calc(100vh - 72px - 64px)`; en <960px pasa a una columna y el hilo queda debajo de toda la lista (hay que hacer scroll infinito para llegar al chat) | `globals.css @media(max-width:960px)` |
| Layout | Sidebar en móvil se convierte en fila horizontal con scroll: poco usable con el pulgar | ídem |
| Jerarquía | En la lista el `user_ref` crudo (`wa:51999…`) va en negrita y el id interno + "N msgs" ocupa una línea entera; no hay nombre del lead, avatar ni hora relativa | `page.tsx:160-175` |
| Jerarquía | Estado como texto crudo (`active`, `handoff`, `closed`) en inglés | `page.tsx:166, 182` |
| Compositor | Dos filas de controles mezcladas (texto + adjuntar + URL imagen); `alert()` para errores | `page.tsx:214-237` |
| Accesibilidad | Contraste de `--muted` sobre vidrio bajo; focos cian sobre fondo cian; sin `aria-label` en botones de icono | `globals.css`, `page.tsx` |
| Dependencias | Tailwind 4 instalado pero no usado (todo CSS global con clases a mano); sin librería de componentes ni iconos | `package.json` |
| Resto | `TenantSelect.tsx` muerto; `public/*.svg` de plantilla Next (vercel, globe) | `web/components`, `web/public` |

## 2. Principios de diseño del nuevo panel

1. **Brasper primero**: el panel debe reconocerse como Brasper en un segundo (logo, azul Brasper, acento Perú↔Brasil), no como "otro inbox".
2. **Operación rápida**: el asesor vive en la bandeja; cada acción frecuente (tomar, responder, respuesta rápida, cerrar) a un clic o atajo de teclado.
3. **Calma visual**: superficies planas con sombra sutil, sin blur ni neón; movimiento solo donde informa (llegó mensaje, cambió estado).
4. **Legible a la primera**: nombre del cliente > último mensaje > hora relativa; estados en español con color semántico.
5. **Responsive real**: desktop 3 columnas, tablet 2, móvil 1 con navegación lista → chat → ficha.
6. **Tokens, no valores sueltos**: todo color/espacio/tipografía sale de variables CSS en `globals.css` para cambiar de tema en un solo lugar (claro/oscuro).

## 3. Sistema visual Brasper (tokens)

> **Pendiente de confirmar con el equipo**: hex oficial del azul Brasper, logo en SVG (horizontal + isotipo) y tipografía de marca. Los valores siguientes están derivados del arte promocional (azul profundo + amarillo/verde Brasil + rojo Perú) y se reemplazan en un solo archivo.

### 3.1 Paleta

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--brand` | `#0A3D91` | `#3B7BFF` | Azul Brasper: botones primarios, enlaces, ítem activo |
| `--brand-strong` | `#072B68` | `#2A62D8` | Hover/pressed del primario |
| `--brand-soft` | `#E8EFFC` | `rgba(59,123,255,.14)` | Fondos de selección, chips informativos |
| `--accent-br` | `#F2C230` | `#F7D25A` | Amarillo Brasil: detalles de marca, badge "Promo", conteo no leídos |
| `--accent-pe` | `#D62839` | `#F0566A` | Rojo Perú: solo alertas/SLA vencido, nunca decorativo |
| `--ok` | `#1B9E5A` | `#3CCB7F` | Estados positivos (envío entregado, cerrado) |
| `--warn` | `#D97706` | `#F59E0B` | Esperando asesor / SLA por vencer |
| `--bg` | `#F5F7FB` | `#0F1420` | Fondo de la app |
| `--surface` | `#FFFFFF` | `#161C2B` | Paneles, cards, lista |
| `--surface-2` | `#EEF2F8` | `#1E2638` | Burbuja del cliente, cabeceras de tabla |
| `--ink` | `#0F172A` | `#F1F5F9` | Texto principal |
| `--muted` | `#5B6475` | `#9AA4B8` | Texto secundario (contraste AA sobre `--surface`) |
| `--line` | `#E3E8F0` | `#283146` | Bordes |

Reglas: un solo acento fuerte por pantalla (azul). El amarillo aparece como detalle fino (barra superior de 3 px bajo el header, badge de no leídos, logo). Los colores de canal (WhatsApp verde, Telegram celeste) solo en el icono del canal, no en el fondo del ítem.

### 3.2 Tipografía

- Display: **Bricolage Grotesque** (ya cargada vía `next/font`) para títulos y numéricos grandes.
- Texto: **Hanken Grotesk** para UI; `JetBrains Mono` solo para ids y montos tabulares.
- Escala: 12 / 13 / 14 (base) / 16 / 20 / 28. Interlineado 1.5 en chat, 1.4 en listas.
- Corregir `globals.css` para usar `var(--font-disp)` / `var(--font-body)` en vez de `'Inter'`.

### 3.3 Forma y movimiento

- Radios: 8 px controles, 12 px cards, 16 px burbujas (con esquina de 4 px hacia el autor).
- Sombras: una sola `--shadow: 0 1px 2px rgba(15,23,42,.06), 0 4px 12px rgba(15,23,42,.06)`. Sin `backdrop-filter`.
- Movimiento: transiciones de 120–160 ms solo en `background-color`/`opacity`. Burbuja nueva: fade de 150 ms. Respetar `prefers-reduced-motion`.
- Tema: claro por defecto para operación de día (mejor lectura de comprobantes/imágenes), oscuro con toggle y persistencia en `localStorage`.

## 4. Arquitectura de la bandeja (pantalla principal)

```
┌─ Rail 72px ─┬─ Lista 340px ───────────┬─ Hilo (flex) ──────────────┬─ Ficha 300px ─┐
│ Logo        │ Buscar  ⌘K   Filtros ▾  │ Nombre · canal · estado    │ Cliente       │
│ Bandeja ●12 │ [Entrada][Míos][Bot]... │ ──────────────────────────  │ Ruta BRL→PEN  │
│ Chat prueba │ ┌ Avatar  Márcia   12:43│   burbujas…                │ Monto / tasa  │
│ Consumo     │ │ WA  "Tô com pressa"  2│                            │ Promo / TC    │
│ Bot         │ └ ⏱ esperando 6 min     │ ▼ ir al final (3 nuevos)    │ Última cotiz. │
│ Integrac.   │ …                       │ ──────────────────────────  │ Cuentas       │
│ Plantillas  │                         │ [Respuestas rápidas ▾] 📎  │ Asignado a    │
│ ───         │                         │ Escribe…            Enviar │ Etiquetas     │
│ Tema  Usuario│                        │ Bot ● activo / ■ pausado   │ Notas internas│
└─────────────┴─────────────────────────┴────────────────────────────┴───────────────┘
```

### 4.1 Rail de navegación (reemplaza sidebar de 260 px)
- Iconos con tooltip; etiqueta visible al expandir (hover o pin). Libera 190 px para el chat.
- Badge con conversaciones en `handoff` sin responder (SLA) sobre "Bandeja".
- Abajo: toggle tema, avatar del asesor, salir.

### 4.2 Lista de conversaciones
- **Pestañas**: Entrada (todas abiertas) · Míos · Libres (cola) · Con el bot · Cerrados. Conteo por pestaña.
- **Ítem**: avatar con inicial (color estable por hash del `user_ref`), nombre del lead (`lead_data.nombre`) con fallback al número formateado, icono de canal pequeño, hora relativa ("hace 6 min"), vista previa en una línea, badge de no leídos en amarillo, chip de estado en español (`Con el bot` / `Atendiendo: Nadia` / `Cerrado`), indicador "⏱ esperando 6 min" cuando está en handoff sin respuesta.
- **Búsqueda** por nombre/número/texto con atajo `⌘K`/`Ctrl K`; filtros por canal, estado, asignado, etapa comercial (del Sprint 4).
- **Scroll**: virtualización con `@tanstack/react-virtual` (lista > 100 ítems sin lag); paginación con cursor `updated_at` en `GET /api/conversations?cursor=&limit=`; separadores "Hoy / Ayer / Semana".
- **Atajos**: `↑/↓` navegar, `Enter` abrir, `T` tomar, `R` devolver al bot, `E` cerrar.

### 4.3 Hilo
- Cabecera fija: nombre, canal, estado, botón primario contextual (Tomar / Devolver al bot / Cerrar), menú "…" (asignar a otro asesor, eliminar con guard).
- Burbujas: cliente a la izquierda en `--surface-2`; bot/asesor a la derecha en `--brand-soft` con borde `--brand`. **Diferenciar bot vs asesor** (icono ✨ "Bot" o avatar del asesor + nombre). Hoy ambos son `assistant`: el backend debe marcar `sender: "bot" | "agent" | "user"` o el panel infiere por `created_at` vs eventos de audit.
- Separadores de fecha, hora al pie de cada grupo de burbujas, estado de entrega (enviado/fallido) tomado de `delivery` en la respuesta de `/reply` y `/upload`.
- Imágenes con lightbox (clic amplía), PDFs con icono + nombre + tamaño; audio con reproductor nativo cuando `kind=audio`.
- **Scroll**: auto-scroll al final al abrir y al enviar; si el asesor está leyendo arriba y llega mensaje nuevo, botón flotante "▼ 3 nuevos"; `scroll-behavior: auto` en carga inicial, suave solo en interacción.
- Skeleton de carga (3 burbujas grises) en vez de pantalla vacía.

### 4.4 Compositor
- Textarea autoexpandible (1–6 líneas), `Enter` envía, `Shift+Enter` salto de línea.
- Fila de herramientas: 📎 adjuntar (drag & drop sobre el hilo + pegar imagen del portapapeles), ⚡ respuestas rápidas (popover buscable con variables `{nombre}`, `{monto}`), 😀 emoji opcional, 🔗 imagen por URL dentro del menú 📎 (no como campo permanente).
- Envío **optimista**: la burbuja aparece al instante en gris con reloj; se confirma o marca error (⚠ reintentar). Reemplaza `alert()` por toasts.
- Pie: estado del bot ("Bot activo · responde solo" / "Bot en pausa · atiendes tú") con el switch de takeover, como el toggle "Brasper" de Umbler pero explícito.
- Modo **Notas internas** (tab junto a Mensaje): no se envía al cliente, se guarda en `conversation_notes` (backend nuevo, pequeño).

### 4.5 Ficha del cliente (columna derecha, colapsable)
- Datos del lead ya disponibles: idioma, ruta, modo, montos, tasa, estado TC, promo, tipo cliente, nombre, documento, banco/PIX, beneficiario.
- Última cotización en formato Brasper ("R$ 400 → S/ 246 · con promo S/ 251"), cuentas de depósito mostradas, enlace a perfil Brasper si hay `customer_id`.
- Asignación: select de asesores (`/api/advisors` con carga), etiquetas (Sprint 4), notas.
- En tablet se convierte en drawer; en móvil en pantalla aparte.

## 5. Responsive

| Ancho | Layout |
|---|---|
| ≥ 1440 | Rail + Lista + Hilo + Ficha |
| 1024–1439 | Rail + Lista + Hilo; Ficha como drawer desde la derecha (botón ⓘ en cabecera) |
| 768–1023 | Rail colapsado (solo iconos) + Lista **o** Hilo (al abrir una conversación la lista se desliza fuera; botón ← para volver) |
| < 768 | Barra inferior de 4 iconos (Bandeja, Chat, Consumo, Más); lista a pantalla completa → hilo a pantalla completa → ficha como hoja inferior; compositor pegado abajo con `env(safe-area-inset-bottom)`; `100dvh` en vez de `100vh` |

Implementación: `grid-template-areas` por breakpoint en `globals.css` + estado `view: "list" | "thread" | "profile"` en móvil; el hilo usa `position: sticky` para cabecera y compositor.

## 6. Velocidad real y percibida

1. **Quitar `backdrop-filter` y sombras pesadas** (mayor ganancia inmediata en scroll).
2. **Polling inteligente** ahora: `GET /api/conversations?since=<updated_at>` devuelve solo cambios; el hilo pide `?after=<last_created_at>` y hace append, no replace. Intervalo 3 s activo, 15 s en pestaña oculta.
3. **Tiempo real después**: endpoint SSE `GET /api/events` (FastAPI `StreamingResponse`) que emite `conversation.updated` y `message.created` desde el worker vía Redis pub/sub (ya hay Redis para el lock). El panel cae a polling si SSE falla.
4. **Estado de datos** con `@tanstack/react-query`: caché por conversación, revalidación en foco, actualizaciones optimistas, deduplicación de peticiones.
5. **Virtualización** de lista e hilo largo (`@tanstack/react-virtual`).
6. **Imágenes**: `/api/media` con `Cache-Control` privado de 1 h y miniaturas (`?w=320`) para la lista/hilo; original en lightbox. Evita re-descargar cada 4 s.
7. **Carga inicial**: `next/font` ya evita FOIT; precargar la lista en el layout; skeletons en lista, hilo y ficha.
8. **Medición**: Lighthouse en CI para `/conversaciones` (performance ≥ 90, a11y ≥ 95) y `web-vitals` enviado a `/api/ops/metrics`.

## 7. Resto de pantallas (consistencia)

- **Login**: tarjeta blanca centrada sobre fondo azul Brasper con isotipo; campos con etiqueta visible, error inline.
- **Chat de prueba**: mismas burbujas y compositor que la bandeja (componente compartido `Thread`); badge "Modo prueba · consume LLM".
- **Consumo**: stat tiles (llamadas, tokens, costo hoy/mes) + gráfico diario desde `/api/ops/usage-daily`; tabla con paginación. Seguir la skill `dataviz` para colores.
- **Bot / Prompt**: formulario en dos columnas con secciones (LLM, Handoff, Cotizador) y vista "Tasas Brasper en vivo" con hora de actualización.
- **Integraciones / Plantillas**: cards con estado (conectado/no) y acciones; sin cambios funcionales.
- **Ops** (nueva, rol owner): alertas de `/api/ops/alerts`, dead-letter, métricas. Hoy no se ve en el panel.

## 8. Base técnica

| Decisión del plan | Qué se hizo | Por qué |
|---|---|---|
| Tailwind 4 + tokens CSS en `globals.css` | ✅ Tokens claro/oscuro en `web/app/globals.css`; tema con `data-theme` y script anti-parpadeo en `layout.tsx` | Un solo lugar para cambiar la marca |
| `shadcn/ui` (Radix) para Dialog/Popover/Tabs/Toast | ⚠️ **No se añadió.** Popovers, pestañas, toasts y lightbox son componentes propios con roles ARIA y teclado (Esc, Enter) | Evitar sumar ~15 dependencias para 5 patrones simples; se puede migrar después sin tocar la API de los componentes |
| `lucide-react` | ⚠️ **No se añadió.** `components/Icon.tsx` ampliado con los iconos necesarios (paths estáticos) | Mismo motivo; cero peso extra |
| `@tanstack/react-query` | ⚠️ **No se añadió.** Polling incremental propio: lista con `?since=` fusionada por id, hilo con `?after=` en append, recarga completa cada 60 s, envío optimista con reintento | Cubre caché, optimismo y deduplicación sin otra librería |
| `@tanstack/react-virtual` | ⚠️ **No se añadió.** Virtualización propia en `ConversationList` (ventana + espaciadores a partir de 60 ítems); hilo recorta a los últimos 300 con "Cargar anteriores" | Alto de fila casi fijo; 40 líneas bastan |
| `date-fns` | ⚠️ **No se añadió.** `lib/format.ts` (`relTime`, `dayLabel`, `clockTime`) con `Intl` | Suficiente para "hace 6 min / ayer / lun" |
| Componentes en `web/components/inbox/*` | ✅ `ConversationList`, `ConversationItem`, `Thread`, `MessageBubble`, `MediaBubble`, `Composer`, `LeadCard`, `Lightbox`, `types.ts` | `page.tsx` quedó como orquestador de estado |
| Eliminar `TenantSelect.tsx` y SVG de plantilla; `public/brand/` + favicon | ✅ Eliminados; `public/brand/isotipo.svg` provisional y `app/icon.svg` | Marca propia (pendiente SVG oficial) |

Cambios de backend realizados (caso **46** en `backend/tests/run_checks.py`):
- `GET /api/conversations`: `?status&channel&assigned(me|none|email)&q&since&before&limit`; cada fila trae `lead_name`, `last_role`, `waiting_since`; respuesta con `next_before` (cursor). `since`/`before` son inclusivos porque el timestamp es de segundos; el panel fusiona por id.
- `GET /api/conversations/{id}?after=`: solo mensajes nuevos (`partial: true`); mensajes con `sender: user|bot|agent` y `agent_email`. Columnas nuevas en `messages` (idempotentes en `_ensure_columns`).
- `GET/POST /api/conversations/{id}/notes`: tabla `conversation_notes`; respeta el guard de asesor; nunca se envía al cliente.
- `GET /api/quick-replies`: desde `tenants.json` (`quick_replies: [{key,title,lang,text}]`) o predeterminadas; variables `{nombre} {monto} {monto_recibir} {ruta}`.
- `GET /api/media`: `Cache-Control: private, max-age=3600`.
- `POST /api/ops/web-vitals` + `web_vitals` (p75 por métrica) en `GET /api/ops/metrics`.
- **SSE `GET /api/events`: pospuesto** (era opcional). `EventSource` no admite la cabecera `X-Auth-Token` (habría que poner el token en la URL) y en producción exige Redis pub/sub entre `api` y `worker`. El polling incremental de 3 s cumple el criterio de "≤ 3 s sin recargar".

## 9. Fases y entregables

| Fase | Entregable | Estado |
|---|---|---|
| **A. Identidad y rendimiento base** | Tokens Brasper claro/oscuro con toggle persistente, sin `backdrop-filter` ni neón, tipografías de marca activas, logo/isotipo/favicon, sidebar colapsable a rail de 72 px, barra inferior móvil, login nuevo, limpieza de archivos muertos | ✅ |
| **B. Bandeja v2** | Pestañas Entrada/Míos/Libres/Bot/Cerrados con conteo, búsqueda `Ctrl K`, ítem con avatar + nombre del lead + hora relativa + no leídos + SLA (5/15 min), virtualización, hilo con separadores de día, auto-scroll y botón "N nuevos", skeletons, compositor con textarea autoexpandible, envío optimista con reintento, toasts, bot vs asesor diferenciados, polling incremental `since`/`after` | ✅ |
| **C. Responsive + ficha** | 4 columnas ≥ 1440; ficha como drawer < 1440; rail < 1280; lista **o** hilo < 1024 con botón ←; barra inferior y `100dvh`/safe-area en móvil; ficha del cliente con operación (cotización, promo), identidad, atención, notas y eliminación con confirmación | ✅ |
| **D. Productividad del asesor** | Respuestas rápidas (⚡ o `/`, buscables, con variables), notas internas (pestaña del compositor + ficha + contador), asignar/liberar asesor con carga visible, atajos `T` `R` `E` `I` `↑↓` `Enter` `Esc`, arrastrar y pegar archivos, vista previa/validación/progreso de adjuntos, imagen por URL en menú, lightbox con descarga, caché de adjuntos (cliente y `Cache-Control`) | ✅ (SSE pospuesto, ver §8) |
| **E. Resto del panel + ops** | Chat de prueba con las mismas burbujas y botón "Nueva conversación"; Consumo con 4 stat tiles, gráfico de costo diario (SVG propio: una tonalidad, barras finas, tooltip, vista tabla) y paginación; página **Monitoreo** (`/ops`): salud API/DB/Redis, alertas, dead-letter, Core Web Vitals p75; Bot y prompt con cabecera y nota de error semántica; Plantillas con estados en chips; Lighthouse en CI (`web/lighthouserc.json`, performance ≥ 0.9, a11y ≥ 0.95) con reporte como artefacto; `WebVitals` reportando al backend | ✅ |

## 10. Criterios de aceptación

| Criterio | Estado |
|---|---|
| Un asesor identifica el panel como Brasper sin leer texto (logo + azul + detalle amarillo) | ✅ con paleta provisional; falta el SVG/hex oficial (§11) |
| Scroll de lista con 500 conversaciones y hilo con 1 000 mensajes fluido (sin `backdrop-filter`, virtualizado) | ✅ implementado; medido con 6 conversaciones en local, pendiente de medir con volumen real |
| Mensaje nuevo visible en ≤ 3 s sin recargar y sin saltar la posición de lectura | ✅ polling de 3 s con `after`, botón "N nuevos" si el asesor está leyendo arriba |
| Responder desde el móvil (375 px) sin zoom ni scroll horizontal | ✅ verificado en el navegador integrado (lista → hilo → ficha) |
| Contraste AA; teclado completo; `prefers-reduced-motion` | ✅ tokens `--muted` ≥ 4.5:1 sobre superficie; atajos y roles ARIA; media query de movimiento reducido |
| `npm run build` + `tsc` en verde; Lighthouse ≥ 90 / ≥ 95 | ✅ build y tsc en local; Lighthouse se evalúa en CI (el primer PR confirma los umbrales) |
| Cada endpoint nuevo con caso en `run_checks.py` | ✅ caso 46 (46/46 en verde) |

## 11. Preguntas abiertas para el equipo

1. **Pendiente:** hex oficial del azul Brasper, logo SVG y tipografía de marca. Mientras, paleta de §3 e isotipo provisional en `public/brand/`; se cambian en `globals.css` (`--brand*`) y `components/Logo.tsx`.
2. **Decidido:** tema claro por defecto si el sistema no pide oscuro; toggle persistente en el pie del menú y en la barra móvil.
3. **Decidido:** notas internas entregadas en Fase D. **Etiquetas** (`conversation_tags`) quedan en el Sprint 4 de [PLAN-MEJORAS-2026-10.md](PLAN-MEJORAS-2026-10.md), que ya las contempla.
4. **Decidido:** SLA = minutos desde `updated_at` en `handoff` (la última actividad del hilo); 5 min aviso (ámbar), 15 min alerta (rojo), visible en la lista.
