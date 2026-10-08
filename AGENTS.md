# AGENTS.md — com_brasper_ia (Cauce / Brasper Bot)

Bot IA de Brasper (remesas Perú↔Brasil) para WhatsApp, Telegram y webchat, con panel de operación. Stack: **FastAPI + LangGraph + Postgres + Redis** (`backend/`) + panel **Next.js** (`web/`).

**Estado del stack:** el repo es **single-tenant Brasper** y toda la lógica fintech (cotizador, API Brasper en vivo, onboarding, handoff) vive en `backend/core/`. El legacy `app/` ya no existe (Fase 0 completada). Si un doc viejo menciona `app/`, `BrasperUseCase` o `clinica_demo`, está desactualizado.

## Skills (`.agents/skills/` y `.cursor/skills/`)

| Skill | Cuándo usar |
|-------|-------------|
| **brasper-ia-audit** | Auditoría pre-launch, CI, "limpiar / auditar bot" |
| **brasper-fintech-ia** | Cotizaciones, tools obligatorias, anti-alucinación, RAG/FAQ, citations fintech |
| **brainstorming** | Antes de features nuevas (canal, vertical, tool, RAG) |
| **thermo-nuclear-code-quality-review** | God files en orchestrators, spaghetti en policies/graph |

### NO copiar de Stemis (otro dominio)

- `shadcn-ui`, `next-best-practices` (salvo panel `web/` con cuidado)
- `nestjs-best-practices`, `prisma-expert`
- `stemis-normativa-ia` tal cual (SPIJ legal) — usar **brasper-fintech-ia**
- `interface-design`, `ui-ux-pro-max` — no para el bot; solo si rediseñas panel

## Flujo recomendado

```
1. brainstorming              → feature nueva
2. brasper-fintech-ia         → tools, policies, RAG, citations
3. Implementar en backend/core/ + caso nuevo en backend/tests/run_checks.py
4. brasper-ia-audit           → pre-merge / pre-launch
5. thermo-nuclear             → review de graph/orchestrator
```

## Capas de validación

| Capa | Comando / artefacto |
|------|---------------------|
| 1 Local | `cd backend && ../.venv/bin/python tests/run_checks.py` (Windows: `..\.venv\Scripts\python.exe tests\run_checks.py`) + `python -m doctest core/policies.py` + evals `python tests/evals/run.py` (54 escenarios ES/PT, sin LLM real) |
| 2 CI PR | `.github/workflows/ci.yml` — backend `run_checks` + doctests + evals, panel `tsc` + `next build` + Lighthouse (`web/lighthouserc.json`: performance ≥ 90, a11y ≥ 95) |
| 3 Gate | Casos del propio `run_checks`: cotizador sin LLM, anti-alucinación (API exclusiva), handoff, onboarding |
| 4 Deploy | `backend/tests/e2e_smoke.py` contra el servidor vivo: health + login + cotización + handoff |

Entorno local: Python 3.12 en `.venv/` (raíz del repo), deps en `requirements.txt` (raíz). El panel usa `npm ci` en `web/`.

Ver `backend/DEPLOY.md`, `backend/RUNBOOK.md`, `PLAN_PLATAFORMA.md`.

## Arquitectura crítica (no romper)

```
Canal (WhatsApp/Telegram/webchat) → api/routes.py → core/engine.py (lock Redis)
  → core/agent_graph.py (LangGraph)
      ├─ quotes.py (determinista, SIN LLM) → brasper_api.py (TC/comisiones/cupones en vivo)
      ├─ lead_onboarding.py (identidad progresiva, clientes Brasper, cuentas de depósito)
      ├─ handoff → auth.derive_to_advisor (asesor con menos carga)
      ├─ knowledge.py (FAQ aprobada con fuente, sin LLM) · handle_status (estado de envío → asesor con resumen)
      ├─ tool_router.py → connectors.py (externalApis declarativas) · tool_contracts.py (contratos tipados, timeout, idempotencia)
      ├─ handoff_summary.py (resumen de derivación) · presence.py (presencia de asesores) · idempotency.py (dedup de webhooks)
      ├─ audio_flow.py + audio_review.py (audios: evidencia, cifras ambiguas → confirmación)
      └─ llm.py (DeepSeek / OpenAI-compatible) solo para conversación libre (con anti-bucle)
```

**Regla de conocimiento:** preguntas informativas se responden **solo** con entradas `approved` de `backend/data/knowledge/brasper/faq.json`, citando fuente y fecha; sin entrada aprobada el bot declara incertidumbre y ofrece asesor. Las entradas `draft` nunca se sirven.

**Flags** (`tenants.json → features`, ver `core/features.py`): `knowledge`, `status_intent`, `anti_loop`, `audio_confirmation`, `webhook_dedup`, `presence_required`, `coex`. Permiten activar/revertir cada capacidad sin redesplegar.

