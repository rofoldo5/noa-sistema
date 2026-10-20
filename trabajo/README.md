# NOA - Modulo Trabajo MVP Kanban v0.1.0

Servicio independiente para el piloto de tres programadores. Esta primera entrega contiene el esquema PostgreSQL/Alembic y una API FastAPI utilizable desde Swagger. Todavia no incluye el dashboard React.

## Alcance funcional

- Proyectos; al crear un proyecto se crea un tablero Kanban principal con las columnas Pendiente, En proceso y Finalizado.
- Tareas con titulo obligatorio, fecha de inicio y fecha final opcional.
- Secciones de apuntes por tarea (Frontend, Backend, QA, etc.) y checklist independiente por seccion.
- Responsable e integrantes de una tarea.
- Comentarios asociados a la tarea y menciones estructuradas a participantes autorizados.
- Adjuntos de imagen y video dentro de comentarios, con metadatos en PostgreSQL y bytes en un volumen persistente independiente.
- URLs temporales firmadas (10 minutos) para que el navegador pueda mostrar imagenes y videos inline sin enviar el Bearer en cada peticion multimedia.
- Historial de actividad y progreso de checklist para las tarjetas Kanban.

## Tablas de la base Trabajo

1. `projects`
2. `boards`
3. `board_columns`
4. `tasks`
5. `task_sections`
6. `checklist_items`
7. `task_members`
8. `comments`
9. `comment_mentions`
10. `attachments`
11. `task_activity`
12. `alembic_version` (gestionada por Alembic)

Los IDs de usuario y departamento son referencias externas de Identidad. No se crean claves foraneas entre las bases, ni se consulta directamente la base de Identidad. Los endpoints de Trabajo validan la sesion con `GET /auth/me` y usan la API de Identidad para validar integrantes.

## Aislamiento de red requerido

**No conectes Trabajo a la red que comparte Identidad con su PostgreSQL.** El Compose actual de Identidad usa `backend_internal` tanto para `api` como para `db`. Para que Trabajo llegue a la API pero no pueda alcanzar la base de Identidad, primero agrega una red API-only:

```bash
bash CONFIGURAR_RED_IDENTIDAD.sh ~/Documents/portf/sys/backend --check
bash CONFIGURAR_RED_IDENTIDAD.sh ~/Documents/portf/sys/backend
```

El script respalda `compose.yaml`, agrega `backend_identity_api` solo al servicio `api` y valida `docker-compose config`. No reinicia servicios automaticamente. Luego aplica la nueva red:

```bash
cd ~/Documents/portf/sys/backend
docker-compose up -d api
curl -i --max-time 5 http://127.0.0.1:18081/health
```

Comprueba que la API responde HTTP 200 antes de continuar. La base `db` de Identidad permanece unicamente en `backend_internal`.

## Instalacion local

Requisitos: Docker Compose, servicio de Identidad en ejecucion y red `backend_identity_api` creada. Copia este directorio a `~/Documents/portf/sys/trabajo`.

Genera `.env` con dos secretos diferentes; no uses los valores de ejemplo:

```bash
cd ~/Documents/portf/sys/trabajo
read -rp "ID numerico del departamento piloto (consultalo en Identidad): " WORK_DEPARTMENT_ID
[[ "$WORK_DEPARTMENT_ID" =~ ^[1-9][0-9]*$ ]] || { echo "ID invalido"; exit 1; }
export WORK_DEPARTMENT_ID
python3 - <<'PY'
import secrets
from pathlib import Path
import os
work_department_id = os.environ['WORK_DEPARTMENT_ID']
content = '\n'.join([
    'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32),
    'IDENTITY_API_URL=http://identity-api:8000',
    'WORK_DEPARTMENT_ID=' + work_department_id,
    'MAX_ATTACHMENT_BYTES=104857600',
    'MEDIA_PREVIEW_SECRET=' + secrets.token_urlsafe(48),
    '',
])
Path('.env').write_text(content)
Path('.env').chmod(0o600)
print('Archivo .env creado con permisos 600. No lo compartas ni lo subas a Git.')
PY
```

Inicia PostgreSQL y la API:

```bash
docker-compose up -d --build
```

Aplica la migracion inicial a la base nueva de Trabajo:

```bash
docker-compose exec work-api alembic upgrade head
docker-compose exec work-api alembic current
docker-compose exec work-api alembic check
curl -i --max-time 5 http://127.0.0.1:18082/health
```

Se espera `0001_trabajo (head)`, `No new upgrade operations detected.` y HTTP 200. Esta base y su volumen son independientes de Identidad.

