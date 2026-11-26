"""Database tests: the CRUD layer, persistence and constraints, without HTTP.

Locally these run on SQLite; in CI they run on a real PostgreSQL service.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

import app.database as database
from app import crud
from app.database import SessionLocal
from app.models import Task
from app.schemas import TaskCreate, TaskPriority, TaskStatus, TaskUpdate


def new_task(db, **fields):
    return crud.create_task(db, TaskCreate(**{"title": "Sample", **fields}))


def test_create_assigns_id_and_timestamps(db_session):
    task = new_task(db_session, title="Persist me")

    assert task.id is not None
    assert task.created_at is not None
    assert task.updated_at is not None


def test_saved_task_is_visible_from_a_new_session(db_session):
    task = new_task(db_session, title="Survives", due_date=date(2026, 12, 24))

    with SessionLocal() as other_session:
        loaded = crud.get_task(other_session, task.id)

    assert loaded.title == "Survives"
    assert loaded.due_date == date(2026, 12, 24)


def test_enums_are_stored_as_readable_text(db_session):
    task = new_task(db_session, status="in_progress", priority="high")

    row = db_session.execute(
        text("SELECT status, priority FROM tasks WHERE id = :id"), {"id": task.id}
    ).one()

    assert tuple(row) == ("in_progress", "high")


def test_get_missing_task_returns_none(db_session):
    assert crud.get_task(db_session, 12345) is None


def test_list_orders_by_id_and_filters(db_session):
    first = new_task(db_session, status="done", priority="low")
    second = new_task(db_session, status="done", priority="high")
    new_task(db_session, status="todo", priority="high")

    assert [t.id for t in crud.list_tasks(db_session, status=TaskStatus.DONE)] == [
        first.id,
        second.id,
    ]
    assert [
        t.id
        for t in crud.list_tasks(db_session, status=TaskStatus.DONE, priority=TaskPriority.HIGH)
    ] == [second.id]


def test_list_limit_and_offset(db_session):
    ids = [new_task(db_session, title=f"t{n}").id for n in range(4)]

    assert [t.id for t in crud.list_tasks(db_session, limit=2, offset=1)] == ids[1:3]


def test_update_changes_row_and_updated_at(db_session):
    task = new_task(db_session)
    created_at, updated_at = task.created_at, task.updated_at

    crud.update_task(db_session, task, TaskUpdate(title="Renamed"))

    with SessionLocal() as other_session:
        loaded = crud.get_task(other_session, task.id)
    assert loaded.title == "Renamed"
    assert loaded.created_at == created_at
    assert loaded.updated_at > updated_at


def test_replace_resets_unsent_fields(db_session):
    task = new_task(db_session, description="notes", priority="high")

    crud.replace_task(db_session, task, TaskCreate(title="Fresh"))

    assert task.description is None
    assert task.priority is TaskPriority.MEDIUM


def test_delete_removes_the_row(db_session):
    task = new_task(db_session)

    crud.delete_task(db_session, task)

    count = db_session.execute(text("SELECT COUNT(*) FROM tasks")).scalar_one()
    assert count == 0


def test_title_is_required_by_the_database(db_session):
    db_session.add(Task(title=None))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_is_reachable():
    assert database.database_is_reachable() is True


def test_unreachable_database_is_reported(monkeypatch):
    # Nothing listens on port 1, so connecting fails fast.
    dead_engine = create_engine(
        "postgresql+psycopg://user:pass@127.0.0.1:1/none", connect_args={"connect_timeout": 2}
    )
    monkeypatch.setattr(database, "engine", dead_engine)

    assert database.database_is_reachable() is False


def test_tables_are_created_on_startup(client):
    # The client fixture runs the app's startup, which creates missing tables.
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1 FROM tasks LIMIT 1"))
