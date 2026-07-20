# Tasas Brasper estrictamente desde su API

## Alcance

El cotizador conserva únicamente los corredores oficiales `PEN→BRL`,
`BRL→PEN`, `USD→BRL` y `BRL→USD`. No se agregan conversiones directas
`USD↔PEN` ni se calculan tasas cruzadas.

## Fuente de verdad

Para el tenant Brasper con `quote.api.enabled=true`, las tasas, comisiones y
cupones provienen exclusivamente de `apibras.finzeler.com`. Las tasas locales
del archivo de configuración dejan de ser un fallback. Si la API no responde o
no publica el corredor solicitado, el bot rechaza temporalmente la cotización
en lugar de calcular o inventar un importe.

## Dashboard

El panel consulta al backend, y el backend consulta la API Brasper. Las cuatro
tasas se muestran como datos de solo lectura con su origen claramente indicado.
El panel ya no permite editar tasas, comisiones o cupones locales cuando la API
está activa.

## Verificación

Las pruebas cubren el uso de una tasa viva, el rechazo cuando la API falla, la
ausencia de fallback local y el rechazo de `USD↔PEN`.
