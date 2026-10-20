# Gestor de Tareas — Módulo Identidad v0.1.0

Primera entrega ejecutable (no es aún el sistema Kanban/Scrum completo).

## Requisitos
Docker Engine + Docker Compose v2. No requiere acceso público a PostgreSQL.

## Instalación local

```bash
cp .env.example .env
python3 - <<'PY'
import secrets
p='.env'
with open(p,'w') as f:
    f.write('POSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\n')
    f.write('JWT_SECRET='+secrets.token_urlsafe(48)+'\n')
PY
chmod 600 .env
docker compose up -d --build
# Ejecutar una única vez para crear tablas y primer SuperAdmin:
docker compose exec api python -m app.bootstrap
```

Abrir http://127.0.0.1:18081 (aplicación sencilla) o http://127.0.0.1:18081/docs (Swagger).

En Docker remoto, acceder por túnel SSH, por ejemplo: `ssh -L 18081:127.0.0.1:18081 usuario@servidor`. No publicar esta versión en internet sin HTTPS, reverse proxy y controles adicionales.

### Funciones implementadas
- Registro pendiente de aprobación, login y logout con token JWT y sesión revocable.
- Argon2 para contraseñas; no hay claves prefijadas.
- Roles SUPERADMIN, JEFE, EMPLEADO, con membresías por departamento.
- Listado acotado por permisos, aprobaciones, asignaciones, auditoría básica.
- Interfaz web de login, autorregistro y acciones administrativas iniciales.
- Base PostgreSQL/volumen propios de Identidad.

### Límites actuales (antes de producción)
- CRUD administrativo todavía parcial; no se implementan eliminación/desactivación de departamentos, restablecimiento de contraseñas ni gestión completa de permisos por acción.
- No hay segundo factor (MFA), recuperación de contraseña, rate limiting ni middleware anti-fuerza-bruta; es un piloto local, no apto aún para publicación externa.
- Las sesiones JWT expiran a las 8 h. La suspensión impide usar sesiones activas en nuevas solicitudes; las sesiones se mantienen para auditoría.
- La creación inicial de tablas (`create_all`) sirve para el piloto: en producción se sustituye por migraciones Alembic versionadas.
- La auditoría no es inmutable ni centralizada todavía. Debe fortalecerse para producción.
- No se han realizado pruebas de carga de 150 concurrentes ni restauración de respaldos.
- La protección del rol JEFE restringe cambios a membresías por departamento; políticas de tareas se implementarán en sus futuras APIs.

### Pruebas
```bash
JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))') pytest -q
```
Estas pruebas pueden ejecutarse en un entorno Python local con dependencias instaladas; usan SQLite solo para testing, producción utiliza PostgreSQL.
