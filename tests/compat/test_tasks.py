"""
Suite: Task State Machine (ACP spec §5)
Tests task CRUD and the 5-state machine: submitted→working→completed/failed/input_required.
"""
import uuid
import time
from compat_base import Compat


class TasksSuite(Compat):
    SUITE_NAME = "Task State Machine"

    def run(self) -> None:
        # ── Create task ───────────────────────────────────────────────────────
        task_body = {
            "title": "compat-test-task",
            "description": "Created by ACP compatibility suite",
            "input": {"type": "text", "content": "test input"},
        }
        s_create, r_create = self.post("/tasks", task_body)

        self.check("POST /tasks returns 200 or 201",
                   s_create in (200, 201), "MUST",
                   f"got {s_create}")

        if s_create not in (200, 201) or not isinstance(r_create, dict):
            # Can't test further without a task
            for n in ["task has 'id'", "task has 'status'",
                      "initial status is 'submitted'",
                      "GET /tasks/{id} returns task",
                      "task status is valid enum"]:
                self.check(n, False, "MUST", "skipped: task creation failed")
            return

        task_id = r_create.get("id") or r_create.get("task_id")
        self.check("task has 'id'",
                   isinstance(task_id, str) and len(task_id) > 0,
                   "MUST")

        self.check("task has 'status'",
                   "status" in r_create,
                   "MUST")

        initial_status = r_create.get("status")
        self.check("initial status is 'submitted' or 'working'",
                   initial_status in ("submitted", "working"),
                   "MUST",
                   f"got '{initial_status}'")

        # ── GET task ──────────────────────────────────────────────────────────
        if task_id:
            s_get, r_get = self.get(f"/tasks/{task_id}")
            self.check("GET /tasks/{id} returns 200",
                       s_get == 200, "MUST",
                       f"got {s_get}")

            if isinstance(r_get, dict):
                valid_states = {"submitted", "working", "completed", "failed", "input_required"}
                self.check("task status is valid ACP enum",
                           r_get.get("status") in valid_states,
                           "MUST",
                           f"got '{r_get.get('status')}' — valid: {valid_states}")

        # ── List tasks ────────────────────────────────────────────────────────
        s_list, r_list = self.get("/tasks")
        self.check("GET /tasks returns 200",
                   s_list == 200, "MUST",
                   f"got {s_list}")
        self.check("GET /tasks returns a list",
                   isinstance(r_list, list), "MUST")

        # ── Cancel task ───────────────────────────────────────────────────────
        if task_id:
            s_cancel, r_cancel = self.post(f"/tasks/{task_id}/cancel", {})
            self.check("POST /tasks/{id}/cancel returns 200",
                       s_cancel == 200, "MUST",
                       f"got {s_cancel}")

            # After cancel, status should be 'failed' (ACP uses failed for terminal states)
            s_after, r_after = self.get(f"/tasks/{task_id}")
            if s_after == 200 and isinstance(r_after, dict):
                self.check("cancelled task has terminal status",
                           r_after.get("status") in ("failed", "completed"),
                           "SHOULD",
                           f"got '{r_after.get('status')}'")

        # ── GET non-existent task → 404 ───────────────────────────────────────
        s_404, r_404 = self.get(f"/tasks/nonexistent_{uuid.uuid4().hex[:8]}")
        self.check("GET /tasks/{unknown_id} returns 404",
                   s_404 == 404, "MUST",
                   f"got {s_404}")

        # ── Error format on 404 ───────────────────────────────────────────────
        if isinstance(r_404, dict):
            self.check("404 response has 'error_code' field",
                       "error_code" in r_404,
                       "SHOULD",
                       "ACP error format: {error_code, message, ...}")
