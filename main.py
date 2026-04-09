from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.infrastructure.adapter.input.http_controller import router

# --- Imports para el Programador de Tareas ---
from apscheduler.schedulers.background import BackgroundScheduler
from app.infrastructure.adapter.output.persist_leads_job import main as persist_leads_job_main

import asyncio

# --- Configuración del Programador (APScheduler) ---
scheduler = BackgroundScheduler(timezone="America/Lima")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Executing startup tasks...")
    # Iniciar el programador de tareas
    scheduler.add_job(persist_leads_job_main, 'interval', minutes=5, id="persist_leads_job")
    scheduler.start()
    print("Scheduler iniciado. El job de persistencia de leads se ejecutará cada 5 minutos.")
    yield
    print("Executing shutdown tasks: stopping scheduler...")
    scheduler.shutdown()
    print("Scheduler detenido.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main():
    print("Corriendo modelo")
      

if __name__=="__main__":
    main()
    
