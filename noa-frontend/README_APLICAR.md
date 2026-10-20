# Aplicar NOA Frontend v1.0.1

**No reemplaces el directorio `sys/frontend` existente.** Esta entrega es independiente y se instala en `~/Documents/portf/sys/noa-frontend`.

## Cambios v1.0.1

Esta actualización visual añade el águila de NOA, favicon, paleta corporativa aprobada y tipografía Inter con escala base de 16 px. Mantiene las APIs y el esquema de datos.

## 1. Instalar o actualizar

Descomprime el ZIP en `~/Documents/portf/down`. Si `sys/noa-frontend` todavia no existe, instala la version completa:

```bash
cd ~/Documents/portf/down/NOA_FRONTEND_V1.0.1
bash INSTALAR.sh ~/Documents/portf/sys/noa-frontend
```

Si ya instalaste la v1 anterior, **no uses `INSTALAR.sh` sobre una carpeta existente**. Ejecuta el actualizador; respalda los archivos que reemplaza y conserva `compose.yaml`, `Dockerfile`, redes y configuracion del servicio:

```bash
cd ~/Documents/portf/down/NOA_FRONTEND_V1.0.1
bash ACTUALIZAR.sh ~/Documents/portf/sys/noa-frontend
```

## 2. Preparar la red API-only de Trabajo

Desde la nueva carpeta del frontend, ejecuta primero la comprobación:

```bash
bash PREPARAR_RED_TRABAJO.sh ~/Documents/portf/sys/trabajo --check
```

Si la comprobación es correcta, aplica la configuración (se crea respaldo de `compose.yaml`):

```bash
bash PREPARAR_RED_TRABAJO.sh ~/Documents/portf/sys/trabajo
```

El script solo agrega la red `trabajo_work_api` al servicio `work-api`. PostgreSQL continúa en `work_private`. No modifica datos ni migraciones.

Después crea la red reiniciando solo la API de Trabajo:

```bash
cd ~/Documents/portf/sys/trabajo
docker-compose config -q
docker-compose up -d work-api
docker-compose ps
curl -i --max-time 5 http://127.0.0.1:18082/health
```

La API de Identidad ya debe estar conectada a `backend_identity_api`, como se validó durante la instalación de NOA Trabajo.

## 3. Validar y levantar frontend

```bash
cd ~/Documents/portf/sys/noa-frontend
docker-compose config -q
docker-compose up -d --build
docker-compose ps
curl -i --max-time 5 http://127.0.0.1:18083/health
```

Espera `HTTP 200` de `/health`. Abre:

- UI: `http://127.0.0.1:18083`
- Swagger de Identidad: `http://127.0.0.1:18081/docs`
- Swagger de Trabajo: `http://127.0.0.1:18082/docs`

## 4. Primer uso

1. Inicia sesión con el SuperAdmin o un usuario activo de Identidad.
2. Crea el proyecto del bot empresarial, seleccionando el departamento configurado en `.env` de Trabajo (`WORK_DEPARTMENT_ID`).
3. Crea tareas, abre una tarjeta, añade secciones y checklists.
4. Publica un comentario; adjunta una imagen o video para comprobar la vista previa.
5. Crea/usa las tres cuentas del piloto y comprueba la visibilidad de integrantes y menciones.

Si el proyecto falla con `403`, verifica que el departamento seleccionado coincida con `WORK_DEPARTMENT_ID`. Si el frontend muestra error de red, revisa `docker-compose logs --tail=100 noa-frontend` y la conectividad desde Nginx hacia `identity-api` y `work-api`.

## 5. Seguridad y respaldo

- No compartas tokens de acceso ni contraseñas.
- No publiques el puerto `18083` directamente a Internet. El puerto se liga a `127.0.0.1` para el piloto local; para acceso remoto usa un reverse proxy con HTTPS y autenticación acorde a la política de la empresa.
- Nginx está conectado a redes API-only, no a las redes privadas de PostgreSQL.
- Los archivos se suben a `trabajo_attachments`; respalda ese volumen además del dump PostgreSQL.
- El Docker del host de desarrollo usa Snap y AppArmor bloquea `no-new-privileges:true` en este entorno. El contenedor frontend se ejecuta con usuario Nginx no privilegiado, filesystem read-only y `cap_drop: ALL`, pero no declara esa opción en Compose para evitar la denegación reproducida en este host. En un host Docker Engine compatible se puede reintroducir tras validar el perfil de seguridad.
