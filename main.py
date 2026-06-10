import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.infrastructure.adapter.input.http_controller import router


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:5173",
            "http://localhost:5179",
            "https://brasper.com",
            "https://www.brasper.com",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main():
    print("Corriendo modelo")
      

if __name__=="__main__":
    main()
    
