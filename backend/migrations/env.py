"""NOA Identity migrations. Never run automatically from an API worker."""
import os
from alembic import context
from app.main import Base
from app.migration_support import migration_engine

config = context.config
url = os.getenv('DATABASE_URL')
if not url:
    raise RuntimeError('DATABASE_URL es obligatorio para ejecutar Alembic')


def apply(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
        if connection.dialect.name == 'sqlite':
            violations = connection.exec_driver_sql('PRAGMA foreign_key_check').all()
            if violations:
                raise RuntimeError(f'Integridad referencial invalida: {violations!r}')


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True,
                      dialect_opts={'paramstyle': 'named'}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    external = config.attributes.get('connection')
    if external is not None:
        apply(external)
    else:
        engine = migration_engine(url)
        try:
            with engine.begin() as connection:
                apply(connection)
        finally:
            engine.dispose()
