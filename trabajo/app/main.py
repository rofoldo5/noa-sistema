from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Integer, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Attachment, Board, BoardColumn, ChecklistItem, Comment, CommentMention,
    Project, Task, TaskActivity, TaskMember, TaskSection,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./noa_work.db")
IDENTITY_API_URL = os.getenv("IDENTITY_API_URL", "http://identity-api:8000").rstrip("/")
WORK_DEPARTMENT_ID_RAW = os.getenv("WORK_DEPARTMENT_ID", "")
try:
    WORK_DEPARTMENT_ID = int(WORK_DEPARTMENT_ID_RAW)
except ValueError as exc:
    raise RuntimeError("Configure WORK_DEPARTMENT_ID con el ID numerico del departamento de esta instancia.") from exc
if WORK_DEPARTMENT_ID <= 0:
    raise RuntimeError("Configure WORK_DEPARTMENT_ID con el ID numerico del departamento de esta instancia.")
ATTACHMENT_STORAGE_PATH = Path(os.getenv("ATTACHMENT_STORAGE_PATH", "./data/attachments"))
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(100 * 1024 * 1024)))
MEDIA_PREVIEW_SECRET = os.getenv("MEDIA_PREVIEW_SECRET", "")
if len(MEDIA_PREVIEW_SECRET) < 32:
    raise RuntimeError("Configure MEDIA_PREVIEW_SECRET con al menos 32 caracteres.")

engine_options = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(pool_size=5, max_overflow=10, pool_recycle=1800)
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

app = FastAPI(title="NOA - Trabajo", version="0.1.0", description="MVP Kanban de NOA")
bearer_scheme = HTTPBearer(auto_error=False)


