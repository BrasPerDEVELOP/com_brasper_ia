# Fase 0 — Unificar Brasper en `backend/` (CRITICAL)

**Estado:** 🔲 Pendiente  
**PR:** `feat/fase-0-brasper-backend`  
**Skill:** `brasper-fintech-ia`  
**Tiempo:** 3–7 días

## Problema

```
Docker → backend/main.py → LangGraph → connectors httpbin (demo)
Legacy → app/ → BrasperUseCase → apibras.finzeler.com (REAL)
```

El launch vende Brasper; prod Docker no usa el motor real.

## Objetivo

Cotizaciones, cupones y features remesa disponibles en el path **`backend/`** que Docker ejecuta.

---

## 0.1 — Inventario (1 día)

- [ ] Listar exports usados: `BrasperUseCase`, policies, features, tool_router legacy
- [ ] Mapear endpoints API Brasper (`apibras.finzeler.com`)
- [ ] Documentar en `FEATURE_MAP.md` (crear si no existe)

## 0.2 — Port / cableado

**Opción A (recomendada):** paquete importable

```
backend/core/brasper/
  use_case.py          # wrap o reexport BrasperUseCase
  policies.py
  features/
  tool_bridge.py       # registra tools en tool_router prod
```

**Opción B:** `PYTHONPATH` incluye `app/` y adapters delgados en `backend/core/`.

- [ ] Elegir A o B y documentar en `AGENTS.md`
- [ ] `agent_graph` / `tool_router` enruta `quote` / `coupon` a Brasper
- [ ] Quitar o desactivar connectors `httpbin` del tenant `brasper`

## 0.3 — `tenants.json` Brasper

- [ ] `externalApis` → base URL real + auth desde env (`BRASPER_API_*`)
- [ ] Tools: cotizar, cupón, (opcional) comisiones
- [ ] `system_prompt`: “no inventes tasas; usa tools”
- [ ] Secrets solo en `.env` / compose

## 0.4 — Verificación

- [ ] `POST /api/brasper/chat` con “cotiza 100 USD a BRL” → respuesta con montos de API
- [ ] Unittest legacy sigue verde
- [ ] `run_checks.py` verde
- [ ] Actualizar `00-ROADMAP.md` → Fase 0 ✅

## Criterio de aceptación

Un mensaje de cotización en el stack Docker **no** puede devolver un número que no venga de la API Brasper.

## Prompt

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md#fase-0).
