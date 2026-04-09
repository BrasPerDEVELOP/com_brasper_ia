# Backend — API FastAPI

API **FastAPI** con LLM (DeepSeek/OpenAI-compatible), caché **Redis**, integración CRM/calendario/WhatsApp. El widget web del chat vive en el directorio hermano `../webchat/`.

---

## Estructura (esta carpeta)

```text
backend/
├── main.py                   # FastAPI, CORS, scheduler (job cada 5 min)
├── requirements.txt
├── .env                      # Credenciales y configuración (no commitear secretos)
└── app/
    ├── application/          # Casos de uso (chat, CRM, calendario, lead scoring, Brasper…)
    ├── domain/               # Contratos (ports) y modelos de dominio
    └── infrastructure/       # Adaptadores: HTTP, Redis, LLM, WhatsApp, CRM, jobs
        └── adapter/
            ├── input/        # Controladores FastAPI (`http_controller.py`)
            └── output/       # Redis, modelos LLM, herramientas, `persist_leads_job`, etc.
```

Flujo resumido: rutas en `app/infrastructure/adapter/input/http_controller.py`; casos de uso en `application/`; Redis y LLM en `infrastructure/adapter/output/`.

---

## Requisitos

- **Python** 3.10+ (recomendado)
- **Redis** en ejecución (caché de proyectos, leads, temporizadores de sesión; host/puerto vía `.env`)

---

## Configuración

1. Crea o edita `.env` en **esta carpeta** (`backend/.env`).

Variables habituales:

| Área | Variables |
|------|-----------|
| LLM | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `DEEPSEEK_MAX_OUTPUT_TOKENS`, `DEEPSEEK_LOG_USAGE` |
| CRM / Zefiron | `ZEFIRON_USERNAME`, `ZEFIRON_PASSWORD` |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`; opcional: `REDIS_USERNAME`, `REDIS_PASSWORD`, `REDIS_SSL` |
| Chat | `CHAT_HISTORY_KEEP_PAIRS`, `CHAT_HISTORY_SNIPPET_CHARS` |
| Debounce (menos llamadas al LLM por ráfagas) | `CHAT_DEBOUNCE_SECONDS` (ej. `2.5`; `0` = desactivado), `CHAT_DEBOUNCE_IMMEDIATE_MIN_WORDS` (ej. `5`: mensajes largos sin esperar) |
| WhatsApp (webhook) | `VERIFY_TOKEN`, `wp_key` |

El debounce acumula mensajes del mismo usuario y ejecuta **una** pasada al pipeline (LLM + orquestador) tras unos segundos de silencio. En varios workers de uvicorn, cada proceso tiene su propia cola en memoria (para escala horizontal haría falta Redis u otra cola compartida).

2. Entorno virtual e instalación (desde `backend/`):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Redis local (ejemplo):

```bash
redis-server
```

---

## Ejecutar la API

Desde `backend/` con el venv activado:

```bash
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

- Base URL: `http://localhost:8001`
- Al iniciar, el scheduler ejecuta cada **5 minutos** el job de persistencia de leads (`persist_leads_job`): envía al CRM los leads cuya sesión en Redis expiró y limpia las claves.

### Rutas útiles

| Método | Ruta | Uso |
|--------|------|-----|
| POST | `/consulta-chat` | Chat genérico (`user_id`, `message_user`) |
| POST | `/consulta-webchat` | Body JSON `{ "message": "..." }` — usado por el widget |
| POST | `/save-lead` | Pruebas de lead |
| POST | `/create-date` | Crear cita |
| GET | `/dates` | Listar citas |
| GET/POST | `/webhook` | Verificación y mensajes WhatsApp Cloud API |

---

## Job de leads (solo persistencia)

Sin levantar la API (por ejemplo desde cron), desde `backend/`:

```bash
source .venv/bin/activate
PYTHONPATH=. python app/infrastructure/adapter/output/persist_leads_job.py
```

Con la API en marcha, el mismo job ya corre cada 5 minutos vía APScheduler en `main.py`.

---

## Widget web

El cliente embebible está en **`../webchat/`** (`npm install`, `npm run dev`, variable `VITE_CHAT_API_URL` apuntando a `http://localhost:8001/consulta-webchat`). Detalle de build y opciones del widget: ver ese directorio.

---

## Notas

- Ejecuta `uvicorn` con **directorio de trabajo** en `backend/` para que `load_dotenv()` encuentre `.env` de forma fiable.
- No subas `credentials.json`, `.env` ni claves reales al repositorio.
