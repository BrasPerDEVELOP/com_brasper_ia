#!/usr/bin/env bash
# Detiene todos los procesos de Cauce (backend, poller, panel, whisper).
# No toca Postgres ni Redis (servicios del sistema).
set -u

stop() { # patrón, nombre
  if pgrep -f "$1" >/dev/null 2>&1; then
    pkill -f "$1" && printf "\033[33m• detenido: %s\033[0m\n" "$2"
  else
    printf "• %s no estaba corriendo\n" "$2"
  fi
}

echo "== Cauce · deteniendo procesos =="
stop "uvicorn main:app --port 8002"            "backend :8002"
stop "dev_telegram.py"                          "poller Telegram"
stop "uvicorn main:app --host 0.0.0.0 --port 8090" "whisper :8090"
stop "next dev"                                 "panel web :3000"
echo "Listo (Postgres y Redis siguen activos)."
