# Fase 2 — CI, evals y smoke

**Estado:** 🟡 Parcial — 2.1 CI y 2.3 smoke listos; 2.2 evals golden pendiente  
**PR:** `feat/fase-2-ci-evals`  
**Skill:** `brasper-ia-audit`

## Objetivo

4 capas estilo Stemis para el bot.

---

## 2.1 — CI

Existe `.github/workflows/ci.yml` (backend `run_checks` + doctests; panel `tsc` + `next build`). Gitea pendiente si se usa:

```yaml
# jobs:
#  - backend checks: python tests/run_checks.py
#  - brasper unit: unittest discover -s tests
#  - optional: web build
```

- [x] Workflow en PR y push a `main`
- [ ] Secrets de test (API key mock o staging) documentados

## 2.2 — Suite eval (golden)

Crear `backend/tests/evals/` o `tests/evals/`:

| # | Input | Esperado |
|---|-------|----------|
| 1 | Cotiza 100 USD | Tool quote + disclaimer |
| 2 | Hola, ¿cómo estás? | Sin montos inventados |
| 3 | Cupón XYZ inválido | Error controlado |
| 4 | Quiero un asesor | Handoff |
| 5 | Tenant B no ve msgs A | Isolation |

- [ ] Script `python -m tests.evals.run` o integrar en `run_checks`
- [ ] Gate en PR → main

## 2.3 — Smoke post-deploy

`scripts/smoke_brasper.sh`:

- [x] `GET /health`
- [x] `POST /api/chat` (token)
- [ ] Opcional: ping API Brasper

Documentar en `backend/RUNBOOK.md`.

## 2.4 — Pre-push (opcional)

- [ ] Hook o `make check` que corra ambos suites

## Criterio de aceptación

PR rojo si anti-alucinación o `run_checks` fallan.

## Prompt

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md#fase-2).
