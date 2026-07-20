# AGENTS.md — com_brasper_ia (Cauce / Brasper Bot)

Plataforma IA multi-tenant para bots (WhatsApp, Telegram, webchat). Stack: **FastAPI + LangGraph + Postgres + Redis** (`backend/`) + panel **Next.js** (`web/`). Lógica fintech Brasper (cotizaciones, anti-alucinación) vive hoy en legacy `app/` — **prioridad: unificar en `backend/`**.

## Skills (`.agents/skills/` y `.cursor/skills/`)

| Skill | Cuándo usar |
|-------|-------------|
| **brasper-ia-audit** | Auditoría pre-launch, dual stack, CI, tenant isolation, "limpiar / auditar bot" |
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
3. Implementar en backend/    → NUNCA solo en app/ si es prod Docker
4. brasper-ia-audit           → pre-merge / pre-launch
5. thermo-nuclear             → review de graph/orchestrator
```

## Capas de validación (estilo Stemis)

| Capa | Comando / artefacto |
|------|---------------------|
| 1 Local | `cd backend && python tests/run_checks.py` + `python -m unittest discover -s tests` (raíz) |
| 2 CI PR | Workflow Gitea/GitHub (pendiente) — ambos suites |
| 3 Gate | Evals: quote API, anti-hallucination, handoff |
| 4 Deploy | Smoke: chat tenant + webhook + cotización real |

Ver `backend/DEPLOY.md`, `backend/RUNBOOK.md`, `PLAN_PLATAFORMA.md`.

## Arquitectura crítica (no romper)

```
Docker prod → backend/main.py → LangGraph (agent_graph) → tools / LLM
Legacy      → main.py + app/  → BrasperUseCase + RemittancePolicyEngine
```

**Regla de launch:** cotizaciones, cupones y montos **solo** vía tool/API (`BrasperUseCase` / connectors reales). El LLM **no inventa tasas**.

**Regla de stack:** cambios de producto Brasper van a `backend/core/` (o librería importada desde `app/`). No dejar lógica crítica solo en `app/` si Docker no la ejecuta.

## Capas del bot

| Capa | Dónde |
|------|-------|
| Canales | `backend/core/whatsapp.py`, `telegram.py`, webhooks en `api/routes.py` |
| Orquestación | `backend/core/agent_graph.py` |
| LLM | `backend/core/llm.py` (DeepSeek / OpenAI-compatible) |
| Tools | `backend/core/tool_router.py` + connectors tenant |
| Fintech (legacy) | `app/application/brasper_use_case.py`, `policies/`, `features/` |
| Tenants | `backend/config/tenants.json` + Admin API |
| Panel | `web/` (Next.js) |

## Convenciones

- Español en respuestas del bot y docs de producto
- Inglés en código (nombres de módulos/funciones)
- Secrets solo en env / Dokploy — nunca en `tenants.json` commiteado
- Cada tool fintech: test de anti-alucinación (ver `tests/test_chat_architecture.py`)
- Tenant isolation: conversaciones, usage y docs RAG siempre con `tenant_id`

## Invocación en Cursor

- *"Usa brasper-ia-audit y genera el reporte de launch"*
- *"Usa brasper-fintech-ia para portar BrasperUseCase a backend/"*
- *"thermo-nuclear en agent_graph.py"*
- *"brainstorming: RAG FAQ por tenant"*

## Roadmap de mejoras (launch Brasper)

| Fase | Estado | Doc |
|------|--------|-----|
| **0** Unificar Brasper en `backend/` | 🔲 **EMPEZAR** | [docs/plans/FASE-0.md](docs/plans/FASE-0.md) |
| **1** Vertical Remesas + anti-alucinación | 🔲 | [docs/plans/FASE-1.md](docs/plans/FASE-1.md) |
| **2** CI + evals + smoke | 🔲 | [docs/plans/FASE-2.md](docs/plans/FASE-2.md) |
| **3** FAQ / RAG ligero | 🔲 | [docs/plans/FASE-3.md](docs/plans/FASE-3.md) |
| **4** Launch ops | 🔲 | [docs/plans/FASE-4.md](docs/plans/FASE-4.md) |

Índice: [docs/plans/00-ROADMAP.md](docs/plans/00-ROADMAP.md)  
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
