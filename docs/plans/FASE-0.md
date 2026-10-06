# Fase 0 — Unificar Brasper en `backend/` (CRITICAL)

**Estado:** ✅ Completada (el legacy `app/` fue eliminado; el repo es single-tenant Brasper)  
**Skill:** `brasper-fintech-ia`

## Problema original

```
Docker → backend/main.py → LangGraph → connectors httpbin (demo)
Legacy → app/ → BrasperUseCase → apibras.finzeler.com (REAL)
```

El launch vendía Brasper pero prod Docker no usaba el motor real.

## Resultado

Cotizaciones, cupones, clientes y cuentas de depósito viven en el path **`backend/`** que Docker ejecuta:

| Pieza legacy | Ahora |
|--------------|-------|
| `BrasperUseCase` (matemática de cotización) | `backend/core/quotes.py` (portado 1:1: comisión por rangos, cupón sobre comisión, modo recibir) |
| Conector apibras | `backend/core/brasper_api.py` (TC/comisiones/cupones públicos + endpoints IA privados con `X-Brasper-IA-Secret`) |
| `RemittancePolicyEngine` (primitivas) | `backend/core/policies.py` (puro, con doctests) |
| Orquestador | `backend/core/agent_graph.py` (LangGraph): cotización/handoff/onboarding deterministas, LLM solo para chat libre |
| Multi-tenant JSON + `clinica_demo` | Single-tenant `tenants.brasper` (migración Alembic `0007_remove_multitenant`, `0008_brasper_modeling`) |

### Checklist cerrado

- [x] Cotizador en el grafo sin LLM (`handle_quote`), API Brasper exclusiva, sin fallback local
- [x] Connectors `httpbin` eliminados del tenant (`externalApis: {}`)
- [x] `tenants.json`: `quote.api` real, secretos solo por `*_env`, prompt "no inventes tasas"
- [x] `run_checks.py` reescrito para single-tenant (45 casos, verde)
- [x] Criterio de aceptación: un mensaje de cotización en Docker **no** puede devolver un número que no venga de la API Brasper (caso 34)

## Siguiente

[FASE-1.md](./FASE-1.md) (reglas duras restantes) y [FASE-2.md](./FASE-2.md) (evals golden; CI ya existe).
