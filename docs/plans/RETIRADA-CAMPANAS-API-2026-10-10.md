# Retirada selectiva de campañas en la API principal (`com_brasper_api`) — 10 de octubre de 2026

Ejecución de la sección «Retirada selectiva del diseño anterior en la API principal» del [plan de campañas y usuarios](PLAN-CAMPANAS-Y-USUARIOS-2026-10-10.md), sobre el [inventario](INVENTARIO-API-CAMPANAS-2026-10-10.md).

## Rama y alcance

| Dato | Valor |
|---|---|
| Repositorio | `com_brasper_api` |
| Rama prevista | `limpieza/retirada-campanas-api`, creada desde `main` en `fd3dc9e` (incluye los commits de facturación `faf3f83` y `fd3dc9e`, sin cambios) |
| Commit | `74595ff` — `refactor(brasper-ai): retirar administración y cotización de campañas de la API` |
| Parche de referencia | [`retirada-campanas-api.patch`](retirada-campanas-api.patch): diff completo de `c750b6a` y `2f182ab` (solo lectura; no se aplica) |

> **Incidencia de Git (requiere decisión del responsable).** Mientras se editaba, una acción externa al agente cambió el repositorio de la rama `limpieza/retirada-campanas-api` a `main` con los cambios sin confirmar (reflog: `checkout: moving from limpieza/retirada-campanas-api to main`). El commit `74595ff` quedó por eso en `main`, y después **otra acción externa lo subió a `origin/main`** (reflog de `origin/main`: `update by push`). El agente no ejecutó ese checkout ni ningún push. La rama `limpieza/retirada-campanas-api` quedó en `fd3dc9e`, sin el commit. No se corrigió automáticamente porque deshacerlo exige reescribir o añadir commits en `main` publicado. Opciones:
> - Mantenerlo (las pruebas pasan: 457).
> - Deshacerlo sin reescribir historial: `git revert 74595ff` en `main`, y volver a aplicarlo en la rama con `git cherry-pick 74595ff` para revisarlo.
> - Si `main` despliega automáticamente, las rutas `/brasper/ai/admin/campaigns*` y `/brasper/ai/quotes` ya pueden haber desaparecido del servidor. Revisar el punto 1 de «Dependencias restantes» y la importación en IA.

No se tocó ninguna base de datos ni se reescribió historial. No se añadió ninguna capacidad a la API.

## Retirado

| Elemento | Archivo | Motivo |
|---|---|---|
| Rutas `GET/POST /brasper/ai/admin/campaigns`, `GET /{id}/history`, `PUT /{id}`, `POST /{id}/publish`, `POST /{id}/disable` y `require_campaign_admin` | `app/modules/brasper/adapters/router/campaign_routes.py` (archivo eliminado) y su registro en `brasper/adapters/router/__init__.py` | Administración de campañas: vive solo en IA. |
| `CampaignService`, `CampaignConflict` | `app/modules/brasper/application/campaign_service.py` (archivo eliminado) | Solo lo usaban las rutas anteriores. |
| `CampaignDraft` | `transactions/application/schemas/campaign_schema.py` | Solo lo usaban servicio y rutas. |
| Ruta `POST /brasper/ai/quotes` (`personalized_quote`) | `brasper/adapters/router/ai_routes.py` | Cotización personalizada con campañas. |
| `CampaignQuoteRequest`, `quote_for_client` (y sus imports de BD/`BrasperAIService`) | `brasper/application/campaign_quote.py` | Su único consumidor era la ruta retirada. |
| `BRASPER_IA_ADMIN_SECRET` | `app/core/settings.py`; mención en `scripts/e2e_identity_link_pglite.py` | Sin otros consumidores. `Settings` usa `extra="ignore"`: si un entorno aún define la variable, la API arranca igual. |
| 5 entradas del inventario de auditoría (`/brasper/ai/quotes` y 4 de `/brasper/ai/admin/campaigns*`) | `audit/infrastructure/audited_routes_inventory.py` | La prueba de inventario exige igualdad con OpenAPI; sigue pasando. |
| Pruebas `test_save_draft_does_not_change_published_rules` y `test_bot_secret_cannot_manage_campaigns` | `tests/test_campaigns.py` | Exclusivas de código retirado. Se añadió `test_campaign_admin_and_quote_routes_were_removed_from_the_api` (rutas retiradas responden 404/405; las de identidad y clientes siguen publicadas). |

