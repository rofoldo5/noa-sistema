import os
import uuid
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.models import Base, Project, Board, BoardColumn, Task, TaskSection, ChecklistItem, Comment, CommentMention, Attachment, TaskActivity, TaskMember

POSTGRES_URL = os.getenv("NOA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="NOA_TEST_POSTGRES_URL no configurado")


def test_alembic_migration_and_postgres_schema():
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = POSTGRES_URL
    try:
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", POSTGRES_URL.replace("%", "%%"))
        command.upgrade(cfg, "head")
        command.check(cfg)
        engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
        try:
            names = set(inspect(engine).get_table_names())
            expected = {"alembic_version", "projects", "boards", "board_columns", "tasks", "task_sections",
                        "checklist_items", "task_members", "comments", "comment_mentions", "attachments", "task_activity"}
            assert expected.issubset(names)
            with Session(engine) as db:
                project = Project(department_id=10, name=f"QA-{uuid.uuid4()}", description="PostgreSQL integration", status="ACTIVE", created_by_user_id=1)
                db.add(project); db.flush()
                board = Board(project_id=project.id, name="QA board", board_type="KANBAN", created_by_user_id=1)
                db.add(board); db.flush()
                col = BoardColumn(board_id=board.id, name="Pendiente", status_key="TODO", position=0, color="#64748b", is_done=False)
                db.add(col); db.flush()
                task = Task(board_id=board.id, column_id=col.id, title="QA task", description="", created_by_user_id=1)
                db.add(task); db.flush()
                db.add(TaskMember(task_id=task.id, user_id=1, member_role="RESPONSIBLE", added_by_user_id=1))
                section = TaskSection(task_id=task.id, title="Backend", notes="", position=0, created_by_user_id=1)
                db.add(section); db.flush()
                db.add(ChecklistItem(section_id=section.id, title="Check", position=0, created_by_user_id=1))
                comment = Comment(task_id=task.id, author_user_id=1, body="PG comment")
                db.add(comment); db.flush()
                db.add(CommentMention(comment_id=comment.id, mentioned_user_id=1))
                db.add(TaskActivity(task_id=task.id, actor_user_id=1, event_type="qa", summary="schema roundtrip", details={}))
                db.commit()
                assert db.scalar(select(Task.id).where(Task.id == task.id)) == task.id
        finally:
            engine.dispose()
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
