#!/usr/bin/env bash
# Fase 2 — Smoke post-deploy Brasper bot
# Uso: API_BASE=http://localhost:8002 ./scripts/smoke_brasper.sh

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8002}"
TENANT="${TENANT:-brasper}"

echo "==> Health"
curl -sf "${API_BASE}/health" | head -c 200
echo

echo "==> Chat smoke (ajustar auth si el endpoint lo exige)"
# TODO Fase 2: header Authorization / ops token
curl -sf -X POST "${API_BASE}/api/${TENANT}/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"hola"}' | head -c 400 || echo "WARN: chat falló (auth o stack)"
echo

echo "==> Smoke done"
