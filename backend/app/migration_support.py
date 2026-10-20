"""Connection setup shared by the guarded migrator and Alembic's CLI."""
from sqlalchemy import create_engine, event, pool


def migration_engine(url):
    engine = create_engine(url, poolclass=pool.NullPool)
    if engine.dialect.name == 'sqlite':
        # Local tests: transactional DDL, with batch ALTER support. The migrator
        # checks foreign_key_check before committing; the application enables FK.
        @event.listens_for(engine, 'connect')
        def connect(dbapi_connection, _record):
            dbapi_connection.isolation_level = None
            dbapi_connection.execute('PRAGMA foreign_keys=OFF')

        @event.listens_for(engine, 'begin')
        def begin(connection):
            connection.exec_driver_sql('BEGIN')
    return engine
