# Fase 3 — Conocimiento (FAQ / RAG ligero)

**Estado:** 🔲 Pendiente  
**PR:** `feat/fase-3-knowledge`  
**Nota:** `PLAN_PLATAFORMA` §11 dice “no RAG por defecto”. Esta fase es **RAG mínimo solo Brasper**, no marketplace.

## Objetivo

Reemplazar ficha hardcodeada (`remittance_requirements_feature`) por docs versionados + citations.

---

## 3.1 — Corpus v1 (sin vector DB si hace falta)

Empezar simple:

- [ ] Markdown/JSON por tenant: `backend/data/knowledge/brasper/*.md`
- [ ] Retrieval por keywords / secciones (BM25 o simple) **antes** de embeddings
- [ ] Tool `search_knowledge(query)` obligatoria para intent `info`

## 3.2 — Citations

- [ ] Respuesta incluye fuente: `doc + sección`
- [ ] Si no hay chunk → “no tengo esa info, te paso con asesor”

## 3.3 — Embeddings (opcional, después)

- [ ] pgvector en Postgres (mismo patrón Stemis normativa)
- [ ] `tenant_id` en metadata siempre
- [ ] Index HNSW solo si el corpus crece

## 3.4 — Panel

- [ ] UI mínima: subir/editar FAQ por tenant (o solo ops via API)
- [ ] Resumen del panel: no marcar RAG “listo” hasta citations en prod

## Criterio de aceptación

Pregunta de requisitos → respuesta con citation; sin citation no afirma requisitos inventados.

## Prompt

Ver [docs/PROMPT-FASES.md](../PROMPT-FASES.md#fase-3).
