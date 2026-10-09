# Prompt para el agente de desarrollo

Copia el siguiente texto en el agente que tendrá acceso a los repositorios locales:

---

Termina el trabajo pendiente de código de Brasper IA siguiendo este plan actualizado:

`C:\Users\USER\Documents\GitHub\com_brasper_ia\docs\plans\PLAN-CODIGO-PENDIENTE-2026-10.md`

Repositorios:
- `C:\Users\USER\Documents\GitHub\com_brasper_ia`
- `C:\Users\USER\Documents\GitHub\com_brasper_api`

Primero lee las instrucciones AGENTS.md aplicables, el plan local completo, la auditoría `docs/plans/AUDITORIA-ATENCION-AUTONOMA-2026-10.md` y los diffs actuales. Hay implementación sin commit de perfiles, campañas, historial, imágenes y defensas financieras: presérvala, comprueba su comportamiento y complétala. No empieces de cero ni borres cambios existentes.

Ejecuta C1–C8 del plan en orden de riesgo. Prioriza integridad financiera de promociones y migraciones, identidad/estado privado de envíos y pausa de IA ante intervención humana. Después completa ES/PT, encuestas/espera, medios, permisos/panel y validación integrada. No te limites a proponer otro plan: implementa y prueba todo lo que pueda completarse localmente.

Las campañas descuentan 0–100% de la comisión, nunca capital ni tipo de cambio. Para primer envío cuentan operaciones completadas; una pendiente reserva y una fallida/cancelada libera una sola vez. Cotizar no reserva. El pago y la ejecución financiera permanecen bajo control humano/sistema autorizado. No inventes porcentajes recurrentes, horarios, textos aprobados ni datos financieros.

Mantén atención libre por IA, sin menús obligatorios ni constructor visual de flujos. Conserva Telegram. Usa datos sintéticos, proveedores simulados y PostgreSQL/Redis aislados; cubre migraciones, concurrencia real, reinicios, backup/restauración y regresión. Compilar y pasar mocks no acredita funcionamiento completo.

No despliegues ni modifiques producción, Umbler o Meta. No actives campañas reales, publiques la app o documentos legales reales, envíes mensajes a clientes ni ejecutes movimientos financieros. No investigues ni configures cuentas de terceros en esta tarea: esas actividades están separadas en `docs/plans/PLAN-DEPENDENCIAS-EXTERNAS-2026-10.md`.

Para contratos Meta aún no confirmados, prepara interfaces internas, persistencia y pruebas con fixtures claramente simulados; no inventes nombres de campos ni declares Coex operativo. Mantén esas salidas desactivadas hasta confirmar contrato e integración real. No uses la falta de una cuenta Meta para dejar sin hacer lógica interna o pruebas locales.

Ejecuta los checks, doctests, evals deterministas, tests de API, TypeScript/build y pruebas locales pertinentes. Actualiza la auditoría y el estado C1–C8 con archivos, comandos y resultados. Si alguna prueba no se puede ejecutar, indica el impedimento concreto y déjala pendiente; no la marques aprobada. Al terminar entrega cambios, evidencia de validación, instrucciones reproducibles y pendientes externos separados. No marques el producto completo como terminado por cerrar solo el código.

---
