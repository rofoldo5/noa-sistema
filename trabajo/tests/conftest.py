import os
from datetime import date
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/noa_work_unit.db")
os.environ.setdefault("IDENTITY_API_URL", "http://identity-not-used.invalid")
os.environ.setdefault("WORK_DEPARTMENT_ID", "10")
os.environ.setdefault("ATTACHMENT_STORAGE_PATH", "/tmp/noa-work-attachments")
os.environ.setdefault("JWT_SECRET", "test-only-not-used-by-work-service")
os.environ.setdefault("MEDIA_PREVIEW_SECRET", "test-only-preview-secret-at-least-32-chars")

from app import main
from app.models import Base, TaskMember
from sqlalchemy import delete

TEST_USER = {"id": 1, "name": "Programador Uno", "email": "uno@example.test", "role": "JEFE", "active": True, "departments": [10]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Use the service's configured test database and isolated attachment directory.
    main.Base = Base
    Base.metadata.drop_all(main.engine)
    Base.metadata.create_all(main.engine)
    monkeypatch.setattr(main, "ATTACHMENT_STORAGE_PATH", tmp_path / "attachments")
    main.app.dependency_overrides[main.get_current_user] = lambda: dict(TEST_USER)
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(main.engine)


@pytest.fixture()
def create_project(client):
    response = client.post("/projects", json={"department_id": 10, "name": "Bot empresarial", "description": "Piloto de tres programadores"})
    assert response.status_code == 201, response.text
    return response.json()
