"""
Tests for the tasks API endpoints.
"""
import pytest

import mock_data


@pytest.fixture(autouse=True)
def clear_tasks():
    """Tasks are module-level state; isolate every test from the others."""
    mock_data.tasks.clear()
    yield
    mock_data.tasks.clear()


def make_task(client, **overrides):
    payload = {"title": "Review stock levels", "priority": "high", "dueDate": "2025-10-08"}
    payload.update(overrides)
    return client.post("/api/tasks", json=payload)


class TestTasksEndpoints:
    """Test suite for /api/tasks endpoints."""

    def test_get_tasks_empty_by_default(self, client):
        """Test that no tasks exist before any are created."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task returns 201 and the frontend task shape."""
        response = make_task(client)
        assert response.status_code == 201

        task = response.json()
        assert isinstance(task["id"], str)
        assert task["title"] == "Review stock levels"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"

    def test_create_task_trims_title(self, client):
        """Test that surrounding whitespace is stripped from the title."""
        response = make_task(client, title="  Approve order  ")
        assert response.status_code == 201
        assert response.json()["title"] == "Approve order"

    def test_create_task_default_priority(self, client):
        """Test that priority defaults to medium when omitted."""
        response = client.post("/api/tasks", json={"title": "No priority", "dueDate": "2025-10-08"})
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    @pytest.mark.parametrize("overrides", [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"priority": "urgent"},
        {"dueDate": "not-a-date"},
        {"dueDate": "2025-13-45"},
    ])
    def test_create_task_invalid_input_rejected(self, client, overrides):
        """Test that invalid titles, priorities and dates are rejected."""
        response = make_task(client, **overrides)
        assert response.status_code == 422
        assert client.get("/api/tasks").json() == []

    def test_create_task_missing_due_date_rejected(self, client):
        """Test that dueDate is required."""
        response = client.post("/api/tasks", json={"title": "No date"})
        assert response.status_code == 422

    def test_get_tasks_newest_first(self, client):
        """Test that tasks come back newest first."""
        first = make_task(client, title="first").json()
        second = make_task(client, title="second").json()

        data = client.get("/api/tasks").json()
        assert [t["id"] for t in data] == [second["id"], first["id"]]

    def test_task_ids_unique(self, client):
        """Test that every created task gets a distinct id."""
        ids = [make_task(client, title=f"task {i}").json()["id"] for i in range(5)]
        assert len(set(ids)) == 5

    def test_task_ids_do_not_collide_with_builtin_frontend_tasks(self, client):
        """Test that ids can never equal the frontend's built-in integer ids (1-4)."""
        task_id = make_task(client).json()["id"]
        assert not task_id.isdigit()

    def test_task_id_not_reused_after_delete(self, client):
        """Test that deleting a task does not free its id for the next task."""
        first = make_task(client, title="first").json()
        second = make_task(client, title="second").json()
        client.delete(f"/api/tasks/{first['id']}")

        third = make_task(client, title="third").json()
        assert third["id"] not in (first["id"], second["id"])

    def test_toggle_task(self, client):
        """Test toggling flips pending to completed and back."""
        task = make_task(client).json()

        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.json()["status"] == "pending"

    def test_toggle_persists(self, client):
        """Test that a toggled status is visible on the next list call."""
        task = make_task(client).json()
        client.patch(f"/api/tasks/{task['id']}")

        data = client.get("/api/tasks").json()
        assert data[0]["status"] == "completed"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_task(self, client):
        """Test deleting a task removes it and returns it."""
        task = make_task(client).json()

        response = client.delete(f"/api/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == task["id"]
        assert client.get("/api/tasks").json() == []

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_twice_returns_404(self, client):
        """Test that a second delete of the same task is a 404, not a crash."""
        task = make_task(client).json()
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 200
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 404
