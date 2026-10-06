# Plan de mejoras — Brasper Bot (octubre 2026)

> Punto de partida: rama `chore/gate-single-tenant-ci`. Fase 0 cerrada, `run_checks.py` con 45 casos en verde, CI en GitHub Actions, panel compilando. Este plan ordena lo que falta para lanzar y operar Brasper con confianza, en sprints de una semana.
>
> Regla de cada entrega: **toda regla de negocio nueva lleva su caso en `backend/tests/run_checks.py`** (sin LLM real, sin red). Un PR sin caso no cierra la tarea.

## Diagnóstico (lo que se encontró al revisar el repo)

| Área | Estado real | Riesgo |
|------|-------------|--------|
| Cotizador | Determinista, API Brasper exclusiva, sin fallback local | Bajo |
| Chat libre (LLM) | El prompt prohíbe inventar tasas, pero **no hay post-check**: si el modelo escribe un número, llega al cliente | **Alto** (anti-alucinación incompleta) |
| Preguntas de información (“qué documentos necesito”) | Van al LLM **sin conocimiento propio**: responde con lo que “sabe” del mundo | **Alto** (requisitos inventados) |
| Alertas | Solo DB/Redis/dead-letter/costo. Un fallo del LLM o de la API Brasper no alerta a nadie | Medio |
| Panel | Bandeja básica. Sin filtros, etiquetas ni respuestas rápidas; quedan restos multi-tenant (`TenantSelect`) | Medio (operación manual lenta) |
| Legal | `POLITICAS.md` es plantilla sin revisión | Medio |
| Deuda técnica | `db.py` con firmas de compatibilidad `*args`, `routes.py` de ~1000 líneas, `tenant_id` sin uso en rutas, variables de clínica en `.env.example` | Bajo, pero frena |

---

## Sprint 1 — Anti-alucinación dura (cierra Fase 1)

**Objetivo:** que ninguna respuesta del LLM contenga una tasa, monto o promesa que no venga de una tool.

- [ ] **Post-check numérico en `persist_llm`**: si la respuesta del LLM trae un patrón de tasa/monto con moneda (`1.46`, `710 BRL`, `S/ 500`) y el turno NO pasó por `handle_quote`, se reemplaza por una invitación a cotizar (“escribe *Cotizar 500 PEN a BRL*”) y se registra `observability.event("llm.numeric_leak")`.
- [ ] **Lista negra de promesas**: “tasa garantizada”, “sin comisión”, “llega en X minutos” → misma sanitización. Configurable en `tenants.json` (`guards.forbidden_claims`).
- [ ] **Idiomas permitidos** (`languages` del tenant): si `detect_language` devuelve uno fuera de la lista, se responde en español con aviso.
- [ ] **Disclaimer configurable**: `quote.disclaimer` por idioma en lugar del texto fijo de `quotes._COPY`.
- [ ] Casos nuevos en `run_checks`: (a) LLM stub que devuelve “la tasa es 1.52” → la salida no contiene el número; (b) stub con “tasa garantizada” → se sanea; (c) mensaje en francés → aviso de idioma.

**Criterio de aceptación:** checklist B de `brasper-ia-audit` en verde; `FASE-1.md` marcado ✅.

## Sprint 2 — Conocimiento Brasper (Fase 3, versión mínima)

**Objetivo:** las preguntas de información se responden desde un corpus versionado, con fuente, o se derivan.

- [ ] Corpus en `backend/data/knowledge/brasper/*.md`: requisitos por tipo de cliente, documentos, tiempos de acreditación, métodos de pago (Yape, Pix, transferencia), horarios, límites, preguntas frecuentes del equipo comercial.
- [ ] `core/knowledge.py`: retrieval por palabras clave y secciones (sin vector DB). Tool `search_knowledge(query)` que devuelve chunks + `source`.
- [ ] Nueva ruta en el grafo: intent `info` (detector por keywords: documentos, requisitos, cuánto demora, cómo pago, horario) → `handle_info` → chunks al LLM con instrucción “responde SOLO con esto y cita la sección”; sin chunks → “no tengo esa información, te paso con un asesor” + handoff.
- [ ] Panel: pestaña “Conocimiento” de solo lectura al inicio (lista de docs y última edición). Edición vía repo/PR.
- [ ] Casos `run_checks`: pregunta con chunk → respuesta cita `source`; pregunta sin chunk → handoff, sin afirmación de requisitos.

**Criterio de aceptación:** “¿qué documentos necesito?” responde con cita; una pregunta fuera del corpus nunca inventa.

## Sprint 3 — Operación y alertas (Fase 4, parte técnica)

**Objetivo:** enterarse de un problema antes que el cliente.

