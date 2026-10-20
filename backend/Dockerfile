FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY static ./static
# COPY conserva permisos de subdirectorios: un umask 077 puede impedir su lectura.
# Solo codigo de migraciones. No se modifican secretos, volumenes ni datos.
RUN chmod -R a+rX /srv/app /srv/migrations /srv/static \
    && chmod a+r /srv/alembic.ini \
    && useradd -u 10001 -m appuser
USER appuser
# Sin conexion a PostgreSQL: falla el build si falta o no se puede leer la revision.
RUN alembic show 0001_identidad && alembic show 0002_roles
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
