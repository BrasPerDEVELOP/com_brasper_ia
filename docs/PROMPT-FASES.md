# Prompts por fase — Brasper IA

Repo: `com_brasper_ia`. Skills: `brasper-ia-audit`, `brasper-fintech-ia`.

---

## Fase 0

```
Fase 0 — Unificar Brasper en backend/
Lee docs/plans/FASE-0.md, FEATURE_MAP.md, AGENTS.md.
Skill: brasper-fintech-ia.

1. Inventariar BrasperUseCase + policies + features en app/
2. Cablear en backend/core/brasper/ (o import app/)
3. tenants.json brasper: quitar httpbin; connectors API real vía env
4. agent_graph/tool_router: quote y coupon → API Brasper
5. Verificar POST /api/brasper/chat cotiza con montos reales
6. run_checks + unittest verdes

Sin rediseñar panel. Actualiza docs/plans/00-ROADMAP.md al terminar.
```

---

## Fase 1

```
Fase 1 — Vertical Remesas + anti-alucinación
Lee docs/plans/FASE-1.md. Skill: brasper-fintech-ia.

Portar RemittancePolicyEngine al path Docker.
should_skip_llm para quote/coupon; strip slots inventados.
Disclaimer referencial multi-idioma.
Tests anti-alucinación contra agent_graph prod.
```

---

## Fase 2

```
Fase 2 — CI + evals + smoke
Lee docs/plans/FASE-2.md. Skill: brasper-ia-audit.

Crear .github/workflows/ci.yml y .gitea/workflows/ci.yml
(run_checks + unittest). Suite evals golden 5 casos.
scripts/smoke_brasper.sh + nota en RUNBOOK.md.
```

---

## Fase 3

```
Fase 3 — Knowledge FAQ / RAG ligero
Lee docs/plans/FASE-3.md. Skill: brasper-fintech-ia.

Corpus Markdown brasper; tool search_knowledge; citations.
Empezar sin pgvector si basta keyword retrieval.
No marketplace RAG.
```

---

## Fase 4

```
Fase 4 — Launch ops
Lee docs/plans/FASE-4.md.

Legal POLITICAS, onboarding Remesas, alertas quote API,
CORS real, runbook API caída → handoff.
```

---

## Auditoría

```
Skill brasper-ia-audit.
Genera docs/audits/AUDITORIA-IA-YYYY-MM-DD.md.
Compara con docs/plans/00-ROADMAP.md. Sin implementar.
```
