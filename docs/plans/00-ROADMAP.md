# Roadmap Brasper Bot — Mejoras para launch

> Complementa `PLAN_PLATAFORMA.md` (plataforma Cauce).  
> Este plan prioriza el **producto Brasper fintech** que se está lanzando.  
> Skills: `brasper-ia-audit`, `brasper-fintech-ia` · Ver `AGENTS.md`.

## Estado por fase

| Fase | Nombre | Estado | Doc | PR sugerido |
|------|--------|--------|-----|-------------|
| **0** | Unificar lógica Brasper en prod | 🔲 **EMPEZAR AQUÍ** | [FASE-0.md](./FASE-0.md) | `feat/fase-0-brasper-backend` |
| **1** | Vertical Remesas + anti-alucinación hard | 🔲 | [FASE-1.md](./FASE-1.md) | `feat/fase-1-remesas-policies` |
| **2** | CI + evals + smoke | 🔲 | [FASE-2.md](./FASE-2.md) | `feat/fase-2-ci-evals` |
| **3** | Conocimiento (FAQ/RAG ligero) | 🔲 | [FASE-3.md](./FASE-3.md) | `feat/fase-3-knowledge` |
| **4** | Launch ops (disclaimers, legal, runbook) | 🔲 | [FASE-4.md](./FASE-4.md) | `feat/fase-4-launch-ops` |

## Orden (no saltar 0)

```
0 (CRITICAL) → 1 → 2 → 3 (opcional pre-launch) → 4
```

**Por qué 0 primero:** Docker corre `backend/`; cotizaciones reales están en `app/`. Sin Fase 0 el bot en prod **no es el Brasper real**.

## Gate antes de cada PR

```bash
cd backend && python tests/run_checks.py
cd .. && python -m unittest discover -s tests -v
```

## Relación con PLAN_PLATAFORMA.md

| PLAN_PLATAFORMA | Este roadmap |
|-----------------|--------------|
| Fases 1–7 plataforma (casi cerradas) | Base Cauce OK |
| §11 “No RAG todavía” | Fase 3 = RAG **mínimo** solo FAQ Brasper, no marketplace |
| Prioridad inmediata §9 | Fase 0–1 son más urgentes para **lanzar Brasper** |

## Definition of Done — listo para lanzar Brasper

- [ ] Tenant `brasper` usa API real (no httpbin)
- [ ] Cotización / cupón vía tool, LLM no inventa montos
- [ ] Tests anti-alucinación verdes en CI
- [ ] Disclaimer referencial en quotes
- [ ] Smoke post-deploy documentado
- [ ] `POLITICAS.md` revisado por legal (o disclaimer “plantilla” visible)

## Prompts Cursor

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md).
