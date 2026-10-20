import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, create_engine, select, func, update, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./dev.db')
JWT_SECRET = os.getenv('JWT_SECRET', '')
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError('Configure JWT_SECRET con al menos 32 caracteres.')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10 if not DATABASE_URL.startswith('sqlite') else 5, max_overflow=20 if not DATABASE_URL.startswith('sqlite') else 10)
# SQLite is used only by the local tests; enforce its foreign keys too.
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_sqlite_foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
hasher = PasswordHasher()

class Base(DeclarativeBase): pass

class Department(Base):
    __tablename__ = 'departments'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Role(Base):
    __tablename__ = 'roles'
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(500), default='')
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), ForeignKey('roles.code', name='fk_users_role_roles', ondelete='RESTRICT'), default='EMPLEADO', index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Membership(Base):
    __tablename__ = 'memberships'
    __table_args__ = (UniqueConstraint('user_id', 'department_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), index=True)

class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

app = FastAPI(title='NOA - Identidad', version='0.1.3')
bearer_scheme = HTTPBearer(auto_error=False)

def db_session():
    with SessionLocal() as db:
        yield db
DB = Annotated[Session, Depends(db_session)]

# Only these departmental capabilities can be delegated to custom roles.
PermissionCode = Literal[
    'users.read.department',
    'memberships.create.department',
    'memberships.delete.department',
]
PERMISSION_CATALOG = {
    'users.read.department': 'Consultar integrantes de sus departamentos',
    'memberships.create.department': 'Asignar integrantes a sus departamentos',
    'memberships.delete.department': 'Retirar integrantes de sus departamentos',
}
SYSTEM_ROLE_CODES = frozenset({'SUPERADMIN', 'JEFE', 'EMPLEADO'})


def audit(db, actor, action, target, details=None):
    db.add(Audit(actor_id=actor, action=action, target=str(target)[:100], details=details))


def public_user(db, user, viewer=None):
    statement = select(Membership.department_id).where(Membership.user_id == user.id)
    # A department manager must not learn a colleague's other memberships.
    if viewer is not None and viewer.id != user.id and viewer.role != 'SUPERADMIN':
        own = select(Membership.department_id).where(Membership.user_id == viewer.id)
        statement = statement.where(Membership.department_id.in_(own))
    role = db.get(Role, user.role)
    out = {'id': user.id, 'name': user.name, 'email': user.email,
           'role': user.role, 'active': user.active,
           'departments': list(db.scalars(statement)),
           'role_name': role.name if role else user.role}
    if viewer is None or viewer.id == user.id or viewer.role == 'SUPERADMIN':
        out['permissions'] = (['*'] if user.role == 'SUPERADMIN' else list(role.permissions)) if role and role.active else []
    return out


def current_user(db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Se requiere iniciar sesion')
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=['HS256'], options={'require': ['exp', 'sub', 'jti']})
        record = db.get(LoginSession, hashlib.sha256(claims['jti'].encode()).hexdigest())
        if not record or record.revoked or record.user_id != int(claims['sub']):
            raise ValueError('sesion invalida')
        user = db.get(User, record.user_id)
        if not user or not user.active:
            raise ValueError('cuenta inactiva')
        role = db.get(Role, user.role)
        if not role or not role.active:
            raise ValueError('rol no disponible')
        return user
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        raise HTTPException(401, 'Sesion invalida, vencida o revocada')
Auth = Annotated[User, Depends(current_user)]


def superadmin(user):
    if user.role != 'SUPERADMIN':
        raise HTTPException(403, 'Solo el administrador global')


def security_admin(db, actor):
    """Serialize security mutations and recheck a possibly stale administrator.

    Lock order: the system role first, then users/other roles. This prevents two
    administrators from demoting each other concurrently and leaving no admin.
    PostgreSQL holds the lock until this request commits or rolls back.
    """
    superadmin(actor)
    root = db.scalar(select(Role).where(Role.code == 'SUPERADMIN').with_for_update().execution_options(populate_existing=True))
    db.refresh(actor)
    if not root or not root.active or not root.is_system or not actor.active or actor.role != 'SUPERADMIN':
        raise HTTPException(403, 'El acceso administrativo ya no esta disponible')


def has_permission(db, user, permission):
    if user.role == 'SUPERADMIN':
        return True
    role = db.get(Role, user.role)
    return bool(role and role.active and permission in role.permissions)


def can_manage(db, user, department_id, permission):
    if user.role == 'SUPERADMIN':
        return True
    if not has_permission(db, user, permission):
        return False
    return db.scalar(select(Membership.id).join(Department).where(
        Membership.user_id == user.id,
        Membership.department_id == department_id,
        Department.active.is_(True),
    )) is not None


def revoke_user_sessions(db, ids):
    db.execute(update(LoginSession).where(LoginSession.user_id.in_(ids), LoginSession.revoked.is_(False)).values(revoked=True))


class Register(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class Login(BaseModel):
    email: EmailStr
    password: str

class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)

class UserPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = Field(default=None, min_length=3, max_length=20)
    active: bool | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Indica al menos un campo; no se admiten valores nulos')
        return self


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    code: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z][A-Z0-9_]{2,19}$')
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default='', max_length=500)
    permissions: list[PermissionCode] = Field(default_factory=list, max_length=3)
    active: bool = True

    @model_validator(mode='after')
    def validate_permissions(self):
        validate_role_permissions(self.permissions)
        return self


class RolePatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[PermissionCode] | None = Field(default=None, max_length=3)
    active: bool | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        fields = self.model_fields_set - {'version'}
        if not fields or any(getattr(self, key) is None for key in fields):
            raise ValueError('Indica campos a modificar; no se admiten valores nulos')
        if self.permissions is not None:
            validate_role_permissions(self.permissions)
        return self


def validate_role_permissions(permissions):
    if len(set(permissions)) != len(permissions):
        raise ValueError('No se admiten permisos repetidos')
    if any(p.startswith('memberships.') for p in permissions) and 'users.read.department' not in permissions:
        raise ValueError('Para gestionar integrantes se requiere users.read.department')


class MemberIn(BaseModel):
    user_id: int
    department_id: int

@app.get('/')
def index():
    return FileResponse(Path(__file__).resolve().parent.parent / 'static' / 'index.html')

@app.get('/health')
def health(db: DB):
    db.execute(select(func.count()).select_from(User))
    return {'status': 'ok'}

@app.post('/auth/register', status_code=201)
def register(data: Register, db: DB):
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'El correo ya está registrado')
    user = User(name=data.name.strip(), email=email, password_hash=hasher.hash(data.password), role='EMPLEADO', active=False)
    db.add(user)
    db.flush()
    audit(db, user.id, 'registration_requested', f'user:{user.id}')
    db.commit()
    return {'message': 'Solicitud registrada; espera aprobación del administrador'}

@app.post('/auth/login')
def login(data: Login, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    try:
        valid = hasher.verify(user.password_hash if user else hasher.hash('invalid-password'), data.password)
    except (VerifyMismatchError, VerificationError):
        valid = False
    if not valid:
        raise HTTPException(401, 'Credenciales inválidas')
    if not user.active:
        raise HTTPException(403, 'Cuenta pendiente de aprobación o suspendida')
    role = db.get(Role, user.role)
    if not role or not role.active:
        raise HTTPException(403, 'El rol de la cuenta no esta disponible; contacta al administrador')
    nonce = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    db.add(LoginSession(token_hash=hashlib.sha256(nonce.encode()).hexdigest(), user_id=user.id, expires=expires))
    audit(db, user.id, 'login', f'user:{user.id}')
    db.commit()
    return {'access_token': jwt.encode({'sub': str(user.id), 'jti': nonce, 'exp': expires}, JWT_SECRET, algorithm='HS256'), 'token_type': 'bearer', 'user': public_user(db, user)}

@app.post('/auth/logout')
def logout(user: Auth, db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None):
    claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=['HS256'])
    record = db.get(LoginSession, hashlib.sha256(claims['jti'].encode()).hexdigest())
    record.revoked = True
    audit(db, user.id, 'logout', f'user:{user.id}')
    db.commit()
    return {'message': 'Sesion cerrada'}

@app.get('/auth/me')
def me(user: Auth, db: DB): return public_user(db, user)

@app.get('/departments')
def departments(user: Auth, db: DB):
    stmt = select(Department).where(Department.active.is_(True))
    if user.role != 'SUPERADMIN':
        stmt = stmt.join(Membership, Membership.department_id == Department.id).where(Membership.user_id == user.id)
    return [{'id': d.id, 'name': d.name} for d in db.scalars(stmt.order_by(Department.name))]

