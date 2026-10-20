#!/usr/bin/env bash
set -Eeuo pipefail
TARGET="${1:-}"
MODE="${2:-}"
if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "Uso: bash PREPARAR_RED_TRABAJO.sh /ruta/a/sys/trabajo [--check]" >&2
  exit 2
fi
COMPOSE="$TARGET/compose.yaml"
[[ -f "$COMPOSE" ]] || { echo "ERROR: no existe $COMPOSE" >&2; exit 2; }
BACKUP=""
if [[ "$MODE" != "--check" ]]; then
  BACKUP_DIR="$HOME/NOA_backups/fuentes"
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/compose_trabajo_api_network_$(date +%Y%m%d_%H%M%S).yaml"
  cp -p "$COMPOSE" "$BACKUP"
  echo "Respaldo de Compose: $BACKUP"
fi
python3 - "$COMPOSE" "$MODE" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
mode = sys.argv[2]
s = p.read_text()
if "name: trabajo_work_api" in s and "- work_api" in s:
    print("OK: la red API-only trabajo_work_api ya esta configurada.")
    raise SystemExit(0)
needle = "      - identity_network\n"
if s.count(needle) != 1:
    raise SystemExit("ERROR: no se encontro exactamente el bloque de redes esperado; no se modifico.")
s = s.replace(needle, needle + "      - work_api\n", 1)
netneedle = "  identity_network:\n    external: true\n    name: backend_identity_api\n"
if s.count(netneedle) != 1:
    raise SystemExit("ERROR: no se encontro la declaracion identity_network esperada; no se modifico.")
s = s.replace(netneedle, netneedle + "  work_api:\n    name: trabajo_work_api\n    internal: true\n", 1)
if mode == "--check":
    print("OK: se puede conectar solo work-api a trabajo_work_api; PostgreSQL permanece en work_private.")
    raise SystemExit(0)
p.write_text(s)
print(f"OK: red API-only agregada en {p}.")
PY
if [[ "$MODE" != "--check" ]]; then
  if (cd "$TARGET" && docker-compose config >/dev/null); then
    echo "OK: docker-compose config valido."
    echo "Siguiente paso manual: cd '$TARGET' && docker-compose up -d work-api"
  else
    cp -p "$BACKUP" "$COMPOSE"
    echo "ERROR: docker-compose config fallo; se restauro el Compose anterior." >&2
    exit 1
  fi
fi
