# Fase 4 — Launch ops

**Estado:** 🔲 Pendiente  
**PR:** `feat/fase-4-launch-ops`

## Objetivo

Cerrar lo comercial/legal/ops para clientes reales Brasper.

---

## 4.1 — Legal / compliance

- [ ] Revisar `POLITICAS.md` con abogado (marcar fecha de revisión)
- [ ] Disclaimers en canal WhatsApp (primera cotización)
- [ ] Retención de conversaciones alineada a política

## 4.2 — Onboarding Brasper

- [ ] Checklist en `ONBOARDING.md` específica Remesas
- [ ] Variables env obligatorias (`BRASPER_API_*`, WhatsApp, LLM)
- [ ] Tenant pause/activate desde panel verificado

## 4.3 — Observabilidad

- [ ] Alertas: error rate quote API, costo LLM > umbral
- [ ] Dashboard: conversaciones Brasper / día (panel o Grafana)
- [ ] Runbook incidente: API Brasper caída → mensaje fallback + handoff

## 4.4 — Hardening final

- [ ] CORS dominio real panel
- [ ] Sin tokens demo
- [ ] Webhooks con firma
- [ ] Backup/restore probado (ya en plataforma — re-verificar)

## Criterio de aceptación

Checklist §10 de `PLAN_PLATAFORMA.md` + DoD de `00-ROADMAP.md` en verde.

## Prompt

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md#fase-4).