def db_session():
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(db_session)]

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict:
    """Validate the live session through Identity; never access its PostgreSQL directly."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Se requiere iniciar sesion")
    try:
        response = httpx.get(
            f"{IDENTITY_API_URL}/auth/me",
            headers={"Authorization": f"Bearer {credentials.credentials}"},
            timeout=4.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="El servicio de Identidad no esta disponible") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="Sesion invalida, vencida o revocada")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="No se pudo validar la identidad")
    try:
        user = response.json()
        if not isinstance(user.get("id"), int) or not user.get("active", True):
            raise ValueError("Perfil no valido")
        user["departments"] = [int(x) for x in user.get("departments", [])]
        return user
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=502, detail="Respuesta invalida del servicio de Identidad") from exc


CurrentUser = Annotated[dict, Depends(get_current_user)]


def get_optional_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict | None:
    if not credentials:
        return None
    return get_current_user(credentials)


OptionalUser = Annotated[dict | None, Depends(get_optional_current_user)]


def require_department(user: dict, department_id: int) -> None:
    # Cada despliegue de Trabajo queda fijado a un solo departamento para aislar fallos y datos.
    if department_id != WORK_DEPARTMENT_ID:
        raise HTTPException(status_code=403, detail="Este servicio de Trabajo pertenece a otro departamento")
    if user.get("role") != "SUPERADMIN" and department_id not in user.get("departments", []):
        raise HTTPException(status_code=403, detail="No tienes acceso a este departamento")


def activity(db: Session, task_id: uuid.UUID, user_id: int, event_type: str, summary: str, details: dict | None = None) -> None:
    db.add(TaskActivity(task_id=task_id, actor_user_id=user_id, event_type=event_type,
                        summary=summary[:500], details=details or {}))


def project_for_user(db: Session, project_id: uuid.UUID, user: dict) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    require_department(user, project.department_id)
    return project


def task_context(db: Session, task_id: uuid.UUID, user: dict) -> tuple[Task, Board, Project]:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    board = db.get(Board, task.board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Tablero no encontrado")
    project = project_for_user(db, board.project_id, user)
    return task, board, project


def section_context(db: Session, section_id: uuid.UUID, user: dict) -> tuple[TaskSection, Task, Board, Project]:
    section = db.get(TaskSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Seccion no encontrada")
    task, board, project = task_context(db, section.task_id, user)
    return section, task, board, project


def safe_filename(filename: str | None) -> str:
    name = Path(filename or "archivo").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:180]
    return name or "archivo"


def detect_media_type(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    return None


def make_preview_token(attachment_id: uuid.UUID, user_id: int, ttl_seconds: int = 600) -> str:
    payload = {"a": str(attachment_id), "u": int(user_id), "e": int(time.time()) + ttl_seconds}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    signature = hmac.new(MEDIA_PREVIEW_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded}.{sig}"


def verify_preview_token(token: str, attachment_id: uuid.UUID) -> bool:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(MEDIA_PREVIEW_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            return False
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
        return payload.get("a") == str(attachment_id) and int(payload.get("e", 0)) > int(time.time()) and int(payload.get("u", 0)) > 0
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def attachment_out(item: Attachment, viewer_user_id: int | None = None) -> dict:
    token = make_preview_token(item.id, viewer_user_id) if viewer_user_id is not None else None
    token_query = f"?token={token}" if token else ""
    return {
        "id": str(item.id), "original_filename": item.original_filename,
        "media_type": item.media_type, "size_bytes": item.size_bytes,
        "sha256": item.sha256, "uploaded_by_user_id": item.uploaded_by_user_id,
        "created_at": item.created_at, "preview_url": f"/attachments/{item.id}/preview{token_query}",
        "download_url": f"/attachments/{item.id}/download{token_query}",
        "preview_url_expires_in": 600 if token else None,
    }


def comment_out(db: Session, comment: Comment, viewer_user_id: int | None = None) -> dict:
    mentions = db.scalars(select(CommentMention).where(CommentMention.comment_id == comment.id)).all()
    attachments = db.scalars(select(Attachment).where(Attachment.comment_id == comment.id).order_by(Attachment.created_at)).all()
    return {
        "id": str(comment.id), "task_id": str(comment.task_id), "author_user_id": comment.author_user_id,
        "body": comment.body, "mentions": [m.mentioned_user_id for m in mentions],
        "attachments": [attachment_out(a, viewer_user_id) for a in attachments], "created_at": comment.created_at,
        "updated_at": comment.updated_at,
    }


def task_out(db: Session, task: Task, board: Board | None = None, detailed: bool = False, viewer_user_id: int | None = None) -> dict:
    column = db.get(BoardColumn, task.column_id)
    sections = db.scalars(select(TaskSection).where(TaskSection.task_id == task.id).order_by(TaskSection.position)).all()
    checklist_counts = db.execute(
        select(func.count(ChecklistItem.id), func.sum(ChecklistItem.is_completed.cast(Integer)))
        .join(TaskSection, TaskSection.id == ChecklistItem.section_id)
        .where(TaskSection.task_id == task.id)
    ).one()
    members = db.scalars(select(TaskMember).where(TaskMember.task_id == task.id).order_by(TaskMember.created_at)).all()
    result = {
        "id": str(task.id), "board_id": str(task.board_id), "column_id": str(task.column_id),
        "column_name": column.name if column else None, "title": task.title, "description": task.description,
        "start_date": task.start_date, "due_date": task.due_date, "position": task.position,
        "created_by_user_id": task.created_by_user_id, "created_at": task.created_at, "updated_at": task.updated_at,
        "completed_at": task.completed_at, "archived_at": task.archived_at,
        "checklist_total": int(checklist_counts[0] or 0), "checklist_completed": int(checklist_counts[1] or 0),
        "members": [{"user_id": m.user_id, "role": m.member_role} for m in members],
    }
    if detailed:
        result["sections"] = []
        for section in sections:
            items = db.scalars(select(ChecklistItem).where(ChecklistItem.section_id == section.id).order_by(ChecklistItem.position)).all()
            result["sections"].append({
                "id": str(section.id), "title": section.title, "notes": section.notes,
                "position": section.position, "created_by_user_id": section.created_by_user_id,
                "checklist": [{"id": str(i.id), "title": i.title, "is_completed": i.is_completed,
                               "position": i.position, "created_by_user_id": i.created_by_user_id,
                               "completed_by_user_id": i.completed_by_user_id, "completed_at": i.completed_at}
                              for i in items],
            })
        comments = db.scalars(select(Comment).where(Comment.task_id == task.id, Comment.deleted_at.is_(None)).order_by(Comment.created_at)).all()
        result["comments"] = [comment_out(db, c, viewer_user_id) for c in comments]
        events = db.scalars(select(TaskActivity).where(TaskActivity.task_id == task.id).order_by(TaskActivity.created_at.desc()).limit(100)).all()
        result["activity"] = [{"id": str(e.id), "actor_user_id": e.actor_user_id, "event_type": e.event_type,
                                "summary": e.summary, "details": e.details, "created_at": e.created_at} for e in events]
    return result


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=10000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre es obligatorio")
        return value


class BoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    start_date: date = Field(default_factory=date.today)
    due_date: date | None = None
    description: str = Field(default="", max_length=20000)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El titulo es obligatorio")
        return value

    @field_validator("due_date")
    @classmethod
    def due_date_optional(cls, value: date | None) -> date | None:
        return value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    start_date: date | None = None
    due_date: date | None = None
    column_id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=0)


class SectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=20000)
    position: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El titulo de la seccion es obligatorio")
        return value


class SectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=20000)
    position: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("El titulo de la seccion es obligatorio")
        return value


class ChecklistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    position: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El elemento de checklist es obligatorio")
        return value


class ChecklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=500)
    is_completed: bool | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("El elemento de checklist es obligatorio")
        return value


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0)
    member_role: Literal["RESPONSIBLE", "COLLABORATOR"] = "COLLABORATOR"


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=10000)
    mentioned_user_ids: list[int] = Field(default_factory=list, max_length=30)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El comentario no puede estar vacio")
        return value


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Base de Trabajo no disponible") from exc


@app.get("/projects")
def list_projects(user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Project).where(Project.department_id == WORK_DEPARTMENT_ID)
    if user.get("role") != "SUPERADMIN":
        dept_ids = user.get("departments", [])
        if WORK_DEPARTMENT_ID not in dept_ids:
            return []
    projects = db.scalars(stmt.order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all()
    return [{"id": str(p.id), "department_id": p.department_id, "name": p.name,
             "description": p.description, "status": p.status, "created_by_user_id": p.created_by_user_id,
             "created_at": p.created_at, "updated_at": p.updated_at} for p in projects]


@app.post("/projects", status_code=201)
def create_project(data: ProjectCreate, user: CurrentUser, db: DB):
    require_department(user, data.department_id)
    project = Project(department_id=data.department_id, name=data.name.strip(), description=data.description.strip(), created_by_user_id=user["id"])
    db.add(project)
    try:
        db.flush()
        board = Board(project_id=project.id, name="Tablero principal", created_by_user_id=user["id"])
        db.add(board)
        db.flush()
        defaults = [
            ("Pendiente", "TODO", 0, "#64748b", False),
            ("En proceso", "IN_PROGRESS", 1, "#2563eb", False),
            ("Finalizado", "DONE", 2, "#16a34a", True),
        ]
        db.add_all([BoardColumn(board_id=board.id, name=name, status_key=key, position=pos, color=color, is_done=done)
                    for name, key, pos, color, done in defaults])
        db.commit()
        db.refresh(project)
        return {"id": str(project.id), "department_id": project.department_id, "name": project.name,
                "description": project.description, "status": project.status, "board_id": str(board.id),
                "created_at": project.created_at, "updated_at": project.updated_at}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un proyecto con ese nombre en el departamento") from exc


@app.get("/projects/{project_id}/boards")
def list_boards(project_id: uuid.UUID, user: CurrentUser, db: DB):
    project = project_for_user(db, project_id, user)
    boards = db.scalars(select(Board).where(Board.project_id == project.id).order_by(Board.created_at)).all()
    return [{"id": str(b.id), "project_id": str(b.project_id), "name": b.name, "board_type": b.board_type,
             "columns": [{"id": str(c.id), "name": c.name, "status_key": c.status_key, "position": c.position, "color": c.color, "is_done": c.is_done}
                         for c in db.scalars(select(BoardColumn).where(BoardColumn.board_id == b.id).order_by(BoardColumn.position)).all()]}
            for b in boards]


@app.post("/projects/{project_id}/boards", status_code=201)
def create_board(project_id: uuid.UUID, data: BoardCreate, user: CurrentUser, db: DB):
    project = project_for_user(db, project_id, user)
    board = Board(project_id=project.id, name=data.name.strip(), created_by_user_id=user["id"])
    db.add(board)
    try:
        db.flush()
        db.add_all([
            BoardColumn(board_id=board.id, name="Pendiente", status_key="TODO", position=0, color="#64748b", is_done=False),
            BoardColumn(board_id=board.id, name="En proceso", status_key="IN_PROGRESS", position=1, color="#2563eb", is_done=False),
            BoardColumn(board_id=board.id, name="Finalizado", status_key="DONE", position=2, color="#16a34a", is_done=True),
        ])
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un tablero con ese nombre") from exc
    return {"id": str(board.id), "project_id": str(project.id), "name": board.name, "board_type": board.board_type}


@app.get("/boards/{board_id}/columns")
def list_columns(board_id: uuid.UUID, user: CurrentUser, db: DB):
    board = db.get(Board, board_id)
    if not board:
        raise HTTPException(404, "Tablero no encontrado")
    project_for_user(db, board.project_id, user)
    return [{"id": str(c.id), "name": c.name, "status_key": c.status_key, "position": c.position, "color": c.color, "is_done": c.is_done}
            for c in db.scalars(select(BoardColumn).where(BoardColumn.board_id == board_id).order_by(BoardColumn.position)).all()]


def task_card_out(db: Session, task: Task, column_by_id: dict, members_by_task: dict, counts_by_task: dict) -> dict:
    column = column_by_id.get(task.column_id)
    total, completed = counts_by_task.get(task.id, (0, 0))
    return {
        "id": str(task.id), "board_id": str(task.board_id), "column_id": str(task.column_id),
        "column_name": column.name if column else None, "title": task.title, "description": task.description,
        "start_date": task.start_date, "due_date": task.due_date, "position": task.position,
        "created_by_user_id": task.created_by_user_id, "created_at": task.created_at, "updated_at": task.updated_at,
        "completed_at": task.completed_at, "archived_at": task.archived_at,
        "checklist_total": total, "checklist_completed": completed,
        "members": [{"user_id": m.user_id, "role": m.member_role} for m in members_by_task.get(task.id, [])],
    }


@app.get("/boards/{board_id}/tasks")
def list_tasks(board_id: uuid.UUID, user: CurrentUser, db: DB, column_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    board = db.get(Board, board_id)
    if not board:
        raise HTTPException(404, "Tablero no encontrado")
    project_for_user(db, board.project_id, user)
    stmt = select(Task).where(Task.board_id == board_id, Task.archived_at.is_(None))
    if column_id:
        column = db.get(BoardColumn, column_id)
        if not column or column.board_id != board_id:
            raise HTTPException(404, "Columna no encontrada en este tablero")
        stmt = stmt.where(Task.column_id == column_id)
    tasks = db.scalars(stmt.order_by(Task.column_id, Task.position, Task.created_at).limit(limit).offset(offset)).all()
    if not tasks:
        return []
    task_ids = [task.id for task in tasks]
    column_ids = {task.column_id for task in tasks}
    column_by_id = {column.id: column for column in db.scalars(select(BoardColumn).where(BoardColumn.id.in_(column_ids))).all()}
    members_by_task: dict = {}
    for member in db.scalars(select(TaskMember).where(TaskMember.task_id.in_(task_ids))).all():
        members_by_task.setdefault(member.task_id, []).append(member)
    counts_by_task: dict = {}
    count_rows = db.execute(
        select(TaskSection.task_id, func.count(ChecklistItem.id), func.coalesce(func.sum(ChecklistItem.is_completed.cast(Integer)), 0))
        .outerjoin(ChecklistItem, ChecklistItem.section_id == TaskSection.id)
        .where(TaskSection.task_id.in_(task_ids)).group_by(TaskSection.task_id)
    ).all()
    for task_id, total, completed in count_rows:
        counts_by_task[task_id] = (int(total or 0), int(completed or 0))
    return [task_card_out(db, task, column_by_id, members_by_task, counts_by_task) for task in tasks]


@app.post("/boards/{board_id}/tasks", status_code=201)
def create_task(board_id: uuid.UUID, data: TaskCreate, user: CurrentUser, db: DB):
    board = db.get(Board, board_id)
    if not board:
        raise HTTPException(404, "Tablero no encontrado")
    project_for_user(db, board.project_id, user)
    if data.due_date and data.due_date < data.start_date:
        raise HTTPException(422, "La fecha final no puede ser anterior a la fecha de inicio")
    first_column = db.scalar(select(BoardColumn).where(BoardColumn.board_id == board_id).order_by(BoardColumn.position))
    if not first_column:
        raise HTTPException(409, "El tablero no tiene columnas configuradas")
    task = Task(board_id=board_id, column_id=first_column.id, title=data.title.strip(), description=data.description.strip(),
                start_date=data.start_date, due_date=data.due_date, created_by_user_id=user["id"], position=0)
    db.add(task)
    db.flush()
    db.add(TaskMember(task_id=task.id, user_id=user["id"], member_role="RESPONSIBLE", added_by_user_id=user["id"]))
    activity(db, task.id, user["id"], "task.created", "Creo la tarea", {"title": task.title})
    db.commit()
    db.refresh(task)
    return task_out(db, task, detailed=True, viewer_user_id=user["id"])


@app.get("/tasks/{task_id}")
def get_task(task_id: uuid.UUID, user: CurrentUser, db: DB):
    task, board, _project = task_context(db, task_id, user)
    return task_out(db, task, board, detailed=True, viewer_user_id=user["id"])


@app.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, data: TaskUpdate, user: CurrentUser, db: DB):
    task, board, _project = task_context(db, task_id, user)
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
        if not changes["title"]:
            raise HTTPException(422, "El titulo es obligatorio")
    if "column_id" in changes and changes["column_id"] is not None:
        column = db.get(BoardColumn, changes["column_id"])
        if not column or column.board_id != board.id:
            raise HTTPException(422, "La columna debe pertenecer al tablero de la tarea")
        changes["column_id"] = column.id
        if column.is_done and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        elif not column.is_done:
            task.completed_at = None
    new_start = changes.get("start_date", task.start_date)
    new_due = changes.get("due_date", task.due_date)
    if new_start is not None and new_due is not None and new_due < new_start:
        raise HTTPException(422, "La fecha final no puede ser anterior a la fecha de inicio")
    before = {}
    for key, value in changes.items():
        if key in {"title", "description", "start_date", "column_id", "position"} and value is None:
            raise HTTPException(422, f"{key} no puede ser nulo")
        if key in {"title", "description", "start_date", "due_date", "column_id", "position"}:
            before[key] = str(getattr(task, key)) if getattr(task, key) is not None else None
            setattr(task, key, value)
    task.updated_at = datetime.now(timezone.utc)
    activity(db, task.id, user["id"], "task.updated", "Actualizo la tarea", {"before": before, "fields": list(changes.keys())})
    db.commit()
    db.refresh(task)
    return task_out(db, task, board, detailed=True, viewer_user_id=user["id"])


@app.post("/tasks/{task_id}/sections", status_code=201)
def create_section(task_id: uuid.UUID, data: SectionCreate, user: CurrentUser, db: DB):
    task, _board, _project = task_context(db, task_id, user)
    position = data.position
    if position is None:
        max_position = db.scalar(select(func.max(TaskSection.position)).where(TaskSection.task_id == task.id))
        position = 0 if max_position is None else int(max_position) + 1
    section = TaskSection(task_id=task.id, title=data.title.strip(), notes=data.notes.strip(), position=position, created_by_user_id=user["id"])
    db.add(section)
    activity(db, task.id, user["id"], "section.created", f"Creo la seccion {section.title}")
    db.commit()
    db.refresh(section)
    return {"id": str(section.id), "task_id": str(section.task_id), "title": section.title, "notes": section.notes,
            "position": section.position, "created_by_user_id": section.created_by_user_id}


@app.patch("/sections/{section_id}")
def update_section(section_id: uuid.UUID, data: SectionUpdate, user: CurrentUser, db: DB):
    section, task, _board, _project = section_context(db, section_id, user)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is not None:
            setattr(section, key, value.strip() if key in {"title", "notes"} else value)
    section.updated_at = datetime.now(timezone.utc)
    activity(db, task.id, user["id"], "section.updated", f"Actualizo la seccion {section.title}", {"fields": list(changes.keys())})
    db.commit()
    db.refresh(section)
    return {"id": str(section.id), "task_id": str(section.task_id), "title": section.title, "notes": section.notes, "position": section.position}


@app.post("/sections/{section_id}/checklist", status_code=201)
def create_checklist_item(section_id: uuid.UUID, data: ChecklistCreate, user: CurrentUser, db: DB):
    section, task, _board, _project = section_context(db, section_id, user)
    item = ChecklistItem(section_id=section.id, title=data.title.strip(), position=data.position, created_by_user_id=user["id"])
    db.add(item)
    activity(db, task.id, user["id"], "checklist.created", "Agrego un elemento al checklist", {"title": item.title, "section_id": str(section.id)})
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "section_id": str(item.section_id), "title": item.title, "is_completed": item.is_completed,
            "position": item.position, "created_by_user_id": item.created_by_user_id, "completed_by_user_id": item.completed_by_user_id,
            "completed_at": item.completed_at}


@app.patch("/checklist/{item_id}")
def update_checklist_item(item_id: uuid.UUID, data: ChecklistUpdate, user: CurrentUser, db: DB):
    item = db.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(404, "Elemento de checklist no encontrado")
    section, task, _board, _project = section_context(db, item.section_id, user)
    changes = data.model_dump(exclude_unset=True)
    if "is_completed" in changes and changes["is_completed"] is None:
        raise HTTPException(422, "is_completed no puede ser nulo")
    for key, value in changes.items():
        if value is not None:
            setattr(item, key, value.strip() if key == "title" else value)
    if "is_completed" in changes:
        if item.is_completed:
            item.completed_by_user_id = user["id"]
            item.completed_at = datetime.now(timezone.utc)
        else:
            item.completed_by_user_id = None
            item.completed_at = None
    item.updated_at = datetime.now(timezone.utc)
    activity(db, task.id, user["id"], "checklist.updated", "Actualizo un elemento del checklist", {"item_id": str(item.id), "fields": list(changes.keys())})
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "section_id": str(item.section_id), "title": item.title, "is_completed": item.is_completed,
            "position": item.position, "created_by_user_id": item.created_by_user_id, "completed_by_user_id": item.completed_by_user_id,
            "completed_at": item.completed_at}


def identity_users_for_department(token: str, department_id: int) -> list[dict]:
    # Identity currently caps page size at 100; paginate so departments larger than 100 work.
    people: list[dict] = []
    offset = 0
    while offset < 10000:
        try:
            response = httpx.get(
                f"{IDENTITY_API_URL}/users",
                params={"limit": 100, "offset": offset},
                headers={"Authorization": f"Bearer {token}"}, timeout=4.0,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar Identidad para validar el integrante") from exc
        if response.status_code == 401:
            raise HTTPException(401, "Sesion invalida")
        if response.status_code != 200:
            raise HTTPException(503, "Identidad no pudo validar los integrantes")
        page = response.json()
        if not isinstance(page, list):
            raise HTTPException(502, "Respuesta invalida al consultar integrantes")
        people.extend(p for p in page if p.get("active") and department_id in [int(d) for d in p.get("departments", [])])
        if len(page) < 100:
            break
        offset += 100
    return people


@app.post("/tasks/{task_id}/members", status_code=201)
def add_task_member(task_id: uuid.UUID, data: MemberCreate, user: CurrentUser, db: DB,
                    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]):
    task, _board, project = task_context(db, task_id, user)
    if db.scalar(select(TaskMember.id).where(TaskMember.task_id == task.id, TaskMember.user_id == data.user_id)):
        raise HTTPException(409, "La persona ya participa en esta tarea")
    if data.user_id == user["id"]:
        target_user = user
    else:
        if not credentials:
            raise HTTPException(401, "Sesion requerida")
        candidates = identity_users_for_department(credentials.credentials, project.department_id)
        target_user = next((p for p in candidates if p.get("id") == data.user_id), None)
        if not target_user:
            raise HTTPException(404, "Usuario no disponible en el departamento o no visible para este rol")
    if data.member_role == "RESPONSIBLE":
        old = db.scalars(select(TaskMember).where(TaskMember.task_id == task.id, TaskMember.member_role == "RESPONSIBLE")).all()
        for member in old:
            db.delete(member)
    member = TaskMember(task_id=task.id, user_id=data.user_id, member_role=data.member_role, added_by_user_id=user["id"])
    db.add(member)
    activity(db, task.id, user["id"], "task.member_added", "Agrego un integrante", {"user_id": data.user_id, "role": data.member_role})
    db.commit()
    return {"task_id": str(task.id), "user_id": data.user_id, "role": data.member_role}


@app.delete("/tasks/{task_id}/members/{member_user_id}", status_code=204)
def remove_task_member(task_id: uuid.UUID, member_user_id: int, user: CurrentUser, db: DB):
    task, _board, _project = task_context(db, task_id, user)
    member = db.scalar(select(TaskMember).where(TaskMember.task_id == task.id, TaskMember.user_id == member_user_id))
    if not member:
        raise HTTPException(404, "Integrante no encontrado")
    if member.member_role == "RESPONSIBLE":
        raise HTTPException(409, "Asigna primero otra persona responsable")
    db.delete(member)
    activity(db, task.id, user["id"], "task.member_removed", "Retiro un integrante", {"user_id": member_user_id})
    db.commit()
    return None


@app.get("/tasks/{task_id}/comments")
def list_comments(task_id: uuid.UUID, user: CurrentUser, db: DB):
    task_context(db, task_id, user)
    comments = db.scalars(select(Comment).where(Comment.task_id == task_id, Comment.deleted_at.is_(None)).order_by(Comment.created_at)).all()
    return [comment_out(db, c, user["id"]) for c in comments]


@app.post("/tasks/{task_id}/comments", status_code=201)
def create_comment(task_id: uuid.UUID, data: CommentCreate, user: CurrentUser, db: DB):
    task, _board, _project = task_context(db, task_id, user)
    mentioned = sorted(set(data.mentioned_user_ids))
    if mentioned:
        participants = set(db.scalars(select(TaskMember.user_id).where(TaskMember.task_id == task.id)).all())
        invalid = set(mentioned) - participants
        if invalid:
            raise HTTPException(422, "Solo puedes mencionar participantes asignados a esta tarea")
    comment = Comment(task_id=task.id, author_user_id=user["id"], body=data.body)
    db.add(comment)
    db.flush()
    db.add_all([CommentMention(comment_id=comment.id, mentioned_user_id=uid) for uid in mentioned])
    activity(db, task.id, user["id"], "comment.created", "Agrego un comentario", {"comment_id": str(comment.id), "mentions": mentioned})
    db.commit()
    db.refresh(comment)
    return comment_out(db, comment, user["id"])


@app.post("/comments/{comment_id}/attachments", status_code=201)
async def upload_comment_attachment(comment_id: uuid.UUID, user: CurrentUser, db: DB, file: UploadFile = File(...)):
    comment = db.get(Comment, comment_id)
    if not comment or comment.deleted_at is not None:
        raise HTTPException(404, "Comentario no encontrado")
    task, _board, _project = task_context(db, comment.task_id, user)
    first = await file.read(32)
    media_type = detect_media_type(first)
    if media_type is None:
        raise HTTPException(415, "Solo se permiten imagenes PNG, JPEG, GIF, WebP y videos MP4, QuickTime o WebM")
    file.file.seek(0)
    ATTACHMENT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    storage_key = uuid.uuid4().hex
    target = ATTACHMENT_STORAGE_PATH / storage_key
    temporary = ATTACHMENT_STORAGE_PATH / f".{storage_key}.part"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(413, f"El archivo supera el limite de {MAX_ATTACHMENT_BYTES} bytes")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(422, "El archivo esta vacio")
        os.replace(temporary, target)
        attachment = Attachment(comment_id=comment.id, storage_key=storage_key,
                                original_filename=safe_filename(file.filename), media_type=media_type,
                                size_bytes=size, sha256=digest.hexdigest(), uploaded_by_user_id=user["id"])
        db.add(attachment)
        db.flush()
        activity(db, task.id, user["id"], "comment.attachment_added", "Adjunto una imagen o video al comentario",
                 {"attachment_id": str(attachment.id), "media_type": media_type, "size_bytes": size})
        db.commit()
        db.refresh(attachment)
        return attachment_out(attachment, user["id"])
    except Exception:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        # Remove the stored file if database commit failed; never leave orphaned bytes on this path.
        if target.exists():
            target.unlink(missing_ok=True)
        db.rollback()
        raise
    finally:
        await file.close()


def get_attachment_for_user(db: Session, attachment_id: uuid.UUID, user: dict) -> Attachment:
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(404, "Adjunto no encontrado")
    comment = db.get(Comment, attachment.comment_id)
    if not comment:
        raise HTTPException(404, "Comentario no encontrado")
    task_context(db, comment.task_id, user)
    path = ATTACHMENT_STORAGE_PATH / attachment.storage_key
    if not path.is_file():
        raise HTTPException(410, "El archivo no esta disponible en almacenamiento")
    return attachment


@app.get("/attachments/{attachment_id}/preview")
def preview_attachment(attachment_id: uuid.UUID, user: OptionalUser, db: DB, token: str | None = Query(default=None)):
    if user is not None:
        attachment = get_attachment_for_user(db, attachment_id, user)
    else:
        if not token or not verify_preview_token(token, attachment_id):
            raise HTTPException(401, "Se requiere una sesion valida o un enlace temporal vigente")
        attachment = db.get(Attachment, attachment_id)
        if not attachment:
            raise HTTPException(404, "Adjunto no encontrado")
    path = ATTACHMENT_STORAGE_PATH / attachment.storage_key
    if not path.is_file():
        raise HTTPException(410, "El archivo no esta disponible en almacenamiento")
    filename = attachment.original_filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    return FileResponse(path, media_type=attachment.media_type,
                        headers={"Content-Disposition": f'inline; filename="{filename}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@app.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: uuid.UUID, user: OptionalUser, db: DB, token: str | None = Query(default=None)):
    if user is not None:
        attachment = get_attachment_for_user(db, attachment_id, user)
    else:
        if not token or not verify_preview_token(token, attachment_id):
            raise HTTPException(401, "Se requiere una sesion valida o un enlace temporal vigente")
        attachment = db.get(Attachment, attachment_id)
        if not attachment:
            raise HTTPException(404, "Adjunto no encontrado")
    path = ATTACHMENT_STORAGE_PATH / attachment.storage_key
    if not path.is_file():
        raise HTTPException(410, "El archivo no esta disponible en almacenamiento")
    filename = attachment.original_filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    return FileResponse(path, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@app.get("/tasks/{task_id}/activity")
def list_task_activity(task_id: uuid.UUID, user: CurrentUser, db: DB, limit: int = Query(100, ge=1, le=200)):
    task_context(db, task_id, user)
    events = db.scalars(select(TaskActivity).where(TaskActivity.task_id == task_id).order_by(TaskActivity.created_at.desc()).limit(limit)).all()
    return [{"id": str(e.id), "actor_user_id": e.actor_user_id, "event_type": e.event_type,
             "summary": e.summary, "details": e.details, "created_at": e.created_at} for e in events]
