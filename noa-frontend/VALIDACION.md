# Validación — NOA Frontend v1.0.1

## Cambios realizados
- Se sustituyó la marca textual `N` por el símbolo de águila SVG en login, sidebar y pantalla de carga.
- Se añadió favicon SVG con el mismo símbolo.
- Se aplicó la paleta corporativa: `#0B2D5B`, `#2563EB`, `#D4AF37`, `#F3F4F6`, `#1F2937`, `#6B7280`.
- Se fijó una escala tipográfica más legible con Inter, base de 16 px y aumentos para tarjetas, formularios, checklists y comentarios.
- No se modificaron contratos API, endpoints ni esquema PostgreSQL.

## Estado de pruebas
- Revisión estática de cambios realizada.
- El build TypeScript/Vite no pudo completarse en este entorno: `npm ci` quedó bloqueado al intentar acceder al registro de paquetes, por lo que no se declara compilación validada.
- Ejecutar `docker-compose up -d --build` en el equipo de desarrollo y comprobar `/health` antes de dar por aplicada la actualización.

## Pruebas manuales sugeridas
1. Login y registro: logo y legibilidad.
2. Dashboard y sidebar: colores, textos y favicon.
3. Tablero Kanban: columnas y tarjetas.
4. Abrir una tarea: apuntes, secciones y checklist.
5. Comentarios, menciones y preview de adjuntos.
6. Comprobar escritorio y móvil.
