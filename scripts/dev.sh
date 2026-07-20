#!/usr/bin/env bash
# Levanta TODO el stack de Cauce en desarrollo con un solo comando.
#   ./scripts/dev.sh          -> backend + poller Telegram + panel web
#   ./scripts/dev.sh --audio  -> además el microservicio Whisper (transcripción de audios)
# Es idempotente: si algo ya corre, no lo duplica. Logs en .logs/
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
LOGS="$ROOT/.logs"
mkdir -p "$LOGS"
WITH_AUDIO=0
[ "${1:-}" = "--audio" ] && WITH_AUDIO=1

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

running() { pgrep -f "$1" >/dev/null 2>&1; }
wait_http() { # url, segundos
  for _ in $(seq 1 "${2:-20}"); do curl -s "$1" >/dev/null 2>&1 && return 0; sleep 1; done; return 1
}

echo "== Cauce · arranque de desarrollo =="

# 0) Requisitos --------------------------------------------------------------
[ -x "$PY" ] || { red "No existe el venv en $ROOT/.venv. Créalo: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
if pg_isready >/dev/null 2>&1; then green "✓ Postgres responde"; else
  red "✗ Postgres NO responde. Arráncalo antes (ej: 'brew services start postgresql@16') y reintenta."; exit 1
fi
redis-cli ping 2>/dev/null | grep -q PONG && green "✓ Redis responde" || yellow "• Redis no responde (opcional: el bot degrada solo)"

# 1) Backend API (:8002) -----------------------------------------------------
if running "uvicorn main:app --port 8002"; then green "✓ backend ya corría (:8002)"; else
  ( cd "$ROOT/backend" && nohup "$PY" -m uvicorn main:app --port 8002 > "$LOGS/backend.log" 2>&1 & )
  wait_http "http://localhost:8002/health" 20 && green "✓ backend arriba (:8002)" || { red "✗ backend no levantó — mira $LOGS/backend.log"; tail -5 "$LOGS/backend.log"; }
fi

# 2) Poller de Telegram (lo que hace que el bot RESPONDA en dev) --------------
if running "dev_telegram.py"; then green "✓ poller Telegram ya corría"; else
  ( cd "$ROOT/backend" && nohup "$PY" -u dev_telegram.py > "$LOGS/telegram.log" 2>&1 & )
  sleep 3
  grep -q "polling activo" "$LOGS/telegram.log" 2>/dev/null && green "✓ poller Telegram activo (el bot ya responde)" || { yellow "• poller iniciado — revisa $LOGS/telegram.log"; tail -4 "$LOGS/telegram.log"; }
fi

# 3) Panel web (:3000) -------------------------------------------------------
if running "next dev"; then green "✓ panel web ya corría (:3000)"; else
  ( cd "$ROOT/web" && nohup npm run dev > "$LOGS/web.log" 2>&1 & )
  wait_http "http://localhost:3000" 30 && green "✓ panel web arriba (:3000)" || { yellow "• panel iniciando — revisa $LOGS/web.log"; }
fi

# 4) Whisper (opcional, --audio) --------------------------------------------
if [ "$WITH_AUDIO" = "1" ]; then
  if running "uvicorn main:app --host 0.0.0.0 --port 8090"; then green "✓ whisper ya corría (:8090)"; else
    ( cd "$ROOT/backend/whisper_service" && nohup "$PY" -m uvicorn main:app --host 0.0.0.0 --port 8090 > "$LOGS/whisper.log" 2>&1 & )
    wait_http "http://localhost:8090/health" 60 && green "✓ whisper arriba (:8090)" || yellow "• whisper tardó en cargar el modelo — revisa $LOGS/whisper.log"
  fi
else
  yellow "• Whisper (audios) NO iniciado. Úsalo con: ./scripts/dev.sh --audio"
fi

echo ""
green "Listo. Cómo probar:"
echo "  • Telegram: escribe al bot (p.ej. @nils_demo_bot) — debe responder."
echo "  • Panel:    http://localhost:3000  (login owner@agencia.com / demo1234) -> Conversaciones -> cliente Brasper"
echo "  • Parar todo: ./scripts/stop.sh    ·    Logs: $LOGS/"
