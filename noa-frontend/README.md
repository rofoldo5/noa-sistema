# NOA Frontend v1.0.1 — Identidad visual y MVP Kanban

Frontend React + TypeScript + Vite para el MVP de NOA Trabajo. Se basa visualmente en el frontend de referencia compartido, con identidad aprobada de NOA: águila geométrica, azul marino `#0B2D5B`, azul de interacción `#2563EB`, dorado `#D4AF37`, fondo `#F3F4F6`, texto `#1F2937` y secundario `#6B7280`. Usa Inter como tipografía principal, con tamaño base de 16 px y ajustes de legibilidad para controles, tarjetas, ficha de tarea y comentarios.

## Cambios visuales v1.0.1

- Logo de águila en login, estado de carga y navegación lateral.
- Favicon de NOA con el mismo símbolo.
- Paleta corporativa aprobada y fuente Inter.
- Escala tipográfica más legible; se aumentaron textos de tareas, formularios, checklist y bandeja de comentarios.

## Funciones incluidas

- Login con el endpoint JSON `POST /auth/login` de Identidad; consulta de sesión en `/auth/me` y logout.
- Solicitud de alta con `POST /auth/register` (la cuenta queda pendiente de aprobación).
- Dashboard con lista de proyectos y tablero Kanban.
- Creación de proyecto y tablero principal.
- Creación de tareas con título, descripción/apuntes generales, fecha de inicio y fecha final opcional.
- Tarjetas movibles entre columnas Kanban mediante arrastrar y soltar.
- Ficha de tarea con edición de título, apuntes, fechas, secciones por área (Frontend/Backend/QA), checklists e integrantes.
- Bandeja de comentarios a la derecha, menciones `@` a participantes asignados y vista previa de imágenes/videos adjuntos.
- Actividad reciente de la tarea.
- Diseño responsive para escritorio y móviles.

## Servicios y rutas

- Frontend: `http://127.0.0.1:18083`
- Identidad se consulta mediante `/identity-api/*`, proxy interno a `identity-api:8000`.
- Trabajo se consulta mediante `/work-api/*`, proxy interno a `work-api:8000`.
- No se habilita CORS porque el navegador utiliza rutas del mismo origen.
- El token de Identidad se guarda en `localStorage` con la clave `noa.access_token`; al recibir 401 la interfaz cierra la sesión local.

## Redes Docker (aislamiento)

Nginx necesita llegar a las dos APIs, pero no debe compartir red con las bases PostgreSQL. Por ello, Identidad usa `backend_identity_api` (solo API de Identidad) y Trabajo necesita una red `trabajo_work_api` conectada solo a `work-api`; `db` de Trabajo permanece exclusivamente en `work_private`.

El frontend Compose se conecta únicamente a `backend_identity_api` y `trabajo_work_api`. No se conecta a `backend_internal` ni a `trabajo_work_private`.

## Limitaciones conocidas de esta v1

- No incluye Scrum, dependencias avanzadas, notificaciones push ni automatizaciones.
- El CRUD de columnas, archivado/eliminación de proyectos y gestión avanzada de permisos se posponen.
- El backend de Trabajo fija cada despliegue a un `WORK_DEPARTMENT_ID`; en el formulario de proyecto hay que seleccionar ese departamento.
- El listado de personas visible en la interfaz depende de los permisos que devuelva Identidad. Si un empleado solo puede consultar su propio usuario, no podrá asignar nuevos integrantes desde la interfaz; los participantes ya asignados siguen apareciendo para menciones, como `Usuario #ID` cuando Identidad no revela su nombre.
- Las menciones se almacenan con IDs de usuarios asignados a la tarea. El envío de notificaciones por mención no está implementado.
- La vista previa de archivos usa URLs firmadas de duración limitada, generadas por Trabajo. Los adjuntos requieren respaldar el volumen Docker `trabajo_attachments` por separado de PostgreSQL.
- Esta entrega es una v1 de frontend para piloto, no una certificación de producción. Hay que probar el flujo en el servidor, en navegadores reales y con los tres programadores.
