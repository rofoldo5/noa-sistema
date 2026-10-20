# Validacion de NOA Trabajo MVP v0.1.0

## Ejecutado en el entorno de construccion

- `python -m pytest`: **15 passed, 1 skipped**.
- `python -m compileall -q app migrations tests`: correcto.
- YAML parse de `compose.yaml` y `compose.qa.yaml`: correcto.
- `alembic upgrade head` + `alembic check` sobre SQLite temporal: correcto; no detecta operaciones de migracion pendientes.
- El test de PostgreSQL se omitio porque no habia `NOA_TEST_POSTGRES_URL` ni Docker disponible en el entorno de construccion.

## Debe ejecutarse en el equipo del usuario

```bash
bash PROBAR_POSTGRES.sh
```

Este script crea PostgreSQL 17 temporal sin puertos ni volumenes persistentes y prueba la migracion Alembic y una escritura/lectura de tablas. No conecta a Identidad real. El paquete no afirma haber sido probado contra PostgreSQL real hasta que ese comando finalice con codigo 0.

## Advertencias/limites

- No se ha construido la imagen Docker en este entorno porque Docker no esta disponible aqui.
- No se ha desplegado el servicio en el host del usuario.
- Las pruebas de API usan un usuario simulado mediante dependency override; la validacion de tokens real ocurre llamando a Identidad en ejecucion, que se debe probar en el entorno local.
- La interfaz React/Trello no esta incluida en esta entrega.
