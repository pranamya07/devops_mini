"""Unit tests for request validation (no database, no HTTP)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    TaskCreate,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)


class TestTaskCreate:
    def test_minimal_task_gets_defaults(self):
        task = TaskCreate(title="Write tests")

        assert task.status is TaskStatus.TODO
        assert task.priority is TaskPriority.MEDIUM
        assert task.description is None
        assert task.due_date is None

    def test_all_fields_are_parsed(self):
        task = TaskCreate(
            title="Deploy",
            description="Ship v1.1.0",
            status="in_progress",
            priority="high",
            due_date="2026-12-31",
        )

        assert task.status is TaskStatus.IN_PROGRESS
        assert task.priority is TaskPriority.HIGH
        assert task.due_date == date(2026, 12, 31)

    def test_title_is_trimmed(self):
        assert TaskCreate(title="  Review PR  ").title == "Review PR"

    def test_title_at_max_length_is_accepted(self):
        title = "x" * TITLE_MAX_LENGTH
        assert TaskCreate(title=title).title == title

    def test_description_at_max_length_is_accepted(self):
        text = "d" * DESCRIPTION_MAX_LENGTH
        assert TaskCreate(title="t", description=text).description == text

    @pytest.mark.parametrize(
        ("payload", "bad_field"),
        [
            ({}, "title"),
            ({"title": ""}, "title"),
            ({"title": "   "}, "title"),
            ({"title": "x" * (TITLE_MAX_LENGTH + 1)}, "title"),
            ({"title": 123}, "title"),
            ({"title": "t", "description": "d" * (DESCRIPTION_MAX_LENGTH + 1)}, "description"),
            ({"title": "t", "status": "later"}, "status"),
            ({"title": "t", "priority": "urgent"}, "priority"),
            ({"title": "t", "due_date": "31-12-2026"}, "due_date"),
            ({"title": "t", "owner": "alex"}, "owner"),
        ],
        ids=[
            "missing-title",
            "empty-title",
            "blank-title",
            "title-too-long",
            "title-not-a-string",
            "description-too-long",
            "unknown-status",
            "unknown-priority",
            "bad-date-format",
            "unknown-field",
        ],
    )
    def test_invalid_input_is_rejected(self, payload, bad_field):
        with pytest.raises(ValidationError) as error:
            TaskCreate(**payload)

        failed_fields = {err["loc"][0] for err in error.value.errors()}
        assert bad_field in failed_fields


class TestTaskUpdate:
    def test_empty_update_is_allowed(self):
        assert TaskUpdate().model_dump(exclude_unset=True) == {}

    def test_only_sent_fields_are_included(self):
        update = TaskUpdate(status="done")
        assert update.model_dump(exclude_unset=True) == {"status": TaskStatus.DONE}

    def test_description_and_due_date_can_be_cleared(self):
        update = TaskUpdate(description=None, due_date=None)
        assert update.model_dump(exclude_unset=True) == {"description": None, "due_date": None}

    @pytest.mark.parametrize("field", ["title", "status", "priority"])
    def test_required_fields_cannot_be_set_to_null(self, field):
        with pytest.raises(ValidationError, match=f"{field} cannot be null"):
            TaskUpdate(**{field: None})

    def test_blank_title_is_rejected(self):
        with pytest.raises(ValidationError):
            TaskUpdate(title="  ")

    def test_unknown_field_is_rejected(self):
        with pytest.raises(ValidationError):
            TaskUpdate(done=True)
