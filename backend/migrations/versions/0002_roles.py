"""Catalogo de roles globales; conserva usuarios y roles de 0001_identidad.

No implementa roles distintos por departamento ni servicios de Trabajo.
La configuracion inicial se congela aqui: no importar defaults de la aplicacion.
"""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = '0002_roles'
down_revision = '0001_identidad'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if op.get_context().as_sql:
        raise RuntimeError('Esta migracion requiere validar los datos: usar python -m app.migrate')
    unknown = connection.execute(sa.text(
        "SELECT DISTINCT role FROM users WHERE role NOT IN ('SUPERADMIN', 'JEFE', 'EMPLEADO') OR role IS NULL"
    )).scalars().all()
    if unknown:
        raise RuntimeError(f'Existen roles previos desconocidos: {unknown!r}. No se reasignaran automaticamente.')
    if connection.dialect.name == 'postgresql':
        connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    roles = op.create_table(
        'roles',
        sa.Column('code', sa.String(20), primary_key=True, nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('name'),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(roles, [
        {'code': 'SUPERADMIN', 'name': 'SuperAdmin', 'description': 'Administracion global de Identidad',
         'permissions': [], 'is_system': True, 'active': True, 'version': 1, 'created_at': now},
        {'code': 'JEFE', 'name': 'Jefe', 'description': 'Consulta y gestion de integrantes de sus departamentos',
         'permissions': ['users.read.department', 'memberships.create.department', 'memberships.delete.department'],
         'is_system': True, 'active': True, 'version': 1, 'created_at': now},
        {'code': 'EMPLEADO', 'name': 'Empleado', 'description': 'Acceso personal y consulta de sus departamentos',
         'permissions': [], 'is_system': True, 'active': True, 'version': 1, 'created_at': now},
    ])
    with op.batch_alter_table('users') as batch:
        batch.create_foreign_key('fk_users_role_roles', 'roles', ['role'], ['code'], ondelete='RESTRICT')
        batch.create_index('ix_users_role', ['role'], unique=False)
    op.add_column('audit_events', sa.Column('details', sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError(
        'Downgrade destructivo bloqueado: puede haber roles asignados y auditoria nueva. '
        'Planificar la reversion con respaldo, sin eliminar tablas automaticamente.'
    )
