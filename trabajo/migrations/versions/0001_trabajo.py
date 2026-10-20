"""Esquema inicial del MVP Kanban de NOA Trabajo."""
from alembic import op
import sqlalchemy as sa

revision = "0001_trabajo"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("department_id", "name", name="uq_projects_department_name"),
        sa.CheckConstraint("status IN ('ACTIVE','COMPLETED','ARCHIVED')", name="ck_projects_status"),
    )
    op.create_index("ix_projects_department_id", "projects", ["department_id"])
    op.create_index("ix_projects_department_status", "projects", ["department_id", "status"])

    op.create_table(
        "boards",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("board_type", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_boards_project_id_projects", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "name", name="uq_boards_project_name"),
    )
    op.create_index("ix_boards_project_id", "boards", ["project_id"])

    op.create_table(
        "board_columns",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("board_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("status_key", sa.String(length=30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], name="fk_board_columns_board_id_boards", ondelete="CASCADE"),
        sa.UniqueConstraint("board_id", "name", name="uq_board_columns_board_name"),
        sa.UniqueConstraint("board_id", "position", name="uq_board_columns_board_position"),
        sa.CheckConstraint("position >= 0", name="ck_board_columns_position"),
    )
    op.create_index("ix_board_columns_board_id", "board_columns", ["board_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("board_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("column_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], name="fk_tasks_board_id_boards", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["column_id"], ["board_columns.id"], name="fk_tasks_column_id_board_columns", ondelete="RESTRICT"),
        sa.CheckConstraint("due_date IS NULL OR due_date >= start_date", name="ck_tasks_due_after_start"),
        sa.CheckConstraint("position >= 0", name="ck_tasks_position"),
    )
    op.create_index("ix_tasks_board_id", "tasks", ["board_id"])
    op.create_index("ix_tasks_column_id", "tasks", ["column_id"])
    op.create_index("ix_tasks_column_position", "tasks", ["column_id", "position"])
    op.create_index("ix_tasks_board_updated", "tasks", ["board_id", "updated_at"])

    op.create_table(
        "task_sections",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_sections_task_id_tasks", ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "position", name="uq_task_sections_task_position"),
        sa.CheckConstraint("position >= 0", name="ck_task_sections_position"),
    )
    op.create_index("ix_task_sections_task_id", "task_sections", ["task_id"])

    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("section_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["task_sections.id"], name="fk_checklist_items_section_id_task_sections", ondelete="CASCADE"),
        sa.CheckConstraint("position >= 0", name="ck_checklist_items_position"),
    )
    op.create_index("ix_checklist_items_section_id", "checklist_items", ["section_id"])
    op.create_index("ix_checklist_items_section_position", "checklist_items", ["section_id", "position"])

    op.create_table(
        "task_members",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("member_role", sa.String(length=20), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_members_task_id_tasks", ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_members_task_user"),
        sa.CheckConstraint("member_role IN ('RESPONSIBLE','COLLABORATOR')", name="ck_task_members_role"),
    )
    op.create_index("ix_task_members_task_id", "task_members", ["task_id"])
    op.create_index("uq_task_members_responsible", "task_members", ["task_id"], unique=True,
                    postgresql_where=sa.text("member_role = 'RESPONSIBLE'"), sqlite_where=sa.text("member_role = 'RESPONSIBLE'"))

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_comments_task_id_tasks", ondelete="CASCADE"),
    )
    op.create_index("ix_comments_task_id", "comments", ["task_id"])
    op.create_index("ix_comments_task_created", "comments", ["task_id", "created_at"])

    op.create_table(
        "comment_mentions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("comment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("mentioned_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], name="fk_comment_mentions_comment_id_comments", ondelete="CASCADE"),
        sa.UniqueConstraint("comment_id", "mentioned_user_id", name="uq_comment_mentions_comment_user"),
    )
    op.create_index("ix_comment_mentions_comment_id", "comment_mentions", ["comment_id"])

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("comment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], name="fk_attachments_comment_id_comments", ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachments_size_positive"),
        sa.CheckConstraint("media_type LIKE 'image/%' OR media_type LIKE 'video/%'", name="ck_attachments_media_type"),
    )
    op.create_index("ix_attachments_comment_id", "attachments", ["comment_id"])
    op.create_index("ix_attachments_comment_created", "attachments", ["comment_id", "created_at"])

    op.create_table(
        "task_activity",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_activity_task_id_tasks", ondelete="CASCADE"),
    )
    op.create_index("ix_task_activity_task_id", "task_activity", ["task_id"])
    op.create_index("ix_task_activity_task_created", "task_activity", ["task_id", "created_at"])


def downgrade():
    raise RuntimeError("Downgrade destructivo bloqueado. Para revertir Trabajo, preparar respaldo y una migracion de recuperacion revisada.")
