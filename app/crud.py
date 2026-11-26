from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.schemas import TaskCreate, TaskPriority, TaskStatus, TaskUpdate


def create_task(db: Session, data: TaskCreate) -> Task:
    task = Task(**data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    *,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Task]:
    query = select(Task).order_by(Task.id)
    if status is not None:
        query = query.where(Task.status == status)
    if priority is not None:
        query = query.where(Task.priority == priority)
    return list(db.scalars(query.limit(limit).offset(offset)))


def get_task(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def replace_task(db: Session, task: Task, data: TaskCreate) -> Task:
    return _apply_changes(db, task, data.model_dump())


def update_task(db: Session, task: Task, data: TaskUpdate) -> Task:
    return _apply_changes(db, task, data.model_dump(exclude_unset=True))


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()


def _apply_changes(db: Session, task: Task, changes: dict) -> Task:
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task
