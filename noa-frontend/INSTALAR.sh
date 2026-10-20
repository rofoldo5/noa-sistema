#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Uso: bash INSTALAR.sh /ruta/a/sys/noa-frontend" >&2
  exit 2
fi
mkdir -p "$(dirname "$TARGET")"
if [[ -e "$TARGET" ]] && [[ -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "ERROR: el destino existe y no esta vacio: $TARGET" >&2
  echo "No se sobrescribio ningun archivo. Usa una ruta nueva o respalda y vacia el destino manualmente." >&2
  exit 2
fi
mkdir -p "$TARGET"
cp -a "$SOURCE"/. "$TARGET"/
echo "OK: NOA Frontend v1 copiado a $TARGET"
echo "Siguiente paso: cd '$TARGET' y seguir README_APLICAR.md"
