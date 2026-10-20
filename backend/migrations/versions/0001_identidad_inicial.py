"""Esquema inicial del modulo Identidad, compatible con v0.1.0.

Revision ID: 0001_identidad
Revises:

Las definiciones replican el modelo SQLAlchemy publicado en v0.1.0.
No realizar un upgrade directo sobre tablas existentes: usar `python -m app.migrate`.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_identidad"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.UniqueConstraint("user_id", "department_id"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_department_id", "memberships", ["department_id"])
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError(
        "El downgrade inicial eliminaria todas las tablas de Identidad. "
        "Se ha deshabilitado para proteger los datos; recuperar un respaldo verificado."
    )