- [ ] `alerts.py`: nuevas alertas desde los eventos ya emitidos: `llm.failed` ≥ N en 10 min, `brasper_api.error` ≥ N en 10 min, `quote.clarify` disparado (posible regresión del extractor), `conversation.handoff` con `reason=llm_error`.
- [ ] Worker: `dispatch_external` a `ALERT_WEBHOOK_URL` (Slack/Mattermost) con cooldown ya existente; documentar en `RUNBOOK.md` el incidente “API Brasper caída” (mensaje que ve el cliente, qué revisar, cómo reactivar).
- [ ] Evals golden (Fase 2.2): `backend/tests/evals/golden.json` con 10 conversaciones reales anonimizadas (cotizar, seguir, continuar, documentos, asesor, portugués). Script `tests/evals/run.py` que las corre contra el grafo con LLM stub y compara ruta + ausencia de números inventados. Se integra en CI.
- [ ] Smoke post-deploy en Dokploy: `e2e_smoke.py --skip-llm` como paso del deploy; `--base` apuntando al dominio real.
- [ ] Dependabot para `requirements.txt` y `web/package.json` (solo PRs semanales, sin auto-merge).

**Criterio de aceptación:** una caída simulada de la API Brasper genera alerta externa y el runbook describe la respuesta.

## Sprint 4 — Panel de operación (benchmark Umbler Talk)

**Objetivo:** que un asesor atienda la bandeja sin ir a la base de datos. Funciones tomadas del benchmark de Umbler Talk que sí aplican al negocio Brasper.

- [ ] **Filtros de bandeja**: por estado (`active`/`handoff`/`closed`), canal, asignado a mí / libres, con lead `commercial_stage` (cotizado, esperando depósito, comprobante recibido). Backend: query params en `GET /api/conversations`.
- [ ] **Etiquetas**: tabla `conversation_tags` + endpoint; chips en la bandeja (ej. “primer envío”, “monto alto”, “reclamo”).
- [ ] **Respuestas rápidas** del asesor: lista en `tenants.json` (`quick_replies`) con variables `{nombre}`, `{monto}`; botón en el chat del panel.
- [ ] **Cola y SLA**: columna “esperando desde” en conversaciones en handoff sin respuesta del asesor; alerta si supera X minutos.
- [ ] **Tarjeta del lead** junto al chat: datos estructurados (`lead_data`), última cotización, cuentas mostradas, enlace al perfil Brasper.
- [ ] Limpieza: eliminar `TenantSelect.tsx` y textos “multi-tenant” del panel; `GET /api/tenants` pasa a `GET /api/account` o se mantiene con un solo elemento documentado.
- [ ] Casos `run_checks` para filtros/etiquetas/quick replies (HTTP con TestClient).

**Criterio de aceptación:** un asesor nuevo atiende una conversación de principio a fin solo desde el panel.

## Sprint 5 — Deuda técnica y hardening

**Objetivo:** bajar el costo de cambiar el código antes de que crezca el equipo.

- [ ] `db.py`: eliminar las firmas `*args` de compatibilidad (quedan tras la migración single-tenant); firmas explícitas y tipadas. `run_checks` ya usa las nuevas.
- [ ] `routes.py`: dividir en `api/chat.py`, `api/webhooks.py`, `api/conversations.py`, `api/admin.py`, `api/ops.py` (mismo router, sin cambio de contrato). Quitar `tenant = T.get_config(); tenant_id = ...` sin uso.
- [ ] `.env.example`: quitar `WA_*_CLINICA` / `TELEGRAM_*_CLINICA`; `tenants.json`: quitar plantilla `recordatorio_cita` (es de clínicas).
- [ ] Postgres en CI: job adicional con `services: postgres` que corre `manage.py migrate` + un subconjunto de `run_checks` (hoy el gate solo prueba SQLite).
- [ ] `thermo-nuclear-code-quality-review` sobre `agent_graph.py` tras añadir las rutas `info` y post-check.
- [ ] Legal: fecha de revisión en `POLITICAS.md` y disclaimer visible “plantilla” hasta la revisión del abogado; política de retención (`RETENTION_DAYS`) alineada al texto.

---

## Orden y dependencias

```
Sprint 1 (anti-alucinación) ──► Sprint 2 (conocimiento) ──► Sprint 3 (alertas + evals)
                                                      └───► Sprint 4 (panel) ──► Sprint 5 (deuda)
```

Sprints 1 y 2 son bloqueantes para el launch comercial: sin ellos el bot puede afirmar cosas que Brasper no respalda. Sprints 3 a 5 mejoran operación y mantenimiento y pueden solaparse con el piloto.

## Definition of Done del plan

- [ ] `run_checks` ≥ 60 casos en verde, CI obligatoria para mezclar a `main`
- [ ] Ningún número en respuestas del LLM sin pasar por tool (evals golden en verde)
- [ ] Preguntas de requisitos con cita de fuente
- [ ] Alertas externas para LLM y API Brasper
- [ ] Panel con filtros, etiquetas y respuestas rápidas
- [ ] `POLITICAS.md` con fecha de revisión legal
