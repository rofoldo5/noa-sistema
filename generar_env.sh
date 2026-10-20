#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -e .env ]]; then
  echo "ERROR: .env ya existe; no se sobrescribio." >&2
  exit 2
fi
read -r -p "ID del departamento piloto en Identidad [1 si es instalacion nueva]: " WORK_DEPARTMENT_ID
WORK_DEPARTMENT_ID="${WORK_DEPARTMENT_ID:-1}"
if [[ ! "$WORK_DEPARTMENT_ID" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: el ID debe ser un entero positivo." >&2
  exit 2
fi
umask 077
python3 - "$WORK_DEPARTMENT_ID" <<'PY'
import secrets
import sys
from pathlib import Path
work_department_id = sys.argv[1]
values = {
    "IDENTITY_POSTGRES_PASSWORD": secrets.token_hex(32),
    "IDENTITY_JWT_SECRET": secrets.token_hex(48),
    "WORK_POSTGRES_PASSWORD": secrets.token_hex(32),
    "WORK_DEPARTMENT_ID": work_department_id,
    "MEDIA_PREVIEW_SECRET": secrets.token_hex(48),
    "IDENTITY_API_PORT": "18081",
    "WORK_API_PORT": "18082",
    "NOA_FRONTEND_PORT": "18083",
    "MAX_ATTACHMENT_BYTES": str(100 * 1024 * 1024),
}
Path(".env").write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
Path(".env").chmod(0o600)
print("OK: .env generado con secretos aleatorios y permisos 600.")
print("No subas .env a Git. En Portainer debes copiar sus valores a Stack > Environment variables.")
PY
