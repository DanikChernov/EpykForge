#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${FORGE_API_URL:-http://localhost:8080}"
curl -fsS "$BASE_URL/health"
curl -fsS -X POST "$BASE_URL/api/demo/reset"
curl -fsS -X POST "$BASE_URL/api/demo/start" -H "Content-Type: application/json" -d '{"sync":true,"speed":99}'
curl -fsS "$BASE_URL/api/incidents/INC-1042"
