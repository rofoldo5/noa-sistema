# NOA

Sistema de gestion de proyectos y tareas.

## Modulos

- backend/: Identidad, autenticacion, usuarios, departamentos y roles.
- trabajo/: proyectos, tableros Kanban, tareas, checklists, comentarios y adjuntos.
- noa-frontend/: interfaz React y TypeScript.

## Arquitectura

Cada modulo backend mantiene su propia API, base de datos,
migraciones Alembic y configuracion de despliegue.

## Seguridad

No versionar secretos, archivos .env, respaldos ni datos operativos.
Consultar la documentacion de cada modulo para instalarlo.
