import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_report_task_persists_steps_across_service_reload(tmp_path, monkeypatch) -> None:
    import app.memory.store as store
    import app.services.report_tasks as report_tasks

    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "tasks.sqlite3")
    task = report_tasks.create_task(
        "task-1",
        {
            "company_name": "PersistCo",
            "symbol": "NASDAQ:PERSIST",
            "yahoo_symbol": "PERSIST",
            "data_provider": "auto",
        },
    )

    assert task["task_id"] == "task-1"
    assert task["status"] == "queued"
    assert [step["name"] for step in task["steps"]] == [
        "queued",
        "fetch_market",
        "fetch_financials",
        "rag_search",
        "agent_analysis",
        "report_render",
        "completed",
        "failed",
    ]
    assert task["steps"][0]["status"] == "success"
    assert task["steps"][0]["started_at"]
    assert task["steps"][0]["finished_at"]

    report_tasks.start_step("task-1", "fetch_market", "Fetching market profile.")
    report_tasks.finish_step("task-1", "fetch_market", "Market profile ready.")
    report_tasks.start_step("task-1", "fetch_financials", "Fetching financial profile.")
    report_tasks.finish_step("task-1", "fetch_financials", "Financial profile ready.")

    reloaded = importlib.reload(report_tasks)
    persisted = reloaded.get_task("task-1")

    assert persisted is not None
    assert persisted["request"]["company_name"] == "PersistCo"
    assert persisted["steps"][1]["status"] == "success"
    assert persisted["steps"][1]["message"] == "Market profile ready."
    assert persisted["steps"][2]["status"] == "success"


def test_report_task_failure_records_failed_step_and_task_error(tmp_path, monkeypatch) -> None:
    import app.memory.store as store
    import app.services.report_tasks as report_tasks

    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "tasks.sqlite3")
    report_tasks.create_task("task-2", {"company_name": "FailureCo"})
    report_tasks.start_step("task-2", "agent_analysis", "Running agents.")
    report_tasks.fail_task("task-2", "LLMProviderError: unavailable", failed_step="agent_analysis")

    task = report_tasks.get_task("task-2")
    agent_step = next(step for step in task["steps"] if step["name"] == "agent_analysis")
    failed_step = next(step for step in task["steps"] if step["name"] == "failed")

    assert task["status"] == "failed"
    assert task["error"] == "LLMProviderError: unavailable"
    assert agent_step["status"] == "failed"
    assert agent_step["error"] == "LLMProviderError: unavailable"
    assert failed_step["status"] == "failed"
    assert failed_step["finished_at"]
