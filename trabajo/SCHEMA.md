# Esquema inicial de NOA Trabajo

La revision Alembic `0001_trabajo` crea las tablas de abajo. IDs de tablas propias son UUID. Los IDs `*_user_id` y `department_id` son IDs externos de Identidad (enteros), sin foreign keys entre motores.

| Tabla | Responsabilidad | Relacion principal |
|---|---|---|
| `projects` | Proyecto y departamento propietario | Tiene muchos `boards` |
| `boards` | Tablero Kanban de un proyecto | Pertenece a `projects`; tiene columnas y tareas |
| `board_columns` | Estados/columnas ordenadas del tablero | Pertenece a `boards`; tareas referencian una columna |
| `tasks` | Tarjeta, titulo, apuntes generales, inicio y fin opcional | Pertenece a `boards` y `board_columns` |
| `task_sections` | Apuntes agrupados como Frontend, Backend, QA | Pertenece a `tasks`; tiene checklist |
| `checklist_items` | Elementos marcables por seccion | Pertenece a `task_sections` |
| `task_members` | Responsable unico y colaboradores | Pertenece a `tasks`; guarda ID externo de usuario |
| `comments` | Conversacion de la tarea | Pertenece a `tasks`; tiene menciones y adjuntos |
| `comment_mentions` | Menciones `@` vinculadas a usuario | Pertenece a `comments`; guarda ID externo de usuario |
| `attachments` | Metadatos de imagen/video y clave de almacenamiento | Pertenece a `comments`; bytes en volumen aparte |
| `task_activity` | Historial cronologico de acciones | Pertenece a `tasks` |
| `alembic_version` | Version del esquema aplicado | Administrada por Alembic |

## Restricciones importantes

- `tasks.due_date` puede ser `NULL`; si tiene valor, no puede ser anterior a `start_date`.
- Solo puede existir un integrante con rol `RESPONSIBLE` por tarea; los demas son `COLLABORATOR`.
- No se puede mover una tarea a una columna de otro tablero.
- Las menciones solo se crean para usuarios que ya participan en la tarea.
- Los adjuntos solo admiten firmas de archivo reconocidas para imagenes/video y tienen limite configurable (100 MiB por defecto).
- Las columnas iniciales son Pendiente, En proceso y Finalizado.
- Las tablas propias usan FK y `ON DELETE CASCADE` para hijos de proyecto/tarea/comentario; no hay FK entre motores.

## Almacenamiento de medios

`attachments` conserva nombre, MIME detectado, tamaño, SHA-256 y `storage_key` aleatorio. El contenido vive en el volumen Docker `trabajo_attachments`, separado del volumen PostgreSQL `trabajo_pgdata`. La API devuelve URLs firmadas por 10 minutos para preview inline. El volumen de medios requiere respaldo independiente.
