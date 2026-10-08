# Roadmap Brasper Bot — Mejoras para launch

> Complementa `PLAN_PLATAFORMA.md` (plataforma Cauce).  
> Este plan prioriza el **producto Brasper fintech** que se está lanzando.  
> Skills: `brasper-ia-audit`, `brasper-fintech-ia` · Ver `AGENTS.md`.

> Plan detallado por sprints: [PLAN-MEJORAS-2026-10.md](./PLAN-MEJORAS-2026-10.md) · Plan UX/UI del panel: [PLAN-PANEL-UX-2026-10.md](./PLAN-PANEL-UX-2026-10.md) · Atención autónoma: [PLAN-ATENCION-AUTONOMA-2026-10.md](./PLAN-ATENCION-AUTONOMA-2026-10.md) (ejecutado en código; diagnóstico en [ATENCION-AUTONOMA-ETAPA-0.md](./ATENCION-AUTONOMA-ETAPA-0.md))

## Estado por fase

| Fase | Nombre | Estado | Doc | PR sugerido |
|------|--------|--------|-----|-------------|
| **0** | Unificar lógica Brasper en prod | ✅ Hecho | [FASE-0.md](./FASE-0.md) | `feat/fase-0-brasper-backend` |
| **1** | Vertical Remesas + anti-alucinación hard | 🟡 Parcial (cotizador/guards en `run_checks`) | [FASE-1.md](./FASE-1.md) | `feat/fase-1-remesas-policies` |
| **2** | CI + evals + smoke | 🟡 CI (`.github/workflows/ci.yml`) y smoke listos; evals golden pendientes | [FASE-2.md](./FASE-2.md) | `feat/fase-2-ci-evals` |
| **3** | Conocimiento (FAQ/RAG ligero) | 🔲 | [FASE-3.md](./FASE-3.md) | `feat/fase-3-knowledge` |
| **4** | Launch ops (disclaimers, legal, runbook) | 🔲 | [FASE-4.md](./FASE-4.md) | `feat/fase-4-launch-ops` |

## Orden (no saltar 0)

```
0 (CRITICAL) → 1 → 2 → 3 (opcional pre-launch) → 4
```

**Fase 0 cerrada:** el legacy `app/` fue eliminado; `backend/core/quotes.py` + `brasper_api.py` cotizan con la API real. Seguir con 1 y 2.

## Gate antes de cada PR

```bash
cd backend && ../.venv/bin/python tests/run_checks.py   # 45 casos, sin LLM real
cd backend && ../.venv/bin/python -m doctest core/policies.py
```

## Relación con PLAN_PLATAFORMA.md

| PLAN_PLATAFORMA | Este roadmap |
|-----------------|--------------|
| Fases 1–7 plataforma (casi cerradas) | Base Cauce OK |
| §11 “No RAG todavía” | Fase 3 = RAG **mínimo** solo FAQ Brasper, no marketplace |
| Prioridad inmediata §9 | Fase 0–1 son más urgentes para **lanzar Brasper** |

## Definition of Done — listo para lanzar Brasper

- [x] Tenant `brasper` usa API real (no httpbin)
- [x] Cotización / cupón vía tool, LLM no inventa montos
- [x] Tests anti-alucinación verdes en CI (`run_checks` caso 34)
- [x] Disclaimer referencial en quotes
- [x] Smoke post-deploy (`backend/tests/e2e_smoke.py`)
- [ ] `POLITICAS.md` revisado por legal (o disclaimer “plantilla” visible)

## Prompts Cursor

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md).
