# Actualización Brasper IA — 10 de octubre de 2026

Autorizado por el usuario: panel y backend Brasper IA. Se actualizaron api, worker y admin-web; no se desplegó la API financiera ni el portal brasper.com.

- Release servidor: `/var/www/brasper-panel-releases/20261010T055451Z`.
- Backup inicial y final de PostgreSQL en `backup/ia.dump` y `backup/ia-final.dump`, con permisos restringidos. Código anterior y Compose conservados en backup. Imágenes anteriores etiquetadas `brasper-ia-api:rollback-20261010`, `brasper-ia-worker:rollback-20261010`, `brasper-ia-panel:rollback-20261010`.
- Restauración de backup en PostgreSQL 16 aislado aprobada; migraciones 0008→0011 aprobadas en la copia y luego en producción. Runtime candidato arrancó correctamente con la copia usando psycopg.
- Imagen candidata backend: 75/75 checks aprobados con red deshabilitada y datos temporales. Build panel/backend aprobados.
- Publicados `brasper-ia-api:candidate-20261010` en API y worker; `brasper-panel:candidate-20261010T055451Z` en admin-web. Código fuente del proyecto remoto actualizado preservando env y configuración existente. Tags Compose habituales apuntan a las imágenes nuevas.
- API healthy; worker y panel en ejecución. HTTPS devuelve 200 en conversaciones, agentes, biblioteca, promociones, seguimiento y accesos. `/login` no es una ruta del panel; no se toma su 404 como fallo del ingreso existente.
- No se activaron campañas ni vinculación de identidad: faltan configuración/secreto administrativo de campañas, clave de grants y disponibilidad de la API financiera correspondiente. Las páginas publicadas no certifican activación comercial ni Coex.

Rollback de contenedores: usar los dos Compose habituales y el override `rollback.yml` de la release, con `up -d --no-deps --no-build api worker admin-web`. No restaurar la base a ciegas después de actividad nueva: decidir la recuperación con los backups y los registros posteriores.
