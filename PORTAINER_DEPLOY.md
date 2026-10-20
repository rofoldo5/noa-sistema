# NOA — despliegue integrado con Portainer (Git Repository)

Este Stack integra el código versionado en `backend/`, `trabajo/` y `noa-frontend/`. No incluye datos de bases de datos. En un servidor nuevo, Identidad y Trabajo empezarán con volúmenes vacíos.

## Arquitectura y redes

- `identity-db` + `identity-api`: PostgreSQL de Identidad en `identity_private`.
- `work-db` + `work-api`: PostgreSQL de Trabajo en `work_private`.
- `identity_api`: red compartida por `identity-api`, `work-api` y frontend; no contiene PostgreSQL.
- `work_api`: red compartida por `work-api` y frontend; no contiene PostgreSQL.
- Los puertos de host de las tres aplicaciones se enlazan a `127.0.0.1`. Para acceso de los programadores, publicar el frontend detrás de un proxy inverso con HTTPS. No expongas 18081/18082 directamente a Internet.

El Compose omite `no-new-privileges:true` por la incompatibilidad AppArmor/Snap Docker ya reproducida en el entorno de desarrollo. Se mantienen imágenes con usuario no root, `read_only`, `cap_drop: ALL` y bases en redes internas. Revisa esta opción si el host de producción usa Docker Engine estándar compatible.

## Variables requeridas

Configura estas variables en Portainer al crear el Stack. Los valores deben generarse con un generador criptográfico; no uses los marcadores de `.env.example`.

- `IDENTITY_POSTGRES_PASSWORD`: secreto hexadecimal aleatorio de 64 caracteres.
- `IDENTITY_JWT_SECRET`: secreto hexadecimal aleatorio de 96 caracteres.
- `WORK_POSTGRES_PASSWORD`: secreto hexadecimal aleatorio de 64 caracteres.
- `WORK_DEPARTMENT_ID`: ID numérico del departamento que atenderá esta instancia de Trabajo. En una base Identidad nueva, se puede usar `1` si ese será el primer departamento creado.
- `MEDIA_PREVIEW_SECRET`: secreto hexadecimal aleatorio de 96 caracteres.
- `IDENTITY_API_PORT`: `18081` (solo loopback del host).
- `WORK_API_PORT`: `18082` (solo loopback del host).
- `NOA_FRONTEND_PORT`: `18083` (solo loopback del host).
- `MAX_ATTACHMENT_BYTES`: `104857600` (100 MiB).

Para generar un `.env` local con secretos:

```bash
bash generar_env.sh
stat -c '%a %n' .env
```

Debe mostrar permisos `600`. Ese archivo es local, está ignorado por Git y **Portainer Git Stack no lee automáticamente el `.env` de tu estación de trabajo**. Copia sus valores a las variables del Stack en Portainer; nunca lo subas al repositorio ni pegues secretos en tickets o chats.

## Crear el Stack desde Git Repository

1. En Portainer, abre **Stacks → Add stack → Git Repository**.
2. Nombre del Stack: `noa`.
3. Repository URL: `https://github.com/rofoldo5/noa-sistema.git`.
4. Reference/Branch: `refs/heads/main`.
5. Compose path: `docker-compose.yml`.
6. Si el repositorio es privado, configura credenciales de lectura de GitHub en Portainer. No incluyas un token en la URL del repositorio.
7. Añade todas las variables enumeradas arriba y despliega el Stack.
8. No habilites actualizaciones automáticas mientras se valida el primer piloto; despliega manualmente después de revisar cada cambio probado.

## Inicialización en servidor nuevo

Después de que los contenedores arranquen, las APIs estarán en ejecución pero Identidad no estará saludable hasta que se creen sus tablas. Desde la consola de Portainer del contenedor `identity-api`, ejecuta:

```bash
python -m app.migrate
python -m app.bootstrap
```

`app.bootstrap` solicitará correo, nombre y contraseña para crear el primer SuperAdmin. No compartas la contraseña ni la salida que incluya tokens.

Después inicia sesión en NOA y crea el departamento piloto. Verifica su ID mediante `GET /departments` en Identidad. Si no coincide con `WORK_DEPARTMENT_ID`, actualiza esa variable en el Stack y redepliega el servicio/Stack sin borrar volúmenes.

Desde la consola del contenedor `work-api`, ejecuta la migración de su base independiente:

```bash
alembic upgrade head
alembic current
alembic check
```

Se espera `0001_trabajo (head)` y `No new upgrade operations detected.`. Luego verifica:

```bash
curl -i http://127.0.0.1:18081/health
curl -i http://127.0.0.1:18082/health
curl -i http://127.0.0.1:18083/health
```

Los dos primeros comandos deben ejecutarse en el host Docker. El frontend estará disponible en `http://127.0.0.1:18083` desde el propio servidor. Para los programadores, configura un dominio y proxy HTTPS que apunte al frontend; el método exacto depende del proxy instalado.

## Datos, respaldos y actualizaciones

- GitHub contiene código, no los datos PostgreSQL ni los adjuntos.
- No uses `docker compose down -v` ni elimines los volúmenes `identity_pgdata`, `work_pgdata` o `work_attachments`.
- Respalda ambas bases PostgreSQL y el volumen `work_attachments`.
- Aplica migraciones de Identidad y Trabajo por separado, después de un respaldo verificado.
- Antes de desplegar a `main`, valida cambios en una rama/entorno de QA y revisa los logs del Stack.
