import os
import tempfile
import importlib
import sys
import pytest
from argon2 import PasswordHasher
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(tmp_path/'testing.db'))
    monkeypatch.setenv('JWT_SECRET', 't'*64)
    sys.modules.pop('app.main', None)
    m = importlib.import_module('app.main')
    # Cheaper hashing ONLY in tests; production defaults are unchanged.
    m.hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    result = subprocess.run([sys.executable, '-m', 'app.migrate'], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    with m.SessionLocal() as db:
        db.add(m.User(name='Admin', email='admin@example.com', password_hash=m.hasher.hash('admin-password-1234'), role='SUPERADMIN', active=True))
        db.commit()
    with TestClient(m.app) as client: yield m,client
    m.engine.dispose()

def login(client, email, password):
    x=client.post('/auth/login',json={'email':email,'password':password})
    assert x.status_code==200,x.text
    return {'Authorization':'Bearer '+x.json()['access_token']}

def test_registration_approval_and_department_visibility(setup):
    m,c=setup
    admin=login(c,'admin@example.com','admin-password-1234')
    for email in ('ana@example.com','bea@example.com'):
        assert c.post('/auth/register',json={'name':email[:3],'email':email,'password':'secure-password-123'}).status_code==201
    assert c.post('/auth/login',json={'email':'ana@example.com','password':'secure-password-123'}).status_code==403
    d1=c.post('/admin/departments',headers=admin,json={'name':'Tesorería'}).json()['id']
    d2=c.post('/admin/departments',headers=admin,json={'name':'Comercio'}).json()['id']
    users=c.get('/users',headers=admin).json()
    ana=next(x['id'] for x in users if x['email']=='ana@example.com')
    bea=next(x['id'] for x in users if x['email']=='bea@example.com')
    for uid in (ana,bea):
        assert c.patch(f'/admin/users/{uid}',headers=admin,json={'active':True}).status_code==200
    assert c.post('/admin/memberships',headers=admin,json={'user_id':ana,'department_id':d1}).status_code==201
    assert c.post('/admin/memberships',headers=admin,json={'user_id':bea,'department_id':d2}).status_code==201
    employee=login(c,'ana@example.com','secure-password-123')
    assert [d['name'] for d in c.get('/departments',headers=employee).json()]==['Tesorería']
    assert len(c.get('/users',headers=employee).json())==1
    assert c.post('/admin/departments',headers=employee,json={'name':'Finanzas'}).status_code==403
    assert c.patch(f'/admin/users/{bea}',headers=employee,json={'role':'SUPERADMIN'}).status_code==403
    assert c.post('/admin/memberships',headers=employee,json={'user_id':ana,'department_id':d2}).status_code==403
    assert c.get('/admin/audit',headers=employee).status_code==403
    assert len(c.get('/admin/audit',headers=admin).json())>=5

def test_revocation_and_role_demotion(setup):
    m,c=setup
    admin=login(c,'admin@example.com','admin-password-1234')
    assert c.patch('/admin/users/1',headers=admin,json={'active':False}).status_code==409
    assert c.patch('/admin/users/1',headers=admin,json={'role':'EMPLEADO'}).status_code==409
    assert c.post('/auth/logout',headers=admin).status_code==200
    assert c.get('/auth/me',headers=admin).status_code==401
    assert c.get('/auth/me').status_code==401
