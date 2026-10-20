"""Optional PostgreSQL 17 checks. Only a disposable database is accepted."""
import importlib
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from test_identity import login
from test_migrations import make_old_db, snapshot, run_migrate, run_command


@pytest.fixture
def postgres_url():
    value = os.getenv('NOA_TEST_POSTGRES_URL')
    if not value:
        pytest.skip('PostgreSQL no disponible; ejecutar PROBAR_POSTGRES.sh en Docker')
    base = make_url(value)
    if base.database != 'noa_roles_test' or base.get_backend_name() != 'postgresql':
        pytest.fail('Solo se admite la base desechable noa_roles_test, nunca Identidad real')
    schema = 'qa_' + uuid.uuid4().hex
    engine = create_engine(base)
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = base.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    try:
        yield isolated
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_postgres_upgrade_preserves_records_and_constraints(postgres_url):
    make_old_db(postgres_url, versioned=True)
    before = snapshot(postgres_url)
    r = run_migrate(postgres_url); assert r.returncode == 0, r.stderr
    assert snapshot(postgres_url) == before
    engine = create_engine(postgres_url)
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0002_roles'
        fk = inspect(c).get_foreign_keys('users')
        assert any(item['name'] == 'fk_users_role_roles' for item in fk)
    r = run_command(postgres_url, '-m','alembic','check'); assert r.returncode == 0, r.stderr
    assert run_migrate(postgres_url).returncode == 0
    engine.dispose()


def test_postgres_two_admins_cannot_demote_each_other(postgres_url, monkeypatch):
    r = run_migrate(postgres_url); assert r.returncode == 0, r.stderr
    monkeypatch.setenv('DATABASE_URL', postgres_url)
    monkeypatch.setenv('JWT_SECRET', 'p'*64)
    sys.modules.pop('app.main', None)
    m = importlib.import_module('app.main')
    m.hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    with m.SessionLocal.begin() as db:
        first = m.User(name='First', email='first@example.com', password_hash=m.hasher.hash('admin-password-1234'),role='SUPERADMIN',active=True)
        second = m.User(name='Second', email='second@example.com', password_hash=m.hasher.hash('admin-password-1234'),role='SUPERADMIN',active=True)
        db.add_all([first,second]); db.flush()
        ids = [first.id, second.id]
    with TestClient(m.app) as c:
        headers = [login(c, f'{who}@example.com','admin-password-1234') for who in ['first','second']]
        barrier = Barrier(2)
        def demote(index):
            barrier.wait(timeout=10)
            return c.patch(f'/admin/users/{ids[1-index]}',headers=headers[index],json={'role':'EMPLEADO'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(demote,[0,1]))
        assert outcomes.count(200) == 1, outcomes
        assert any(code in (401,403) for code in outcomes), outcomes
        with m.SessionLocal() as db:
            active = list(db.scalars(select(m.User).where(m.User.role=='SUPERADMIN',m.User.active.is_(True))))
            assert len(active) == 1
    m.engine.dispose()
