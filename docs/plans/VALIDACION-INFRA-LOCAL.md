# Validación local con servicios reales

El entorno `docker-compose.validation.yml` usa PostgreSQL 16 y Redis 7 con datos sintéticos, sin puertos publicados y con red interna. El contenedor de pruebas no tiene acceso a servicios de producción. PostgreSQL usa almacenamiento temporal; el nombre del proyecto es exclusivo de validación.

Desde la raíz del repositorio:

```powershell
docker compose -f docker-compose.validation.yml up --build --abort-on-container-exit --exit-code-from checks
```

El runner exige una base `brasper_test_*`, host local/de pruebas, Redis DB 15 y dotenv desactivado. Aplica Alembic, comprueba inicialización repetida, locks Redis con dueño correcto, exclusión concurrente de idempotencia/documentos en PostgreSQL y seguimiento persistente. Este conjunto no sustituye las pruebas de concurrencia financiera de la otra API ni el ensayo de backup/restore.

La migración IA `0009_autonomous_attention` incorpora tablas que antes solo se creaban al iniciar, revisiones de conversación y recibos de salida. El índice único de documentos falla ante duplicados históricos: revisar antes de migrar, sin borrar evidencias para forzarlo. El downgrade destructivo se rechaza; restaurar un backup verificado si se necesita volver físicamente al esquema anterior. Revertir binarios conservando tablas aditivas es distinto de revertir datos.

## Evidencia del 8 de octubre

- No hay Docker, PostgreSQL ni Redis instalados disponibles para esta sesión. WSL informa que no está instalado.
- Se descargaron binarios portables desde [EDB, proveedor enlazado por PostgreSQL](https://www.enterprisedb.com/download-postgresql-binaries). Windows impidió ejecutar `initdb.exe`: «Una directiva de Control de aplicaciones bloqueó este archivo». No se desactivó esa protección ni se intentó eludirla.
- El entorno reproducible queda preparado, **sin ejecución acreditada**. Un equipo autorizado con Docker o un runtime permitido debe ejecutar el comando y conservar la salida. No marcar pruebas de PostgreSQL/Redis como aprobadas a partir de SQLite.

Pendientes adicionales: migración financiera 083 sobre datos históricos sintéticos; competencia real por cliente/cupón entre campañas; rollback transaccional; backup y restauración en una segunda base y comparación de conteos/evidencias.
