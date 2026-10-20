# Aplicar NOA Trabajo MVP

Este paquete crea un servicio nuevo en `sys/trabajo`; no modifica la base ni el codigo de Identidad. No incluye aun el dashboard React.

## 1. Copiar el modulo

```bash
cd ~/Documents/portf/down
unzip NOA_TRABAJO_MVP_v0.1.0.zip
mkdir -p ~/Documents/portf/sys/trabajo
cp -a NOA_TRABAJO_MVP_v0.1.0/. ~/Documents/portf/sys/trabajo/
```

## 2. Separar la red de la API de Identidad

Trabajo no debe compartir la red de Identidad con su PostgreSQL. El script crea una red API-only, hace respaldo del Compose y valida su sintaxis:

```bash
bash ~/Documents/portf/sys/trabajo/CONFIGURAR_RED_IDENTIDAD.sh ~/Documents/portf/sys/backend --check
bash ~/Documents/portf/sys/trabajo/CONFIGURAR_RED_IDENTIDAD.sh ~/Documents/portf/sys/backend
cd ~/Documents/portf/sys/backend
docker-compose up -d api
curl -i --max-time 5 http://127.0.0.1:18081/health
```

No continúes si la API de Identidad no responde HTTP 200. La base `db` de Identidad permanece solo en `backend_internal`; Trabajo se conecta a Identidad por `backend_identity_api`.

## 3. Crear secretos y fijar el departamento

En `sys/trabajo`, ejecuta el comando interactivo de la sección Instalación de `README.md`. Solicita el ID numerico del departamento piloto y genera dos secretos aleatorios distintos. Esta instancia queda fijada a un solo departamento. No subas `.env` a Git.

## 4. Levantar y migrar la nueva base

```bash
cd ~/Documents/portf/sys/trabajo
docker-compose up -d --build
docker-compose exec work-api alembic upgrade head
docker-compose exec work-api alembic current
docker-compose exec work-api alembic check
curl -i --max-time 5 http://127.0.0.1:18082/health
```

Se espera `0001_trabajo (head)`, `No new upgrade operations detected.` y HTTP 200. La migracion inicial crea tablas unicamente en la nueva base `trabajo`.

## 5. Probar

Abre `http://127.0.0.1:18082/docs`, autoriza con un token valido de Identidad y prueba el flujo del README. Antes de usarlo con tareas reales, ejecuta:

```bash
bash PROBAR_POSTGRES.sh
```

No ejecutes comandos `down -v` en el proyecto de Identidad. El volumen de archivos adjuntos requiere respaldo independiente del dump PostgreSQL.
