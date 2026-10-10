# Inventario de cambios en la API financiera (`com_brasper_api`) — 10 de octubre de 2026

Requisito del [plan de campañas y usuarios](PLAN-CAMPANAS-Y-USUARIOS-2026-10-10.md): la administración de campañas pertenece a la plataforma IA y la API financiera no se modifica sin autorización. Los cambios existentes se **inventarían y separan**; no se revierten automáticamente.

## Estado de ramas

| Rama | Contenido | Situación |
|---|---|---|
| `main` (= `origin/main`) | `c750b6a`, `8fdf8d3`, `2f182ab` | Ya subidos por el equipo. No se revierten. |
| `archivo/campanas-api-diseno-anterior` (local) | `0531391`: rutas múltiples, código interno, `/brasper/ai/campaigns/active` | **No aplicado.** Trabajo del diseño anterior, apartado al cambiar el plan. |
| `respaldo/ia-campanas-identidad-2026-10-10` (local) | Copia de los 3 commits | Solo respaldo. |

## Clasificación de `c750b6a`, `8fdf8d3` y `2f182ab`

| Grupo | Archivos | Uso desde IA tras el nuevo diseño |
|---|---|---|
| **Campañas (diseño anterior)** | `brasper/adapters/router/campaign_routes.py`, `brasper/application/campaign_service.py`, `transactions/application/campaign_policy.py`, `transactions/application/schemas/campaign_schema.py`, migración `083_coupon_campaign_rules`, ruta `POST /brasper/ai/quotes` y `campaign_quote.quote_for_client`, `BRASPER_IA_ADMIN_SECRET`, `tests/test_campaigns.py` | **Ninguno.** IA ya no llama `/brasper/ai/admin/campaigns*` ni `/brasper/ai/quotes`. Las rutas quedan inactivas: sin `BRASPER_IA_ADMIN_SECRET` responden 503. |
| **Identidad / estado privado** | `identity_links.py`, `identity_routes.py`, `domain/identity_link.py`, migración `084_ai_identity_links`, `BRASPER_IA_IDENTITY_LINK_ENABLED`, `ai_routes` (`/clients/{id}/history`, `/clients/{id}/operations`), `ai_service`, `ai_schemas`, `tests/test_identity_links.py`, `tests/test_brasper_ai_identity.py`, `scripts/*` (laboratorio PGlite y E2E) | Sí: vinculación de chats, estado privado e historial oficial para la elegibilidad de campañas cuando el contrato está desplegado. |
| **Correcciones financieras generales** | `coin/domain/commission_selection.py` (tramo único y `normalize_amount`), `transaction_use_cases.py` (bloqueos y tramo de la cotización al registrar), `coupon_use_cases.py`/`coupon_routes.py` (`max_uses` ≥ usados), `tests/test_c1_financial_integrity.py`, `tests/test_commission_selection.py`, `tests/test_coupon_concurrency.py` | Indirecto: cotización y registro coherentes en Brasper. |
| **Seguridad** | `auth_use_cases.py` (sin sesión para cuentas deshabilitadas), `auth_routes.py` (401 sin errores internos), `audited_routes_inventory.py`, `redactor.py`, `tests/test_login_account_state.py` | Ninguno directo. |

### Archivos mezclados (requieren cuidado si se separa)

- `transaction_use_cases.py`: reserva/consumo/liberación de cupones de campaña **y** las correcciones C1 en las mismas funciones.
- `ai_routes.py`, `settings.py`, `brasper/adapters/router/__init__.py`, `transactions/domain/models.py`: registran a la vez rutas o campos de campañas e identidad.
- Migración `083`: además de las columnas de campaña, elimina el índice único `uq_coupon_redemptions_coupon_user_live` (permite varios usos por persona cuando `per_user_limit` > 1). Afecta al registro general de cupones, no solo a campañas.

## Recomendación (requiere autorización del responsable de la API)

1. No revertir: lo publicado no rompe la API y las rutas de campañas quedan inactivas sin secreto administrativo.
2. Si se decide retirar campañas de la API: separarlas en un commit propio, revirtiendo solo `campaign_routes.py`, `campaign_service.py` y la ruta `/brasper/ai/quotes`. Conservar `083` (ya puede estar aplicada) y las correcciones C1 en `transaction_use_cases.py`.
3. El registro de operaciones en Brasper no admite hoy indicar un descuento de campaña de IA. El ahorro que muestra el bot es informativo; el asesor lo aplica al registrar con las herramientas que Brasper ya ofrece (p. ej. cupones del backoffice). Integrarlo en el cobro requiere un contrato nuevo en la API, fuera de este plan.
