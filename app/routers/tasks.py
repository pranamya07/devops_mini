import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import Task
from app.observability import TASK_OPERATIONS
from app.schemas import TaskCreate, TaskPriority, TaskRead, TaskStatus, TaskUpdate

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
logger = logging.getLogger("app.tasks")

DbSession = Annotated[Session, Depends(get_db)]
TaskId = Annotated[int, Path(gt=0, description="ID of the task")]

NOT_FOUND = {404: {"description": "Task not found"}}


def get_task_or_404(task_id: TaskId, db: DbSession) -> Task:
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


ExistingTask = Annotated[Task, Depends(get_task_or_404)]


@router.post("", response_model=TaskRead, status_code=201)
def create_task(data: TaskCreate, db: DbSession, response: Response):
    task = crud.create_task(db, data)
    TASK_OPERATIONS.labels("create").inc()
    logger.info("Task created id=%s priority=%s", task.id, task.priority.value)
    response.headers["Location"] = f"{router.prefix}/{task.id}"
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    db: DbSession,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return crud.list_tasks(db, status=status, priority=priority, limit=limit, offset=offset)


@router.get("/{task_id}", response_model=TaskRead, responses=NOT_FOUND)
def get_task(task: ExistingTask):
    return task


@router.put("/{task_id}", response_model=TaskRead, responses=NOT_FOUND)
def replace_task(data: TaskCreate, task: ExistingTask, db: DbSession):
    task = crud.replace_task(db, task, data)
    TASK_OPERATIONS.labels("replace").inc()
    logger.info("Task replaced id=%s", task.id)
    return task


@router.patch("/{task_id}", response_model=TaskRead, responses=NOT_FOUND)
def update_task(data: TaskUpdate, task: ExistingTask, db: DbSession):
    changed = sorted(data.model_fields_set)
    task = crud.update_task(db, task, data)
    TASK_OPERATIONS.labels("update").inc()
    logger.info("Task updated id=%s fields=%s", task.id, ",".join(changed) or "none")
    return task


@router.delete("/{task_id}", status_code=204, responses=NOT_FOUND)
def delete_task(task: ExistingTask, db: DbSession):
    task_id = task.id
    crud.delete_task(db, task)
    TASK_OPERATIONS.labels("delete").inc()
    logger.info("Task deleted id=%s", task_id)
