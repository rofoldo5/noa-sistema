from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("department_id", "name", name="uq_projects_department_name"),
        CheckConstraint("status IN ('ACTIVE','COMPLETED','ARCHIVED')", name="ck_projects_status"),
        Index("ix_projects_department_status", "department_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # ID externo de Identidad; sin FK entre bases.
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_boards_project_name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Tablero principal")
    board_type: Mapped[str] = mapped_column(String(20), nullable=False, default="KANBAN")
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class BoardColumn(Base):
    __tablename__ = "board_columns"
    __table_args__ = (
        UniqueConstraint("board_id", "name", name="uq_board_columns_board_name"),
        UniqueConstraint("board_id", "position", name="uq_board_columns_board_position"),
        CheckConstraint("position >= 0", name="ck_board_columns_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    board_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status_key: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#64748b")
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("due_date IS NULL OR due_date >= start_date", name="ck_tasks_due_after_start"),
        CheckConstraint("position >= 0", name="ck_tasks_position"),
        Index("ix_tasks_column_position", "column_id", "position"),
        Index("ix_tasks_board_updated", "board_id", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    board_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True)
    column_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("board_columns.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)


class TaskSection(Base):
    __tablename__ = "task_sections"
    __table_args__ = (UniqueConstraint("task_id", "position", name="uq_task_sections_task_position"), CheckConstraint("position >= 0", name="ck_task_sections_position"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)  # Frontend, Backend, QA, etc.
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    __table_args__ = (CheckConstraint("position >= 0", name="ck_checklist_items_position"), Index("ix_checklist_items_section_position", "section_id", "position"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("task_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)


class TaskMember(Base):
    __tablename__ = "task_members"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_members_task_user"),
        CheckConstraint("member_role IN ('RESPONSIBLE','COLLABORATOR')", name="ck_task_members_role"),
        Index("uq_task_members_responsible", "task_id", unique=True, postgresql_where=text("member_role = 'RESPONSIBLE'"), sqlite_where=text("member_role = 'RESPONSIBLE'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)  # ID externo de Identidad; sin FK entre bases.
    member_role: Mapped[str] = mapped_column(String(20), nullable=False, default="COLLABORATOR")
    added_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_task_created", "task_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommentMention(Base):
    __tablename__ = "comment_mentions"
    __table_args__ = (UniqueConstraint("comment_id", "mentioned_user_id", name="uq_comment_mentions_comment_user"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, index=True)
    mentioned_user_id: Mapped[int] = mapped_column(Integer, nullable=False)  # ID externo de Identidad.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_attachments_size_positive"),
        CheckConstraint("media_type LIKE 'image/%' OR media_type LIKE 'video/%'", name="ck_attachments_media_type"),
        Index("ix_attachments_comment_created", "comment_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class TaskActivity(Base):
    __tablename__ = "task_activity"
    __table_args__ = (Index("ix_task_activity_task_created", "task_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
