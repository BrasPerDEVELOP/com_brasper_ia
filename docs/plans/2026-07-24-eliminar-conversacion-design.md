# Eliminación administrativa de una conversación

## Objetivo

Permitir que un administrador elimine permanentemente del bot una conversación
y su historial cuando conoce tanto el ID interno como la referencia del usuario.
La operación no elimina cuentas externas de Telegram ni perfiles de la API
Brasper.

## Alternativas consideradas

1. Ejecutar SQL manual en producción: rápido, pero la base interna del contenedor
   no está accesible con las credenciales locales y aumenta el riesgo de apuntar
   al entorno equivocado.
2. Marcar la conversación como cerrada: reversible, pero no cumple la solicitud
   de eliminar datos.
3. Endpoint administrativo protegido: recomendado porque usa la misma conexión
   del runtime, deja auditoría y permite verificar la identidad antes del borrado.

## Diseño

`DELETE /api/conversations/{conversation_id}` requiere permiso
`tenants:write` y el query param obligatorio `expected_user_ref`. La capa de
persistencia verifica que ambos identificadores correspondan al mismo registro.
En una sola transacción elimina mensajes, eventos de uso, citas y cotizaciones
asociadas, y finalmente la conversación. Luego la ruta registra un evento de
auditoría con los conteos eliminados.

Errores:

- `404` si la conversación no existe.
- `409` si `expected_user_ref` no coincide.
- `401/403` si el actor no tiene autorización.

La prueba mínima crea una conversación aislada, comprueba que un `user_ref`
incorrecto no borra nada y luego confirma la eliminación de todos los registros
dependientes.
