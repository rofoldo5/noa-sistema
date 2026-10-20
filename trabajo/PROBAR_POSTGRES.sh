#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="noa-work-qa-$(date +%Y%m%d%H%M%S)-$RANDOM"
cd "$ROOT"
cleanup() {
  docker-compose -p "$PROJECT" -f compose.qa.yaml down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
printf 'QA independiente: %s\n' "$PROJECT"
printf 'PostgreSQL temporal, sin puertos publicados ni volumenes persistentes.\n'
docker-compose -p "$PROJECT" -f compose.qa.yaml up --build --abort-on-container-exit --exit-code-from tests
printf 'OK: pruebas locales y PostgreSQL completadas.\n'
