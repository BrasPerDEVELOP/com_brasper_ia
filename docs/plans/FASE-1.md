# Fase 1 — Vertical Remesas + anti-alucinación hard

**Estado:** 🔲 Pendiente (después de Fase 0)  
**PR:** `feat/fase-1-remesas-policies`  
**Skill:** `brasper-fintech-ia`

## Objetivo

Reglas hard para vertical “Remesas / Fintech” (hoy `_vertical_errors` casi no valida fintech).

---

## 1.1 — Policy en path prod

- [ ] Portar / adaptar `RemittancePolicyEngine` a `backend/core/brasper/policies.py`
- [ ] Intent determinístico: quote, coupon, info, handoff
- [ ] `should_skip_llm` (o equivalente) para quote/coupon
- [ ] Strip de slots inventados si no hay señal de quote (como legacy)

## 1.2 — Validaciones vertical

En `backend/core/tenants.py` o módulo brasper:

- [ ] Montos solo desde tool result
- [ ] Idiomas permitidos del tenant
- [ ] Handoff por keywords + umbral de monto (configurable)
- [ ] Rechazar promesas de “tasa garantizada” en prompt + post-check

## 1.3 — Disclaimer

- [ ] Toda cotización incluye texto referencial (es/pt/en según idioma detectado)
- [ ] Configurable en tenant config

## 1.4 — Tests

- [ ] Portar casos de `tests/test_chat_architecture.py` al graph `backend/`
- [ ] Caso: sin señal de quote → no tasa en respuesta
- [ ] Caso: cupón inválido → error API, no inventado

## Criterio de aceptación

`brasper-ia-audit` checklist B (fintech) en verde para path Docker.

## Prompt

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md#fase-1).