@app.post('/admin/departments', status_code=201)
def create_department(data: DepartmentIn, user: Auth, db: DB):
    superadmin(user)
    if db.scalar(select(Department.id).where(Department.name == data.name.strip())):
        raise HTTPException(409, 'Departamento existente')
    d = Department(name=data.name.strip())
    db.add(d); db.flush()
    audit(db, user.id, 'department_created', f'department:{d.id}')
    db.commit()
    return {'id': d.id, 'name': d.name}

@app.get('/users')
def users(user: Auth, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), pending: bool = False):
    if pending and user.role != 'SUPERADMIN':
        raise HTTPException(403, 'Solo el administrador puede ver solicitudes pendientes')
    if not has_permission(db, user, 'users.read.department'):
        return [public_user(db, user)] if offset == 0 else []
    stmt = select(User)
    if user.role != 'SUPERADMIN':
        dept_ids = select(Membership.department_id).join(Department).where(
            Membership.user_id == user.id, Department.active.is_(True))
        stmt = stmt.where(User.id.in_(select(Membership.user_id).where(Membership.department_id.in_(dept_ids))))
    if pending:
        stmt = stmt.where(User.active.is_(False))
    return [public_user(db, u, viewer=user) for u in db.scalars(stmt.order_by(User.id).limit(limit).offset(offset))]


@app.patch('/admin/users/{user_id}')
def update_user(user_id: int, data: UserPatch, admin: Auth, db: DB):
    security_admin(db, admin)
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, 'Usuario inexistente')
    db.refresh(target)
    if data.role is not None:
        new_role = db.get(Role, data.role)
        if not new_role or not new_role.active:
            raise HTTPException(422, 'El rol no existe o esta inactivo')
    if target.id == admin.id and (data.active is False or (data.role is not None and data.role != 'SUPERADMIN')):
        raise HTTPException(409, 'No puedes quitarte acceso administrativo a ti mismo')
    losing_admin = data.active is False or (data.role is not None and data.role != 'SUPERADMIN')
    if target.role == 'SUPERADMIN' and target.active and losing_admin:
        count = db.scalar(select(func.count()).select_from(User).where(User.role == 'SUPERADMIN', User.active.is_(True)))
        if count <= 1:
            raise HTTPException(409, 'Debe permanecer al menos un SuperAdmin activo')
    before = {'role': target.role, 'active': target.active}
    if data.name is not None:
        target.name = data.name
    if data.role is not None:
        target.role = data.role
    if data.active is not None:
        target.active = data.active
    after = {'role': target.role, 'active': target.active}
    if before['role'] != after['role'] or (before['active'] and not after['active']):
        revoke_user_sessions(db, [target.id])
    audit(db, admin.id, 'user_updated', f'user:{target.id}', {'before': before, 'after': after})
    db.commit()
    return public_user(db, target)


@app.post('/admin/memberships', status_code=201)
def add_membership(data: MemberIn, actor: Auth, db: DB):
    if not can_manage(db, actor, data.department_id, 'memberships.create.department'): raise HTTPException(403, 'Sin permisos para este departamento')
    if not db.get(User, data.user_id) or not db.get(Department, data.department_id):
        raise HTTPException(404, 'Usuario o departamento inexistente')
    if db.scalar(select(Membership.id).where(Membership.user_id == data.user_id, Membership.department_id == data.department_id)):
        raise HTTPException(409, 'Ya pertenece al departamento')
    db.add(Membership(user_id=data.user_id, department_id=data.department_id))
    audit(db, actor.id, 'membership_added', f'user:{data.user_id}/department:{data.department_id}')
    db.commit()
    return {'message': 'Miembro asignado'}

@app.delete('/admin/memberships/{user_id}/{department_id}')
def remove_membership(user_id: int, department_id: int, actor: Auth, db: DB):
    if not can_manage(db, actor, department_id, 'memberships.delete.department'): raise HTTPException(403, 'Sin permisos para este departamento')
    membership = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.department_id == department_id))
    if not membership: raise HTTPException(404, 'Membresía inexistente')
    db.delete(membership)
    audit(db, actor.id, 'membership_removed', f'user:{user_id}/department:{department_id}')
    db.commit()
    return {'message': 'Membresía eliminada'}

@app.get('/admin/audit')
def audit_events(user: Auth, db: DB, limit: int = Query(50, ge=1, le=100)):
    superadmin(user)
    return [{'id': a.id, 'actor_id': a.actor_id, 'action': a.action, 'target': a.target, 'details': a.details, 'created_at': a.created_at.isoformat()} for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limit))]


