"""Migration regressions, using the frozen 0001 schema and real SQL."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect, text
ROOT = Path(__file__).resolve().parents[1]
SECRET = 'x' * 64
HEAD = '0002_roles'
TABLES = ['users', 'departments', 'memberships', 'login_sessions', 'audit_events']


def run_command(url, *args, root=ROOT):
    return subprocess.run([sys.executable, *args], cwd=root, env={**os.environ, 'DATABASE_URL':url, 'JWT_SECRET':SECRET}, capture_output=True, text=True, timeout=40)


def run_migrate(url, check=False):
    return run_command(url, '-m', 'app.migrate', *(['--check'] if check else []))


def make_old_db(url, versioned=False, empty_version=False):
    r = run_command(url, '-m', 'alembic', 'upgrade', '0001_identidad')
    assert r.returncode == 0, r.stderr
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO departments (id,name,active) VALUES (1,'Comercio',true)"))
        c.execute(text("INSERT INTO users (id,name,email,password_hash,role,active,created_at) VALUES (1,'Admin Existente','admin@example.com','hash-original','SUPERADMIN',true,'2026-10-20 00:00:00')"))
        c.execute(text("INSERT INTO memberships (id,user_id,department_id) VALUES (1,1,1)"))
        c.execute(text("INSERT INTO login_sessions (token_hash,user_id,expires,revoked) VALUES ('original-session',1,'2030-01-01',false)"))
        c.execute(text("INSERT INTO audit_events (id,actor_id,action,target,created_at) VALUES (1,1,'login','user:1','2026-10-20 00:00:00')"))
        if not versioned:
            c.execute(text('DELETE FROM alembic_version' if empty_version else 'DROP TABLE alembic_version'))
    engine.dispose()


def snapshot(url):
    engine = create_engine(url)
    with engine.connect() as c:
        result = {}
        for name in TABLES:
            columns = [item['name'] for item in inspect(c).get_columns(name) if item['name'] != 'details']
            result[name] = c.execute(text(f'SELECT {",".join(columns)} FROM {name} ORDER BY 1')).all()
    engine.dispose()
    return result


def test_empty_database_and_repeat_are_consistent(tmp_path):
    url = f'sqlite:///{tmp_path}/empty.db'
    r = run_migrate(url); assert r.returncode == 0, r.stderr
    e = create_engine(url)
    with e.connect() as c:
        assert set(inspect(c).get_table_names()) == set(TABLES) | {'roles','alembic_version'}
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == HEAD
        assert c.scalar(text('SELECT count(*) FROM roles')) == 3
        assert any(f['name'] == 'fk_users_role_roles' for f in inspect(c).get_foreign_keys('users'))
        assert any(i['name'] == 'ix_users_role' for i in inspect(c).get_indexes('users'))
    assert run_migrate(url).returncode == 0
    r = run_command(url, '-m', 'alembic', 'check'); assert r.returncode == 0, r.stderr
    e.dispose()


@pytest.mark.parametrize('versioned,empty_version', [(False,False),(False,True),(True,False)])
def test_adoption_and_upgrade_preserve_all_records(tmp_path, versioned, empty_version):
    url = f'sqlite:///{tmp_path}/old.db'; make_old_db(url, versioned=versioned, empty_version=empty_version)
    before = snapshot(url)
    r = run_migrate(url); assert r.returncode == 0, r.stderr
    assert snapshot(url) == before
    assert run_migrate(url).returncode == 0


@pytest.mark.parametrize('versioned', [True,False])
def test_schema_drift_is_rejected_before_changes(tmp_path, versioned):
    url = f'sqlite:///{tmp_path}/drift.db'; make_old_db(url, versioned=versioned)
    e = create_engine(url)
    with e.begin() as c: c.execute(text('DROP INDEX ix_users_email'))
    r = run_migrate(url)
    assert r.returncode != 0 and 'no se marco' in r.stderr
    with e.connect() as c:
        assert 'roles' not in inspect(c).get_table_names()
        assert c.scalar(text('SELECT count(*) FROM users')) == 1
        if versioned: assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0001_identidad'
    e.dispose()


def test_unknown_prior_roles_abort_without_coercion(tmp_path):
    url = f'sqlite:///{tmp_path}/unknown_role.db'; make_old_db(url, versioned=True)
    e = create_engine(url)
    with e.begin() as c: c.execute(text("UPDATE users SET role='UNRECOGNIZED'"))
    r = run_migrate(url)
    assert r.returncode != 0 and 'desconocidos' in r.stderr
    with e.connect() as c:
        assert 'roles' not in inspect(c).get_table_names()
        assert c.scalar(text('SELECT role FROM users')) == 'UNRECOGNIZED'
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0001_identidad'
    e.dispose()


def test_unknown_revision_is_never_overwritten(tmp_path):
    url = f'sqlite:///{tmp_path}/revision.db'; make_old_db(url, versioned=True)
    e = create_engine(url)
    with e.begin() as c: c.execute(text("UPDATE alembic_version SET version_num='unexpected'"))
    assert run_migrate(url).returncode != 0
    with e.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == 'unexpected'
        assert 'roles' not in inspect(c).get_table_names()
    e.dispose()


def test_incomplete_schema_is_rejected(tmp_path):
    url = f'sqlite:///{tmp_path}/partial.db'; e = create_engine(url)
    with e.begin() as c: c.execute(text('CREATE TABLE users (id integer primary key)'))
    assert run_migrate(url).returncode != 0
    with e.connect() as c: assert set(inspect(c).get_table_names()) == {'users'}
    e.dispose()


def test_preflight_does_not_modify_schema_or_records(tmp_path):
    url = f'sqlite:///{tmp_path}/preflight.db'; make_old_db(url, versioned=True)
    before = snapshot(url)
    r = run_migrate(url, check=True); assert r.returncode == 0, r.stderr
    assert snapshot(url) == before
    e = create_engine(url)
    with e.connect() as c:
        assert 'roles' not in inspect(c).get_table_names()
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0001_identidad'
    e.dispose()


@pytest.mark.parametrize('missing', ['0001_identidad_inicial.py','0002_roles.py'])
def test_missing_revision_fails_before_database_connection(tmp_path, missing):
    isolated = tmp_path/'isolated'; isolated.mkdir()
    for folder in ['app','migrations']: shutil.copytree(ROOT/folder, isolated/folder)
    shutil.copyfile(ROOT/'alembic.ini',isolated/'alembic.ini')
    (isolated/'migrations'/'versions'/missing).unlink()
    for cache in isolated.rglob('__pycache__'): shutil.rmtree(cache)
    file = tmp_path/'must_not_exist.db'
    r = run_command(f'sqlite:///{file}', '-m','app.migrate',root=isolated)
    assert r.returncode != 0 and not file.exists()


def test_empty_version_only_is_initializable(tmp_path):
    url = f'sqlite:///{tmp_path}/only_version.db'; e = create_engine(url)
    with e.begin() as c: c.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY NOT NULL)'))
    r = run_migrate(url); assert r.returncode == 0, r.stderr
    e.dispose()


def test_destructive_downgrade_is_refused(tmp_path):
    url = f'sqlite:///{tmp_path}/downgrade.db'
    assert run_migrate(url).returncode == 0
    r = run_command(url,'-m','alembic','downgrade','0001_identidad')
    assert r.returncode != 0 and 'destructivo bloqueado' in r.stderr