Abre `http://127.0.0.1:18082/docs`. Autoriza con un Bearer token emitido por Identidad. La API de Trabajo comprueba el token mediante Identidad; si Identidad no responde, las operaciones autenticadas fallan de forma cerrada con 503. `/health` solo comprueba PostgreSQL de Trabajo.

## Primer flujo de uso

1. Consulta `GET /departments` en Identidad con el token para obtener el ID de un departamento al que pertenezca el usuario.
2. En Trabajo, `POST /projects` con `department_id`, `name` y `description`. Esto crea un tablero Kanban y las tres columnas predeterminadas.
3. Usa `GET /projects/{project_id}/boards` para obtener `board_id` y columnas.
4. Crea una tarea con `POST /boards/{board_id}/tasks`: `title`, `start_date` opcional (por defecto hoy), `due_date` opcional y `description` opcional. El creador queda como responsable inicial.
5. Agrega secciones con `POST /tasks/{task_id}/sections`, checklist con `POST /sections/{section_id}/checklist`, integrantes con `POST /tasks/{task_id}/members` y comentarios con `POST /tasks/{task_id}/comments`.
6. Para imagenes y videos, crea el comentario y sube el archivo a `POST /comments/{comment_id}/attachments` como multipart field `file`. La respuesta trae `preview_url` y `download_url` temporales; el navegador puede usar `<img>` o `<video controls>` directamente con esa URL durante 10 minutos.

Solo se aceptan firmas de archivo reconocidas para PNG, JPEG, GIF, WebP, MP4, QuickTime y WebM. Limite predeterminado: 100 MiB. El nombre original se guarda como metadato; el almacenamiento usa una clave aleatoria. El contenido binario no se guarda en PostgreSQL.

## Endpoints principales

- `GET /projects`, `POST /projects`
- `GET /projects/{project_id}/boards`, `POST /projects/{project_id}/boards`
- `GET /boards/{board_id}/columns`, `GET /boards/{board_id}/tasks`, `POST /boards/{board_id}/tasks`
- `GET /tasks/{task_id}`, `PATCH /tasks/{task_id}`
- `POST /tasks/{task_id}/sections`, `PATCH /sections/{section_id}`
- `POST /sections/{section_id}/checklist`, `PATCH /checklist/{item_id}`
- `POST /tasks/{task_id}/members`, `DELETE /tasks/{task_id}/members/{user_id}`
- `GET /tasks/{task_id}/comments`, `POST /tasks/{task_id}/comments`
- `POST /comments/{comment_id}/attachments`, `GET /attachments/{id}/preview`, `GET /attachments/{id}/download`
- `GET /tasks/{task_id}/activity`, `GET /health`

## Pruebas

Pruebas locales con SQLite:

```bash
DATABASE_URL=sqlite:////tmp/noa_work_test.db \
IDENTITY_API_URL=http://identity-not-used.invalid \
ATTACHMENT_STORAGE_PATH=/tmp/noa-work-attachments \
MEDIA_PREVIEW_SECRET=test-only-preview-secret-at-least-32-chars \
python3 -m pytest -q
```

Pruebas con PostgreSQL 17 desechable, sin puertos publicados ni volumenes persistentes:

```bash
bash PROBAR_POSTGRES.sh
```

El entorno de QA no se conecta a la base de Identidad ni al almacenamiento del piloto. No se configura `no-new-privileges` en el Compose de QA porque el Docker instalado mediante Snap en el host de desarrollo produjo una denegacion AppArmor reproducible con esa opcion; se mantienen red interna, usuario no root en la imagen de pruebas y filesystem de solo lectura.

## Limites explicitos del MVP

- Solo Kanban. Scrum, dependencias interdepartamentales y bot de Telegram no se implementan aqui.
- El tablero crea columnas predeterminadas; CRUD de columnas y archivado/eliminacion de proyectos/tareas se pueden agregar tras probar el flujo inicial.
- En este piloto, los usuarios autenticados con acceso al departamento pueden operar sus proyectos y tareas. El aislamiento de departamento es obligatorio; las politicas mas finas por rol de Trabajo deben cerrarse en la auditoria de autorizacion antes de produccion.
- La validacion de usuarios de otros participantes usa la API actual de Identidad con paginacion de 100; empleados sin permiso para listar integrantes solo pueden ser reconocidos como el usuario actual. Jefe/SuperAdmin pueden asignar integrantes visibles por Identidad.
- La dependencia de autenticacion con Identidad es deliberada: si Identidad esta fuera de servicio, las operaciones autenticadas de Trabajo responden 503 en vez de aceptar tokens sin validar su revocacion.
- El almacenamiento de adjuntos necesita respaldo propio, independiente del dump PostgreSQL.
