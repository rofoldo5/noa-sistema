import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_and_metadata_match(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    command.check(cfg)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"alembic_version", "projects", "boards", "board_columns", "tasks", "task_sections",
                "checklist_items", "task_members", "comments", "comment_mentions", "attachments", "task_activity"}.issubset(tables)
    finally:
        engine.dispose()
