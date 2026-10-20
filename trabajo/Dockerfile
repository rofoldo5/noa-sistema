FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /data/attachments /tmp \
    && chown -R appuser:appuser /data/attachments /srv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN chmod -R a+rX /srv/app /srv/migrations \
    && chmod a+r /srv/alembic.ini \
    && chown -R appuser:appuser /data/attachments
USER appuser
RUN alembic show 0001_trabajo
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
