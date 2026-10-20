#!/usr/bin/env bash
set -Eeuo pipefail
TARGET="${1:-}"
MODE="${2:-}"
if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "Uso: bash CONFIGURAR_RED_IDENTIDAD.sh /ruta/a/sys/backend [--check]" >&2
  exit 2
fi
COMPOSE="$TARGET/compose.yaml"
[[ -f "$COMPOSE" ]] || { echo "ERROR: no existe $COMPOSE" >&2; exit 2; }
BACKUP=""
if [[ "$MODE" != "--check" ]]; then
  BACKUP_DIR="$HOME/NOA_backups/fuentes"
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/compose_identidad_red_api_$(date +%Y%m%d_%H%M%S).yaml"
  cp -p "$COMPOSE" "$BACKUP"
  echo "Respaldo de Compose: $BACKUP"
fi
python3 - "$COMPOSE" "$MODE" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
mode = sys.argv[2]
text = p.read_text()
if "name: backend_identity_api" in text and "aliases: [identity-api]" in text:
    print("OK: la red dedicada de la API de Identidad ya esta configurada.")
    raise SystemExit(0)
if "  api:\n" not in text or "  db:\n" not in text:
    raise SystemExit("ERROR: compose.yaml no coincide con la estructura esperada; no se modifico.")
if "networks:\n  internal:\n" not in text:
    raise SystemExit("ERROR: no se encontro la declaracion de redes esperada; no se modifico.")
start = text.index("  api:\n")
end = text.find("\nvolumes:\n", start)
if end < 0:
    raise SystemExit("ERROR: no se encontro el final del bloque api; no se modifico.")
block = text[start:end]
if block.count("    networks: [internal]") != 1:
    raise SystemExit("ERROR: el bloque api no contiene exactamente la red esperada; no se modifico.")
block = block.replace("    networks: [internal]", "    networks:\n      internal: {}\n      identity_api:\n        aliases: [identity-api]")
updated = text[:start] + block + text[end:]
updated = updated.replace("networks:\n  internal:\n", "networks:\n  internal:\n  identity_api:\n    name: backend_identity_api\n", 1)
if mode == "--check":
    print("OK: se puede agregar backend_identity_api solo a la API, manteniendo PostgreSQL en internal.")
    raise SystemExit(0)
p.write_text(updated)
print(f"OK: red API-only agregada en {p}.")
print("IMPORTANTE: se guardo el archivo; aun no se reiniciaron contenedores.")
PY
if [[ "$MODE" != "--check" ]]; then
  if (cd "$TARGET" && docker-compose config >/dev/null); then
    echo "OK: docker-compose config valido."
    echo "Siguiente paso manual: cd '$TARGET' && docker-compose up -d api"
  else
    cp -p "$BACKUP" "$COMPOSE"
    echo "ERROR: docker-compose config fallo; se restauro el Compose anterior." >&2
    exit 1
  fi
fi
