import base64
import uuid
from sqlalchemy import select
from app import main
from app.models import Board, BoardColumn, Comment, Project, Task, TaskMember
from conftest import TEST_USER


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_project_creates_default_kanban(client):
    response = client.post("/projects", json={"department_id": 10, "name": "Bot empresarial"})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Bot empresarial"
    boards = client.get(f"/projects/{data['id']}/boards").json()
    assert len(boards) == 1
    assert [c["status_key"] for c in boards[0]["columns"]] == ["TODO", "IN_PROGRESS", "DONE"]


def test_user_cannot_create_project_in_other_department(client):
    response = client.post("/projects", json={"department_id": 20, "name": "No autorizado"})
    assert response.status_code == 403


def test_task_has_required_start_and_optional_due_date(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    response = client.post(f"/boards/{board['id']}/tasks", json={"title": "Integrar Telegram"})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Integrar Telegram"
    assert task["start_date"]
    assert task["due_date"] is None
    assert task["members"] == [{"user_id": 1, "role": "RESPONSIBLE"}]


def test_due_date_before_start_is_rejected(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    response = client.post(f"/boards/{board['id']}/tasks", json={"title": "Fechas invalidas", "start_date": "2026-10-20", "due_date": "2026-10-19"})
    assert response.status_code == 422


def test_task_sections_and_checklist_are_nested_in_task_detail(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Integrar bot"}).json()
    frontend = client.post(f"/tasks/{task['id']}/sections", json={"title": "Frontend", "notes": "Conectar la pantalla"})
    backend = client.post(f"/tasks/{task['id']}/sections", json={"title": "Backend", "notes": "Crear endpoint"})
    assert frontend.status_code == 201, frontend.text
    assert backend.status_code == 201, backend.text
    item = client.post(f"/sections/{frontend.json()['id']}/checklist", json={"title": "Consumir API"})
    assert item.status_code == 201, item.text
    checked = client.patch(f"/checklist/{item.json()['id']}", json={"is_completed": True})
    assert checked.status_code == 200, checked.text
    detail = client.get(f"/tasks/{task['id']}").json()
    assert [s["title"] for s in detail["sections"]] == ["Frontend", "Backend"]
    assert detail["sections"][0]["checklist"][0]["is_completed"] is True
    assert detail["checklist_total"] == 1
    assert detail["checklist_completed"] == 1


def test_comment_mentions_only_task_participants(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Menciones"}).json()
    denied = client.post(f"/tasks/{task['id']}/comments", json={"body": "Hola @usuario", "mentioned_user_ids": [2]})
    assert denied.status_code == 422
    with main.SessionLocal() as db:
        db.add(TaskMember(task_id=uuid.UUID(task['id']), user_id=2, member_role="COLLABORATOR", added_by_user_id=1))
        db.commit()
    comment = client.post(f"/tasks/{task['id']}/comments", json={"body": "@usuario revisa esto", "mentioned_user_ids": [2]})
    assert comment.status_code == 201, comment.text
    assert comment.json()["mentions"] == [2]


def test_comment_image_upload_and_preview(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Adjuntar captura"}).json()
    comment = client.post(f"/tasks/{task['id']}/comments", json={"body": "Adjunto captura de prueba"}).json()
    # Minimal PNG-signature fixture; preview endpoint tests secure inline delivery, not image decoding.
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfHcAAAAASUVORK5CYII=")
    upload = client.post(f"/comments/{comment['id']}/attachments", files={"file": ("captura.png", png, "image/png")})
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["media_type"] == "image/png"
    preview = client.get(attachment["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/png")
    assert preview.content == png
    detail = client.get(f"/tasks/{task['id']}").json()
    assert detail["comments"][0]["attachments"][0]["id"] == attachment["id"]


def test_upload_rejects_unknown_file_type(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Tipo invalido"}).json()
    comment = client.post(f"/tasks/{task['id']}/comments", json={"body": "Archivo"}).json()
    response = client.post(f"/comments/{comment['id']}/attachments", files={"file": ("script.html", b"<script>alert(1)</script>", "text/html")})
    assert response.status_code == 415


def test_moving_task_between_board_columns_is_recorded(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Mover tarjeta"}).json()
    columns = board["columns"]
    response = client.patch(f"/tasks/{task['id']}", json={"column_id": columns[1]["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["column_name"] == "En proceso"
    assert any(event["event_type"] == "task.updated" for event in response.json()["activity"])


def test_foreign_board_column_cannot_be_used(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Mover tarjeta"}).json()
    response = client.patch(f"/tasks/{task['id']}", json={"column_id": "00000000-0000-0000-0000-000000000001"})
    assert response.status_code == 422


def test_comment_video_upload_and_inline_preview(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Video de avance"}).json()
    comment = client.post(f"/tasks/{task['id']}/comments", json={"body": "Video de prueba"}).json()
    # Minimal MP4 ftyp header; tests type detection and protected temporary preview URL.
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 12
    upload = client.post(f"/comments/{comment['id']}/attachments", files={"file": ("avance.mp4", mp4, "video/mp4")})
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["media_type"] == "video/mp4"
    preview = client.get(attachment["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("video/mp4")
    assert preview.content == mp4
    tampered = client.get(attachment["preview_url"] + "x")
    assert tampered.status_code == 401


def test_task_cannot_be_read_from_another_department(client, create_project):
    board = client.get(f"/projects/{create_project['id']}/boards").json()[0]
    task = client.post(f"/boards/{board['id']}/tasks", json={"title": "Privacidad departamental"}).json()
    main.app.dependency_overrides[main.get_current_user] = lambda: {
        "id": 99, "name": "Otro departamento", "email": "otro@example.test",
        "role": "EMPLEADO", "active": True, "departments": [20],
    }
    response = client.get(f"/tasks/{task['id']}")
    assert response.status_code == 403


def test_superadmin_is_still_scoped_to_this_work_instance(client):
    main.app.dependency_overrides[main.get_current_user] = lambda: {
        "id": 99, "name": "SuperAdmin", "email": "admin@example.test",
        "role": "SUPERADMIN", "active": True, "departments": [],
    }
    response = client.post("/projects", json={"department_id": 20, "name": "No debe entrar en esta instancia"})
    assert response.status_code == 403