def role_output(db, role, assigned_count=None):
    if assigned_count is None:
        assigned_count = db.scalar(select(func.count()).select_from(User).where(User.role == role.code))
    return {'code': role.code, 'name': role.name, 'description': role.description,
            'permissions': list(role.permissions), 'is_system': role.is_system,
            'active': role.active, 'version': role.version, 'assigned_users': assigned_count,
            'created_at': role.created_at.isoformat()}


def commit_security_change(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Conflicto de integridad; actualiza los datos e intentalo de nuevo')


@app.get('/admin/permissions', tags=['Roles'])
def permissions_catalog(actor: Auth):
    superadmin(actor)
    return [{'code': code, 'description': label, 'scope': 'DEPARTMENT'} for code, label in PERMISSION_CATALOG.items()]


@app.get('/admin/roles', tags=['Roles'])
def roles_list(actor: Auth, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), active: bool | None = None):
    superadmin(actor)
    stmt = select(Role, func.count(User.id)).outerjoin(User, User.role == Role.code).group_by(Role.code)
    if active is not None:
        stmt = stmt.where(Role.active == active)
    return [role_output(db, role, count) for role, count in db.execute(stmt.order_by(Role.code).limit(limit).offset(offset))]


@app.get('/admin/roles/{code}', tags=['Roles'])
def role_detail(code: str, actor: Auth, db: DB):
    superadmin(actor)
    role = db.get(Role, code)
    if not role:
        raise HTTPException(404, 'Rol inexistente')
    return role_output(db, role)


@app.post('/admin/roles', status_code=201, tags=['Roles'])
def role_create(data: RoleCreate, actor: Auth, db: DB):
    security_admin(db, actor)
    if data.code in SYSTEM_ROLE_CODES or db.get(Role, data.code):
        raise HTTPException(409, 'El codigo ya existe o esta reservado')
    if db.scalar(select(Role.code).where(func.lower(Role.name) == data.name.lower())):
        raise HTTPException(409, 'Ya existe un rol con ese nombre')
    role = Role(**data.model_dump(), is_system=False)
    db.add(role)
    db.flush()
    audit(db, actor.id, 'role_created', f'role:{role.code}', {'after': role_output(db, role, 0)})
    commit_security_change(db)
    return role_output(db, role, 0)


@app.patch('/admin/roles/{code}', tags=['Roles'])
def role_update(code: str, data: RolePatch, actor: Auth, db: DB):
    security_admin(db, actor)
    role = db.get(Role, code)
    if not role:
        raise HTTPException(404, 'Rol inexistente')
    if data.version != role.version:
        raise HTTPException(409, 'El rol cambio; vuelve a consultarlo antes de guardar')
    changes = data.model_dump(exclude_unset=True, exclude={'version'})
    if role.is_system and ({'permissions', 'active'} & changes.keys()):
        raise HTTPException(409, 'Los permisos y el estado de los roles del sistema estan protegidos')
    if data.name is not None and db.scalar(select(Role.code).where(Role.code != code, func.lower(Role.name) == data.name.lower())):
        raise HTTPException(409, 'Ya existe un rol con ese nombre')
    before = role_output(db, role)
    for field, value in changes.items():
        setattr(role, field, value)
    role.version += 1
    if before['permissions'] != role.permissions or (before['active'] and not role.active):
        revoke_user_sessions(db, select(User.id).where(User.role == code))
    after = role_output(db, role, before['assigned_users'])
    audit(db, actor.id, 'role_updated', f'role:{code}', {'before': before, 'after': after})
    commit_security_change(db)
    return after


@app.delete('/admin/roles/{code}', status_code=204, tags=['Roles'])
def role_delete(code: str, actor: Auth, db: DB, version: int = Query(ge=1)):
    security_admin(db, actor)
    role = db.get(Role, code)
    if not role:
        raise HTTPException(404, 'Rol inexistente')
    if role.is_system or code in SYSTEM_ROLE_CODES:
        raise HTTPException(409, 'No se puede eliminar un rol del sistema')
    if version != role.version:
        raise HTTPException(409, 'El rol cambio; vuelve a consultarlo antes de eliminar')
    before = role_output(db, role)
    if before['assigned_users']:
        raise HTTPException(409, 'El rol tiene usuarios asignados, incluso inactivos; reasignalos primero')
    audit(db, actor.id, 'role_deleted', f'role:{code}', {'before': before})
    db.delete(role)
    commit_security_change(db)
    return Response(status_code=204)
