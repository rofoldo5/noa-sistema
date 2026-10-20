"""Role CRUD, scope, session invalidation and privilege escalation regression."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_identity import setup, login

PASSWORD = 'secure-password-123'


def admin(c):
    return login(c, 'admin@example.com', 'admin-password-1234')


def create_user(m, name='employee', role='EMPLEADO', active=True):
    with m.SessionLocal.begin() as db:
        u = m.User(name=name, email=f'{name}@example.com', password_hash=m.hasher.hash(PASSWORD), role=role, active=active)
        db.add(u)
        db.flush()
        return u.id


def create_role(c, headers, code='LECTOR', permissions=None):
    r = c.post('/admin/roles', headers=headers, json={'code': code, 'name': code.title(), 'permissions': permissions or []})
    assert r.status_code == 201, r.text
    return r.json()


def test_role_crud_and_audit(setup):
    m, c = setup; h = admin(c)
    assert len(c.get('/admin/roles', headers=h).json()) == 3
    assert len(c.get('/admin/permissions', headers=h).json()) == 3
    role = create_role(c, h)
    assert role['version'] == 1 and not role['is_system']
    assert c.get('/admin/roles/LECTOR', headers=h).json()['code'] == 'LECTOR'
    changed = c.patch('/admin/roles/LECTOR', headers=h, json={'version': 1, 'name': 'Consulta', 'description': 'Solo consulta'}).json()
    assert changed['version'] == 2
    assert c.patch('/admin/roles/LECTOR', headers=h, json={'version': 1, 'name': 'Viejo'}).status_code == 409
    assert c.delete('/admin/roles/LECTOR?version=1', headers=h).status_code == 409
    assert c.delete('/admin/roles/LECTOR?version=2', headers=h).status_code == 204
    assert c.get('/admin/roles/LECTOR', headers=h).status_code == 404
    events = c.get('/admin/audit', headers=h).json()
    assert {e['action'] for e in events} >= {'role_created', 'role_updated', 'role_deleted'}
    update = next(e for e in events if e['action'] == 'role_updated')
    assert update['details']['before']['name'] == 'Lector'
    assert update['details']['after']['name'] == 'Consulta'


@pytest.mark.parametrize('role', ['EMPLEADO', 'JEFE'])
def test_all_role_operations_are_admin_only(setup, role):
    m, c = setup; create_user(m, role=role)
    h = login(c, 'employee@example.com', PASSWORD)
    requests = [
        ('GET', '/admin/roles', None), ('GET', '/admin/roles/EMPLEADO', None),
        ('GET', '/admin/permissions', None),
        ('POST', '/admin/roles', {'code': 'EVIL', 'name': 'Evil'}),
        ('PATCH', '/admin/roles/EMPLEADO', {'version': 1, 'name': 'Cambio'}),
        ('DELETE', '/admin/roles/EMPLEADO?version=1', None),
    ]
    for method, path, body in requests:
        assert c.request(method, path, headers=h, json=body).status_code == 403, (method, path)
        assert c.request(method, path, json=body).status_code == 401, (method, path)


@pytest.mark.parametrize('code', ['SUPERADMIN', 'JEFE', 'EMPLEADO'])
def test_builtin_role_security_is_protected(setup, code):
    m, c = setup; h = admin(c)
    assert c.delete(f'/admin/roles/{code}?version=1', headers=h).status_code == 409
    assert c.patch(f'/admin/roles/{code}', headers=h, json={'version': 1, 'active': False}).status_code == 409
    assert c.patch(f'/admin/roles/{code}', headers=h, json={'version': 1, 'permissions': []}).status_code == 409
    assert c.patch(f'/admin/roles/{code}', headers=h, json={'version': 1, 'code': 'OTRO'}).status_code == 422
    assert c.patch(f'/admin/roles/{code}', headers=h, json={'version': 1, 'description': 'Texto descriptivo'}).status_code == 200


@pytest.mark.parametrize('body', [
    {'code': 'ab', 'name': 'No'}, {'code': 'minuscula', 'name': 'No'},
    {'code': 'GOOD', 'name': '  '}, {'code': 'GOOD', 'name': 'Ok', 'is_system': True},
    {'code': 'GOOD', 'name': 'Ok', 'permissions': ['*']},
    {'code': 'GOOD', 'name': 'Ok', 'permissions': ['roles.create']},
    {'code': 'GOOD', 'name': 'Ok', 'permissions': ['memberships.create.department']},
    {'code': 'GOOD', 'name': 'Ok', 'permissions': ['users.read.department', 'users.read.department']},
])
def test_invalid_role_inputs(setup, body):
    m, c = setup
    assert c.post('/admin/roles', headers=admin(c), json=body).status_code == 422


def test_no_duplicate_codes_or_names(setup):
    m, c = setup; h = admin(c)
    create_role(c, h)
    assert c.post('/admin/roles', headers=h, json={'code': 'LECTOR', 'name': 'Other'}).status_code == 409
    assert c.post('/admin/roles', headers=h, json={'code': 'OTHER', 'name': 'LECTOR'}).status_code == 409
    assert c.post('/admin/roles', headers=h, json={'code': 'SUPERADMIN', 'name': 'Other'}).status_code == 409


def test_custom_role_without_permissions_never_sees_global_users(setup):
    m, c = setup; h = admin(c)
    create_role(c, h)
    uid = create_user(m, role='LECTOR')
    create_user(m, name='other')
    user = login(c, 'employee@example.com', PASSWORD)
    assert [u['id'] for u in c.get('/users', headers=user).json()] == [uid]
    assert c.get('/users?pending=true', headers=user).status_code == 403
    assert c.patch('/admin/users/1', headers=user, json={'role': 'EMPLEADO'}).status_code == 403
    assert c.get('/admin/roles', headers=user).status_code == 403
    assert c.post('/admin/departments', headers=user, json={'name': 'No'}).status_code == 403
    assert c.get('/admin/audit', headers=user).status_code == 403


def test_custom_department_scope_and_cross_department_memberships(setup):
    m, c = setup; h = admin(c)
    create_role(c, h, permissions=['users.read.department', 'memberships.create.department'])
    uid = create_user(m, role='LECTOR')
    peer = create_user(m, name='peer'); other = create_user(m, name='other')
    d1 = c.post('/admin/departments', headers=h, json={'name': 'Comercio'}).json()['id']
    d2 = c.post('/admin/departments', headers=h, json={'name': 'Tesoreria'}).json()['id']
    for u, d in [(uid,d1), (peer,d1), (peer,d2), (other,d2)]:
        assert c.post('/admin/memberships', headers=h, json={'user_id': u, 'department_id': d}).status_code == 201
    member = login(c, 'employee@example.com', PASSWORD)
    result = c.get('/users', headers=member).json()
    assert {u['id'] for u in result} == {uid,peer}
    assert next(u for u in result if u['id'] == peer)['departments'] == [d1]
    assert c.post('/admin/memberships', headers=member, json={'user_id': uid, 'department_id': d2}).status_code == 403
    assert c.post('/admin/memberships', headers=member, json={'user_id': other, 'department_id': d1}).status_code == 201
    assert c.delete(f'/admin/memberships/{other}/{d1}', headers=member).status_code == 403


def test_role_assignment_revokes_old_session_and_cannot_delete_in_use(setup):
    m, c = setup; h = admin(c)
    create_role(c, h)
    uid = create_user(m)
    user = login(c, 'employee@example.com', PASSWORD)
    r = c.patch(f'/admin/users/{uid}', headers=h, json={'role': 'LECTOR'})
    assert r.status_code == 200 and r.json()['active'] is True
    assert c.get('/auth/me', headers=user).status_code == 401
    assert c.get('/admin/roles/LECTOR', headers=h).json()['assigned_users'] == 1
    assert c.delete('/admin/roles/LECTOR?version=1', headers=h).status_code == 409
    assert c.patch(f'/admin/users/{uid}', headers=h, json={'active': False}).status_code == 200
    assert c.delete('/admin/roles/LECTOR?version=1', headers=h).status_code == 409
    assert c.patch(f'/admin/users/{uid}', headers=h, json={'role': 'EMPLEADO'}).status_code == 200
    assert c.delete('/admin/roles/LECTOR?version=1', headers=h).status_code == 204


def test_permissions_and_role_suspension_revoke_sessions(setup):
    m, c = setup; h = admin(c)
    create_role(c, h)
    uid = create_user(m, role='LECTOR')
    user = login(c, 'employee@example.com', PASSWORD)
    assert c.patch('/admin/roles/LECTOR', headers=h, json={'version':1,'permissions':['users.read.department']}).status_code == 200
    assert c.get('/auth/me', headers=user).status_code == 401
    user2 = login(c, 'employee@example.com', PASSWORD)
    assert c.patch('/admin/roles/LECTOR', headers=h, json={'version':2,'active':False}).status_code == 200
    assert c.get('/auth/me', headers=user2).status_code == 401
    assert c.post('/auth/login',json={'email':'employee@example.com','password':PASSWORD}).status_code == 403
    assert c.patch(f'/admin/users/{uid}', headers=h, json={'role':'LECTOR'}).status_code == 422
    assert c.patch('/admin/roles/LECTOR', headers=h, json={'version':3,'active':True}).status_code == 200
    assert c.get('/auth/me', headers=user2).status_code == 401  # Cannot revive revoked tokens.
    login(c, 'employee@example.com', PASSWORD)


def test_person_cannot_select_privileged_role_on_registration(setup):
    m, c = setup
    assert c.post('/auth/register', json={'name':'Visitor','email':'visitor@example.com','password':PASSWORD,'role':'SUPERADMIN'}).status_code == 422


def test_no_admin_can_remove_own_access(setup):
    m, c = setup; h = admin(c)
    create_role(c, h)
    assert c.patch('/admin/users/1', headers=h, json={'role':'LECTOR'}).status_code == 409
    assert c.patch('/admin/users/1', headers=h, json={'active':False}).status_code == 409
    assert c.patch('/admin/users/1', headers=h, json={'role':'NOT_EXISTENT'}).status_code == 422


def test_role_foreign_key_is_real(setup):
    m, c = setup
    with pytest.raises(IntegrityError):
        with m.SessionLocal.begin() as db:
            db.add(m.User(name='Invalid',email='bad@example.com',password_hash='x',role='MISSING',active=True))
