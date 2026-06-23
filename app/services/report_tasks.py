import json
from copy import deepcopy

from app.memory.store import _connect, _now_iso


STEP_NAMES = [
    "queued",
    "fetch_market",
    "fetch_financials",
    "rag_search",
    "agent_analysis",
    "report_render",
    "completed",
    "failed",
]


def _initial_steps() -> list[dict]:
    now = _now_iso()
    steps = [
        {
            "name": name,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "message": "",
            "error": None,
        }
        for name in STEP_NAMES
    ]
    steps[0].update(
        {
            "status": "success",
            "started_at": now,
            "finished_at": now,
            "message": "Task queued.",
        }
    )
    return steps


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: object) -> object:
    if not value:
        return deepcopy(default)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return deepcopy(default)


def _row_to_task(row) -> dict | None:
    if row is None:
        return None
    return {
        "task_id": row["task_id"],
        "status": row["status"],
        "request": _json_load(row["request_json"], {}),
        "result": _json_load(row["result_json"], None),
        "error": row["error"],
        "steps": _json_load(row["steps_json"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _step_index(steps: list[dict], step_name: str) -> int:
    for index, step in enumerate(steps):
        if step.get("name") == step_name:
            return index
    raise ValueError(f"Unknown report task step: {step_name}")


def _update_task(task_id: str, *, status: str | None = None, result=None, error: str | None = None, steps: list[dict] | None = None) -> dict:
    current = get_task(task_id)
    if current is None:
        raise KeyError(task_id)

    next_status = status if status is not None else current["status"]
    next_result = result if result is not None else current["result"]
    next_error = error if error is not None else current["error"]
    next_steps = steps if steps is not None else current["steps"]
    updated_at = _now_iso()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE report_tasks
            SET status = ?, result_json = ?, error = ?, steps_json = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                next_status,
                _json_dump(next_result) if next_result is not None else None,
                next_error,
                _json_dump(next_steps),
                updated_at,
                task_id,
            ),
        )

    return get_task(task_id)


def create_task(task_id: str, request: dict) -> dict:
    now = _now_iso()
    steps = _initial_steps()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO report_tasks (
                task_id, status, request_json, result_json, error, steps_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                "queued",
                _json_dump(request),
                None,
                None,
                _json_dump(steps),
                now,
                now,
            ),
        )
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT task_id, status, request_json, result_json, error, steps_json, created_at, updated_at
            FROM report_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
    return _row_to_task(row)


def start_step(task_id: str, step_name: str, message: str = "") -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    steps = task["steps"]
    step = steps[_step_index(steps, step_name)]
    now = _now_iso()
    step.update(
        {
            "status": "running",
            "started_at": step.get("started_at") or now,
            "finished_at": None,
            "message": message,
            "error": None,
        }
    )
    return _update_task(task_id, status="running", steps=steps)


def finish_step(task_id: str, step_name: str, message: str = "") -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    steps = task["steps"]
    step = steps[_step_index(steps, step_name)]
    now = _now_iso()
    step.update(
        {
            "status": "success",
            "started_at": step.get("started_at") or now,
            "finished_at": now,
            "message": message or step.get("message", ""),
            "error": None,
        }
    )
    return _update_task(task_id, status="running", steps=steps)


def fail_task(task_id: str, error: str, *, failed_step: str = "failed") -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    steps = task["steps"]
    now = _now_iso()
    if failed_step in STEP_NAMES and failed_step != "failed":
        step = steps[_step_index(steps, failed_step)]
        step.update(
            {
                "status": "failed",
                "started_at": step.get("started_at") or now,
                "finished_at": now,
                "message": "Step failed.",
                "error": error,
            }
        )

    failed = steps[_step_index(steps, "failed")]
    failed.update(
        {
            "status": "failed",
            "started_at": failed.get("started_at") or now,
            "finished_at": now,
            "message": "Task failed.",
            "error": error,
        }
    )
    return _update_task(task_id, status="failed", error=error, steps=steps)


def complete_task(task_id: str, result: dict) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    steps = task["steps"]
    now = _now_iso()
    completed = steps[_step_index(steps, "completed")]
    completed.update(
        {
            "status": "success",
            "started_at": completed.get("started_at") or now,
            "finished_at": now,
            "message": "Task completed.",
            "error": None,
        }
    )
    return _update_task(task_id, status="success", result=result, error=None, steps=steps)
