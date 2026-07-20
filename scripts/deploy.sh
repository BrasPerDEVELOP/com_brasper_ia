#!/usr/bin/env bash
# ============================================================================
# scripts/deploy.sh  —  Deploy del bot Brasper IA en el server (ia.finzeler.com)
#
# Actualiza el código y reconstruye SOLO los servicios de la app
# (api, worker, admin-web) que viven detrás de nginx.
#
#   ⚠️  NUNCA levanta el servicio `reverse-proxy` (Caddy) del compose: eso
#       tomaría los puertos 80/443 y tumbaría nginx + TODOS los sitios del
#       server. Por eso aquí se listan los servicios de forma explícita.
#
# Uso:
#   bash scripts/deploy.sh              # backend + worker + panel
#   bash scripts/deploy.sh api worker   # solo lo que indiques
# ============================================================================
set -euo pipefail

# Raíz del repo (este script vive en scripts/).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.server.yml)
if [ "$#" -gt 0 ]; then
  SERVICES=("$@")
else
  SERVICES=(api worker admin-web)
fi
HEALTH_URL="http://127.0.0.1:8596/health"

echo "==> [1/3] git pull --ff-only"
if ! git pull --ff-only; then
  echo "ERROR: 'git pull' falló. Revisa 'git status' (¿cambios locales?)." >&2
  echo "       Si son cambios ya subidos por otra vía: git reset --hard origin/main" >&2
  exit 1
fi

echo "==> [2/3] build + up: ${SERVICES[*]}"
"${COMPOSE[@]}" up -d --build "${SERVICES[@]}"

echo "==> [3/3] verificando ${HEALTH_URL} ..."
for _ in $(seq 1 20); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    echo "OK  ->  $(curl -s "$HEALTH_URL")"
    echo "✅ Deploy completado."
    exit 0
  fi
  sleep 2
done
echo "⚠️  /health no respondió a tiempo. Revisa: ${COMPOSE[*]} logs --tail 60 api" >&2
exit 1
