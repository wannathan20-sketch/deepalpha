from datetime import datetime, timezone
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_trace(company_name: str) -> dict:
    started_at = _now_iso()

    return {
        "trace_id": str(uuid4()),
        "company_name": company_name,
        "steps": [],
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
    }


def add_trace_step(
    trace: dict,
    step_name: str,
    status: str,
    detail: str = "",
) -> None:
    trace["steps"].append(
        {
            "step_name": step_name,
            "status": status,
            "detail": detail,
            "timestamp": _now_iso(),
        }
    )


def finish_trace(trace: dict) -> dict:
    finished_at = _now_iso()
    started_at = datetime.fromisoformat(trace["started_at"])
    finished_at_datetime = datetime.fromisoformat(finished_at)

    trace["finished_at"] = finished_at
    trace["duration_seconds"] = round(
        (finished_at_datetime - started_at).total_seconds(),
        4,
    )

    return trace
