"""API tests for /api/v1/tasks: every CRUD route, its errors and edge cases."""

import pytest

TASKS = "/api/v1/tasks"


class TestCreateTask:
    def test_returns_201_with_the_new_task(self, client):
        response = client.post(TASKS, json={"title": "Write Dockerfile"})

        assert response.status_code == 201
        task = response.json()
        assert task["id"] > 0
        assert task["title"] == "Write Dockerfile"
        assert task["status"] == "todo"
        assert task["priority"] == "medium"
        assert task["description"] is None
        assert task["due_date"] is None
        assert task["created_at"] and task["updated_at"]

    def test_sets_location_header(self, client):
        response = client.post(TASKS, json={"title": "t"})
        assert response.headers["location"] == f"{TASKS}/{response.json()['id']}"

    def test_accepts_every_field(self, client):
        payload = {
            "title": "Release v1.1.0",
            "description": "Tag and deploy",
            "status": "in_progress",
            "priority": "high",
            "due_date": "2026-12-15",
        }

        task = client.post(TASKS, json=payload).json()

        assert {key: task[key] for key in payload} == payload

    def test_ids_are_unique(self, make_task):
        ids = {make_task(title=f"task {n}")["id"] for n in range(5)}
        assert len(ids) == 5

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"title": ""},
            {"title": "   "},
            {"title": "x" * 201},
            {"title": None},
            {"title": "t", "status": "later"},
            {"title": "t", "priority": "urgent"},
            {"title": "t", "due_date": "tomorrow"},
            {"title": "t", "id": 99},
        ],
        ids=[
            "missing-title",
            "empty-title",
            "blank-title",
            "title-too-long",
            "null-title",
            "bad-status",
            "bad-priority",
            "bad-date",
            "client-chosen-id",
        ],
    )
    def test_invalid_body_returns_422(self, client, payload):
        response = client.post(TASKS, json=payload)

        assert response.status_code == 422
        assert "detail" in response.json()

    def test_rejected_task_is_not_saved(self, client):
        client.post(TASKS, json={"title": ""})
        assert client.get(TASKS).json() == []

    def test_malformed_json_returns_422(self, client):
        response = client.post(
            TASKS, content="{not json", headers={"content-type": "application/json"}
        )
        assert response.status_code == 422


class TestListTasks:
    def test_empty_list(self, client):
        response = client.get(TASKS)

        assert response.status_code == 200
        assert response.json() == []

    def test_returns_tasks_in_creation_order(self, client, make_task):
        first, second = make_task(title="first"), make_task(title="second")

        listed = client.get(TASKS).json()

        assert [task["id"] for task in listed] == [first["id"], second["id"]]

    def test_filter_by_status(self, client, make_task):
        make_task(title="a", status="todo")
        done = make_task(title="b", status="done")

        listed = client.get(TASKS, params={"status": "done"}).json()

        assert [task["id"] for task in listed] == [done["id"]]

    def test_filter_by_priority(self, client, make_task):
        high = make_task(title="a", priority="high")
        make_task(title="b", priority="low")

        listed = client.get(TASKS, params={"priority": "high"}).json()

        assert [task["id"] for task in listed] == [high["id"]]

    def test_filters_combine(self, client, make_task):
        make_task(title="a", status="done", priority="low")
        match = make_task(title="b", status="done", priority="high")
        make_task(title="c", status="todo", priority="high")

        listed = client.get(TASKS, params={"status": "done", "priority": "high"}).json()

        assert [task["id"] for task in listed] == [match["id"]]

    def test_pagination(self, client, make_task):
        ids = [make_task(title=f"task {n}")["id"] for n in range(5)]

        page = client.get(TASKS, params={"limit": 2, "offset": 2}).json()

        assert [task["id"] for task in page] == ids[2:4]

    def test_offset_past_the_end_is_empty(self, client, make_task):
        make_task()
        assert client.get(TASKS, params={"offset": 10}).json() == []

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
            {"limit": "ten"},
            {"status": "later"},
            {"priority": "urgent"},
        ],
    )
    def test_invalid_query_returns_422(self, client, params):
        assert client.get(TASKS, params=params).status_code == 422


class TestGetTask:
    def test_returns_the_task(self, client, make_task):
        created = make_task(title="Read me")

        response = client.get(f"{TASKS}/{created['id']}")

        assert response.status_code == 200
        assert response.json() == created

    def test_missing_task_returns_404(self, client):
        response = client.get(f"{TASKS}/9999")

        assert response.status_code == 404
        assert response.json() == {"detail": "Task 9999 not found"}

    @pytest.mark.parametrize("bad_id", ["0", "-1", "abc", "1.5"])
    def test_invalid_id_returns_422(self, client, bad_id):
        assert client.get(f"{TASKS}/{bad_id}").status_code == 422