Mensajes de error de `CreateCouponUseCase`, `UpdateCouponUseCase` y `DeleteCouponUseCase` que remitían al «editor versionado de campañas» se reescribieron para indicar que las campañas se gestionan en la plataforma IA. La lógica no cambia.

## Conservado (y por qué)

| Elemento | Motivo |
|---|---|
| Identidad: `identity_links.py`, `identity_routes.py`, `domain/identity_link.py`, `/brasper/ai/clients/{id}/history`, `/operations`, `/clients/lookup`, `/clients/upsert`, `/deposit-accounts`, `ai_service`, `ai_schemas`, `BRASPER_IA_IDENTITY_LINK_ENABLED` | Fuera de la retirada; la IA los usa para elegibilidad y estado. |
| Autenticación (`auth_use_cases`, `auth_routes`), auditoría (`redactor`, inventario restante) y facturación | Correcciones independientes. |
| `coin/domain/commission_selection.py` (`select_commission`, `normalize_amount`) | Corrección financiera C1 y precisión de `2f182ab`. |
| `transaction_use_cases.py`: bloqueo cliente→cupón, tramo re-seleccionado, normalización del monto, `lock_transaction_owners`, `release_coupon_usage`, `validate_coupon_edit` | Integridad financiera general (cupones tradicionales incluidos). |
| `transaction_use_cases.py`: rama `campaign_rules` del registro (conteo de completadas/pendientes, `discount_for` con segmento/mínimo/máximo/tope, sellado `coupon_campaign_version`) | **Latente.** Solo actúa sobre filas con `campaign_rules`, que la API ya no puede crear ni publicar. Retirarla haría que una fila de campaña ya existente (si 083 se aplicó y se creó alguna) se aplicara **sin sus límites**: riesgo de descuento mayor al permitido. Se dejó comentada como latente. |
| `campaign_policy.py` (`discount_for`, `discount_state`, `validate_campaign_dates`) | `discount_for` además valida 0–100 % en cupones tradicionales (`test_legacy_invalid_percentage_cannot_be_redeemed`); `discount_state` alimenta el campo calculado `coupon_discount_state` de `TransactionReadDTO`. |
| `campaign_schema.CampaignRules`/`CampaignCopy` | Los usan `discount_for` y los DTO de cupones (`campaign_rules` en lectura y rechazo en alta/edición). |
| `campaign_quote.calculate` e `inverse_quote` | Funciones puras sin ruta ni BD. Son la referencia contra la que `test_c1_financial_integrity.py`, `test_commission_selection.py` y `test_campaigns.py` verifican que el registro reproduce el tramo, la precisión y los importes de la cotización. Retirarlas obligaba a reescribir pruebas financieras; se documentaron como referencia sin consumidores en producción. |
| `coupon_use_cases`: rechazo de `campaign_rules`/`CAMPAIGN` en alta y edición, borrado bloqueado para `CAMPAIGN`, `max_uses >= used_count`, versión optimista (`expected_version`, `campaign_version + 1`) y `coupon_routes` 409 | Mantienen el comportamiento actual de cupones tradicionales y protegen filas de campaña existentes. |
| `ListCouponsUseCase(automatic_only=True)` oculta cupones con `campaign_rules` **o con `per_user_limit`** | Cambio de `c750b6a` que también afecta a cupones tradicionales con límite por persona. No se revirtió para no alterar el comportamiento vigente; queda como decisión del responsable de la API. |
| Modelos: columnas `Coupon.campaign_rules`, `campaign_version`, `published_version`, `Transaction.coupon_campaign_version` y modelo `CouponCampaignVersion` | Corresponden a la migración 083; quitarlos desalinearía los metadatos de Alembic con el esquema. |
| Migraciones `083_coupon_campaign_rules` y `084_ai_identity_links` | **Sin cambios.** Pueden estar aplicadas; no se hace downgrade ni drop. 083 además elimina el índice único `uq_coupon_redemptions_coupon_user_live`, que afecta al registro general de cupones. |
| Scripts PGlite (`8fdf8d3`) | Laboratorio de migraciones e identidad; solo se quitó la variable retirada. `validate_migrations_pglite.py` sigue verificando la tabla `coupon_campaign_versions` de 083. |

