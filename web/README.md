# web/ · Frontend de producción (Next.js)

Panel de agencia con la **arquitectura del plan**: Next.js 16 (App Router) + TypeScript + Tailwind v4. Consume el backend real (`../backend`, puerto 8002).

## Ejecutar

```bash
cd web
npm run dev        # desarrollo → http://localhost:3000
# o producción:
npm run build && npm run start
```

El backend debe estar corriendo: `cd ../backend && ../.venv/bin/python -m uvicorn main:app --port 8002`.
La URL del backend se configura con `NEXT_PUBLIC_API_BASE` (default `http://localhost:8002`).

Con contenedores:

```bash
docker compose up --build
# abre http://localhost:8080
```

## Arquitectura

- `app/layout.tsx` — root layout, fuentes (Bricolage/Hanken/JetBrains vía `next/font`), envuelve todo en `<AppFrame>`.
- `components/AppFrame.tsx` — cliente: auth gate (login por email → token en localStorage), sidebar con nav filtrado por permisos (RBAC), topbar. Renderiza las rutas hijas solo si hay sesión.
- `lib/api.ts` — cliente fetch tipado (envía `X-Auth-Token`, maneja 401), tipos e `can()` para permisos.
- `app/{resumen,clientes,conversaciones,chat,consumo,integraciones,plantillas}/page.tsx` — una ruta real por pantalla (App Router), todas con datos reales del backend.
- `components/{Icon,TenantSelect}.tsx` — reutilizables.

`Clientes` ya consume la Admin API: puede crear/editar tenants, configurar refs de IA/WhatsApp/Telegram y pausar o reanudar clientes si el usuario tiene `tenants:write`.

Login demo solo en desarrollo local: `owner@agencia.com` (todo) · `agent@brasper.com` (solo su cliente) · `billing@agencia.com`.
En `APP_ENV=production` esos usuarios demo se purgan, el backend exige `PANEL_LOGIN_CODE` y debes entrar con el admin creado desde `PANEL_ADMIN_EMAIL`/`PANEL_ADMIN_TOKEN`.

Pantallas de fases siguientes (constructor de flujos, analítica histórica, RAG) se listan honestamente en Resumen → "En construcción", no se falsean.
