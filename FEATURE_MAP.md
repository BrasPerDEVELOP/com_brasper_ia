# FEATURE_MAP — Brasper Bot / Cauce

> Contrato: intención → path código → tool → API. Actualizar al portar `app/` → `backend/`.

## Dos stacks (hasta Fase 0)

| Stack | Entry | Orquestación | Cotización real |
|-------|-------|--------------|-----------------|
| **Prod Docker** | `backend/main.py` | `backend/core/agent_graph.py` | ⚠️ connectors demo httpbin |
| **Legacy** | `main.py` | `app/.../conversation_orchestador.py` | ✅ `BrasperUseCase` → apibras |

## Intenciones Brasper

| Intención | Legacy feature | Tool / API | Path prod (objetivo Fase 0) |
|-----------|----------------|------------|-----------------------------|
| Cotización | `remittance_quote_feature` | quote → apibras | `backend/core/brasper` + tool_router |
| Cupón | coupon feature | coupon API | idem |
| Info / requisitos | `remittance_requirements_feature` | ficha / RAG Fase 3 | search_knowledge |
| Handoff | keywords | WhatsApp link | `handoff` en tenants.json |
| Chat libre | LLM | DeepSeek | `llm.py` |

## Endpoints API plataforma

| Método | Path | Uso |
|--------|------|-----|
| POST | `/api/{tenant_id}/chat` | Webchat / panel test |
| POST | webhooks WhatsApp/Telegram | Canales |
| GET | `/health` | Liveness |
| GET | `/api/ops/metrics` | Ops |

## Tenant Brasper (`tenants.json`)

| Campo | Estado |
|-------|--------|
| `vertical: Remesas / Fintech` | ✅ |
| `system_prompt` | ⚠️ pide estimado referencial; debe forzar tools |
| `externalApis.erp_demo` | ❌ httpbin — reemplazar Fase 0 |
| `handoff` | ✅ keywords |

## Tests

| Suite | Path | Cubre |
|-------|------|-------|
| Platform | `backend/tests/run_checks.py` | Multi-tenant, webhooks, graph stub |
| Fintech | `tests/test_chat_architecture.py` | Anti-alucinación, quote, coupon |

## Plan

[docs/plans/00-ROADMAP.md](docs/plans/00-ROADMAP.md)