## Dependencias restantes

### En la API (antes de mergear)

1. **Filas de campaña existentes.** Si en algún entorno se aplicó 083 y se usaron las rutas administrativas, puede haber cupones `CAMPAIGN`. Tras la retirada no hay forma de desactivarlos por API (edición y borrado genéricos los rechazan). Comprobación de solo lectura para el responsable:
   `SELECT id, code, is_active, used_count FROM transaction.coupons WHERE coupon_type = 'CAMPAIGN' OR campaign_rules IS NOT NULL;`
   Si hay filas activas, decidir aparte (desactivación por operación de datos aprobada, o permitirla en la edición genérica). No se hizo aquí.
2. Quitar `BRASPER_IA_ADMIN_SECRET` del entorno desplegado (Dokploy) tras el despliegue. Es opcional porque la API lo ignora.

### En IA (`com_brasper_ia`, no modificado por esta tarea)

- `backend/manage.py` `import-campaigns` sin `--file` lee `GET /brasper/ai/admin/campaigns`, que deja de existir. **Antes de desplegar esta rama**, si hay campañas que conservar, ejecutar la importación explícita o exportarlas con la consulta anterior y usar `--file`.
- `backend/core/brasper_api.personalized_quote` llama a `POST /brasper/ai/quotes`; `quotes.compute(..., identity=...)` es su único consumidor y hoy `agent_graph` llama a `compute` **sin** `identity`, así que la ruta no se usa. Es código muerto que conviene retirar en IA junto con el mock de `run_checks.py` (líneas cercanas a 2090).
- `backend/.env.example` y `backend/tests/identity_e2e.py` todavía mencionan `BRASPER_IA_ADMIN_SECRET`; `_integration_request(admin=True)` solo lo usa la importación anterior.
- El registro de operaciones de Brasper sigue sin aceptar un descuento de campaña de IA (ver inventario, punto 3): el ahorro del bot es informativo y el asesor lo aplica con las herramientas existentes.

## Pruebas

`com_brasper_api`: `.venv/Scripts/python.exe -m pytest -q tests`

| Momento | Resultado |
|---|---|
| Antes (rama recién creada desde `main`) | **458 passed** |
| Después (`74595ff`) | **457 passed** (−2 pruebas exclusivas de lo retirado, +1 prueba de retirada) |

Siguen pasando sin cambios `test_c1_financial_integrity.py`, `test_commission_selection.py`, `test_coupon_concurrency.py`, `test_coupon_percentage.py`, `test_identity_links.py`, `test_brasper_ai_identity.py`, `test_brasper_ai_routes.py`, `test_login_account_state.py`, `test_phase4_mutation_audit.py` (inventario de auditoría) y las de facturación.

## Cómo revisar (lo hace el responsable de la API)

Por la incidencia descrita arriba, el commit ya está en `main` y en `origin/main`. Revisarlo directamente:

```bash
cd com_brasper_api
git show --stat 74595ff                                      # 13 archivos, +47/−324
git diff fd3dc9e 74595ff                                     # diff por función
.venv/Scripts/python.exe -m pytest -q tests                  # 457 passed
```

1. Ejecutar la comprobación de filas `CAMPAIGN` (solo lectura) y, si las hay, importarlas en IA (`manage.py import-campaigns --file`): la ruta administrativa ya no existe en `main`.
2. Revisar el diff por función con este documento; confirmar las decisiones de «conservado».
3. No requiere migración nueva.
4. Retirar `BRASPER_IA_ADMIN_SECRET` del entorno y el código muerto de IA listado arriba.

Si se decide no retirar: `git revert 74595ff` en `main` (commit nuevo, sin reescribir historial).
