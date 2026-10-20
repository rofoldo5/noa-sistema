"""Guarded Alembic upgrade. Usage: python -m app.migrate [--check]."""
import argparse
import os
from pathlib import Path
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import inspect, text
from app.main import Base
from app.legacy_identity_schema import Base as LegacyBase
from app.migration_support import migration_engine

BASELINE_REVISION = '0001_identidad'
HEAD_REVISION = '0002_roles'


def alembic_config():
    return Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini'))


def verify_revision_files(config):
    try:
        scripts = ScriptDirectory.from_config(config)
        scripts.get_revision(BASELINE_REVISION)
    except (CommandError, OSError) as exc:
        raise RuntimeError('No se puede leer la revision 0001_identidad. Revisar archivos y permisos antes de migrar.') from exc
    try:
        scripts.get_revision(HEAD_REVISION)
        if scripts.get_heads() != [HEAD_REVISION]:
            raise RuntimeError('El historial no corresponde a esta entrega; no se migrara automaticamente.')
    except (CommandError, OSError) as exc:
        raise RuntimeError('No se puede leer la revision 0002_roles. Revisar archivos y permisos antes de migrar.') from exc
    return scripts


def verify_schema(connection, metadata):
    diffs = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), metadata)
    if diffs:
        raise RuntimeError(
            'La estructura real no coincide con su revision; no se marco ni actualizo la base. '
            f'Revisar las diferencias: {diffs!r}'
        )


def migrate(check_only=False):
    url = os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('DATABASE_URL es obligatorio: no se migrara una base por defecto')
    config = alembic_config()
    scripts = verify_revision_files(config)  # No DB connection before this point.
    engine = migration_engine(url)
    try:
        with engine.begin() as connection:
            if connection.dialect.name == 'postgresql':
                locked = connection.scalar(text('SELECT pg_try_advisory_xact_lock(78621, 1001)'))
                if not locked:
                    raise RuntimeError('Ya hay una migracion de Identidad en curso. Espera y vuelve a verificar.')
            tables = set(inspect(connection).get_table_names())
            managed = tables - {'alembic_version'}
            versions = list(connection.scalars(text('SELECT version_num FROM alembic_version'))) if 'alembic_version' in tables else []
            if versions:
                if len(versions) != 1 or versions[0] not in (BASELINE_REVISION, HEAD_REVISION):
                    raise RuntimeError(f'Revision registrada no admitida: {versions!r}; no se sustituira.')
                scripts.get_revision(versions[0])
                verify_schema(connection, LegacyBase.metadata if versions[0] == BASELINE_REVISION else Base.metadata)
                action = 'upgrade'
            elif not managed:
                action = 'create'
            else:
                if managed != set(LegacyBase.metadata.tables):
                    raise RuntimeError('Esquema incompleto o con tablas inesperadas; no se marco la migracion.')
                verify_schema(connection, LegacyBase.metadata)
                action = 'adopt'
            if check_only:
                print(f'OK: esquema comprobado; accion prevista={action}, destino={HEAD_REVISION}. No se modificaron tablas.')
                return
            config.attributes['connection'] = connection
            if action == 'adopt':
                command.stamp(config, BASELINE_REVISION)
            command.upgrade(config, HEAD_REVISION)
            verify_schema(connection, Base.metadata)
        # Message emitted only after commit succeeded.
        print(f'OK: Identidad en {HEAD_REVISION}; esquema verificado y roles inicializados')
    finally:
        engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validar sin aplicar migraciones')
    migrate(parser.parse_args().check)