class TestReplaceTask:
    def test_put_replaces_every_field(self, client, make_task):
        task = make_task(
            title="Old", description="old notes", priority="high", due_date="2026-12-01"
        )

        response = client.put(f"{TASKS}/{task['id']}", json={"title": "New"})

        assert response.status_code == 200
        replaced = response.json()
        assert replaced["title"] == "New"
        # Fields not sent go back to their defaults.
        assert replaced["description"] is None
        assert replaced["priority"] == "medium"
        assert replaced["due_date"] is None
        assert replaced["created_at"] == task["created_at"]

    def test_put_missing_task_returns_404(self, client):
        assert client.put(f"{TASKS}/9999", json={"title": "x"}).status_code == 404

    def test_put_without_title_returns_422(self, client, make_task):
        task = make_task()
        assert client.put(f"{TASKS}/{task['id']}", json={"status": "done"}).status_code == 422


class TestUpdateTask:
    def test_patch_changes_only_sent_fields(self, client, make_task):
        task = make_task(title="Keep me", description="notes", priority="high")

        response = client.patch(f"{TASKS}/{task['id']}", json={"status": "done"})

        assert response.status_code == 200
        updated = response.json()
        assert updated["status"] == "done"
        assert updated["title"] == "Keep me"
        assert updated["description"] == "notes"
        assert updated["priority"] == "high"

    def test_patch_is_saved(self, client, make_task):
        task = make_task()
        client.patch(f"{TASKS}/{task['id']}", json={"title": "Renamed"})

        assert client.get(f"{TASKS}/{task['id']}").json()["title"] == "Renamed"

    def test_patch_moves_updated_at_forward(self, client, make_task):
        task = make_task()

        updated = client.patch(f"{TASKS}/{task['id']}", json={"priority": "low"}).json()

        assert updated["updated_at"] > task["updated_at"]
        assert updated["created_at"] == task["created_at"]

    def test_patch_can_clear_description(self, client, make_task):
        task = make_task(description="temporary")

        updated = client.patch(f"{TASKS}/{task['id']}", json={"description": None}).json()

        assert updated["description"] is None

    @pytest.mark.parametrize(
        "payload",
        [
            {"title": None},
            {"title": ""},
            {"status": "later"},
            {"priority": None},
            {"colour": "red"},
        ],
    )
    def test_invalid_patch_returns_422(self, client, make_task, payload):
        task = make_task(title="Unchanged")

        assert client.patch(f"{TASKS}/{task['id']}", json=payload).status_code == 422
        assert client.get(f"{TASKS}/{task['id']}").json()["title"] == "Unchanged"

    def test_patch_missing_task_returns_404(self, client):
        assert client.patch(f"{TASKS}/9999", json={"status": "done"}).status_code == 404


class TestDeleteTask:
    def test_delete_returns_204_with_empty_body(self, client, make_task):
        task = make_task()

        response = client.delete(f"{TASKS}/{task['id']}")

        assert response.status_code == 204
        assert response.content == b""

    def test_deleted_task_is_gone(self, client, make_task):
        keep, remove = make_task(title="keep"), make_task(title="remove")

        client.delete(f"{TASKS}/{remove['id']}")

        assert client.get(f"{TASKS}/{remove['id']}").status_code == 404
        assert [task["id"] for task in client.get(TASKS).json()] == [keep["id"]]

    def test_deleting_twice_returns_404(self, client, make_task):
        task = make_task()
        client.delete(f"{TASKS}/{task['id']}")

        assert client.delete(f"{TASKS}/{task['id']}").status_code == 404


def test_full_task_lifecycle(client):
    """Create -> read -> update -> list -> delete, the flow shown in the demo."""
    created = client.post(TASKS, json={"title": "Demo task", "priority": "high"})
    assert created.status_code == 201
    task_url = f"{TASKS}/{created.json()['id']}"

    assert client.get(task_url).json()["title"] == "Demo task"
    assert client.patch(task_url, json={"status": "in_progress"}).json()["status"] == "in_progress"
    assert len(client.get(TASKS, params={"status": "in_progress"}).json()) == 1
    assert client.delete(task_url).status_code == 204
    assert client.get(task_url).status_code == 404


def test_wrong_method_returns_405(client):
    assert client.delete(TASKS).status_code == 405