**WhatsApp:** `whatsapp.connections` admite varios números (API estándar o `coex`); cada conversación guarda `connection_id` y las respuestas salen por el número de origen. Los ecos de la app del celular (`smb_message_echoes`) son actividad humana: pausan el bot y nunca generan respuesta.

**Regla de launch:** cotizaciones, cupones, montos y cuentas **solo** vía `quotes.py` / `brasper_api.py`. El LLM **no inventa tasas**. Si la API Brasper falla, el cotizador rechaza la cotización (nunca usa una tasa local como respaldo).

**Regla de canal:** el asesor atiende dentro del mismo chat (takeover). El bot **nunca** deriva a WhatsApp externo ni redes; `agent_graph.sanitize_no_external_channels` lo garantiza a la entrada y salida del LLM.

**Regla de config:** `backend/config/tenants.json` solo guarda referencias `*_env`; los secretos van en `.env` / Dokploy. La Admin API rechaza secretos crudos en producción.

## Capas del bot

| Capa | Dónde |
|------|-------|
| Canales | `backend/core/whatsapp.py`, `telegram.py`, webhooks en `api/routes.py` |
| Orquestación | `backend/core/agent_graph.py` (+ `engine.py` lock por conversación) |
| LLM | `backend/core/llm.py` |
| Cotizador | `backend/core/quotes.py` + `brasper_api.py` + `policies.py` (primitivas puras) |
| Onboarding / clientes | `backend/core/lead_onboarding.py` |
| Tools genéricas | `backend/core/tool_router.py` + `connectors.py` |
| Config | `backend/config/tenants.json` (`tenants.brasper`) + Admin API |
| Panel | `web/` (Next.js). Bandeja en `web/components/inbox/*`; tokens de marca en `web/app/globals.css`; plan UX en `docs/plans/PLAN-PANEL-UX-2026-10.md` |

## Convenciones

- Español en respuestas del bot y docs de producto; inglés en código
- Secrets solo en env / Dokploy — nunca en `tenants.json` commiteado
- Cada regla fintech nueva lleva un caso en `backend/tests/run_checks.py` (sin LLM real, sin red)
- Flujos del grafo deterministas (cotización, handoff, onboarding) devuelven `usage: None`: no gastan LLM

## Invocación en Cursor

- *"Usa brasper-ia-audit y genera el reporte de launch"*
- *"Usa brasper-fintech-ia para añadir la tool X en backend/core/"*
- *"thermo-nuclear en agent_graph.py"*
- *"brainstorming: RAG FAQ Brasper"*

## Roadmap de mejoras (launch Brasper)

| Fase | Estado | Doc |
|------|--------|-----|
| **0** Unificar Brasper en `backend/` | ✅ Hecho | [docs/plans/FASE-0.md](docs/plans/FASE-0.md) |
| **1** Vertical Remesas + anti-alucinación | 🟡 Parcial (en `quotes.py` / `run_checks`) | [docs/plans/FASE-1.md](docs/plans/FASE-1.md) |
| **2** CI + evals + smoke | 🟢 CI, smoke y evals de escenarios (`tests/evals`) en CI | [docs/plans/FASE-2.md](docs/plans/FASE-2.md) |
| **3** FAQ / RAG ligero | 🟡 FAQ con fuente en `core/knowledge.py` (13 aprobadas, 3 borradores comerciales) | [docs/plans/FASE-3.md](docs/plans/FASE-3.md) |
| **4** Launch ops | 🔲 | [docs/plans/FASE-4.md](docs/plans/FASE-4.md) |

Índice: [docs/plans/00-ROADMAP.md](docs/plans/00-ROADMAP.md) · Plan de mejoras: [docs/plans/PLAN-MEJORAS-2026-10.md](docs/plans/PLAN-MEJORAS-2026-10.md) · Plan UX panel: [docs/plans/PLAN-PANEL-UX-2026-10.md](docs/plans/PLAN-PANEL-UX-2026-10.md) · Atención autónoma: [docs/plans/PLAN-ATENCION-AUTONOMA-2026-10.md](docs/plans/PLAN-ATENCION-AUTONOMA-2026-10.md) (diagnóstico: [docs/plans/ATENCION-AUTONOMA-ETAPA-0.md](docs/plans/ATENCION-AUTONOMA-ETAPA-0.md))  
Mapa: [FEATURE_MAP.md](FEATURE_MAP.md)  
Prompts: [docs/PROMPT-FASES.md](docs/PROMPT-FASES.md)

## Docs clave

| Doc | Uso |
|-----|-----|
| `README.md` | Stack y estado honesto |
| `PLAN_PLATAFORMA.md` | Roadmap plataforma Cauce (Fases 1–7) |
| `POLITICAS.md` | Plantilla legal (revisar con abogado) |
| `VERTICALES.md` | Contratos de vertical |
| `backend/DEPLOY.md` / `RUNBOOK.md` | Ops |
| `ONBOARDING.md` | Alta de clientes |
