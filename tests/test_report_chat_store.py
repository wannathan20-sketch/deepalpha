import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch) -> None:
    import app.memory.store as store

    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "report_chat_store.sqlite3")


def test_report_chat_history_is_isolated_by_user_and_task() -> None:
    from app.services.report_chat_store import get_history, save_turn

    save_turn("user-a", "task-1", "Tesla", "Q1", {"answer": "A1"}, "general", "auto", {})
    save_turn("user-b", "task-1", "Tesla", "Q2", {"answer": "A2"}, "risk", "auto", {})

    assert [item["question"] for item in get_history("user-a", "task-1")] == ["Q1"]
    assert [item["question"] for item in get_history("user-b", "task-1")] == ["Q2"]
    assert get_history("user-a", "task-2") == []


def test_recent_context_returns_only_last_six_complete_turns() -> None:
    from app.services.report_chat_store import get_recent_turns, save_turn

    for index in range(7):
        save_turn(
            "user-a",
            "task-1",
            "Tesla",
            f"Q{index}",
            {"answer": f"A{index}", "key_points": [], "risks": [], "report_citations": []},
            "general",
            "report_only",
            {},
        )

    turns = get_recent_turns("user-a", "task-1", limit=6)

    assert [turn["question"] for turn in turns] == [f"Q{index}" for index in range(1, 7)]


def test_save_turn_writes_user_and_assistant_messages_atomically() -> None:
    from app.memory.store import _connect
    from app.services.report_chat_store import save_turn

    save_turn(
        "user-a",
        "task-1",
        "Tesla",
        "Question",
        {"answer": "Answer"},
        "general",
        "auto",
        {"mode": "report_qa"},
    )

    with _connect() as connection:
        rows = connection.execute(
            "SELECT role FROM report_chat_messages ORDER BY created_at, rowid"
        ).fetchall()

    assert [row["role"] for row in rows] == ["user", "assistant"]


def test_delete_history_only_deletes_current_user_session() -> None:
    from app.services.report_chat_store import delete_history, get_history, save_turn

    save_turn("user-a", "task-1", "Tesla", "Q1", {"answer": "A1"}, "general", "auto", {})
    save_turn("user-b", "task-1", "Tesla", "Q2", {"answer": "A2"}, "general", "auto", {})

    assert delete_history("user-a", "task-1") is True
    assert get_history("user-a", "task-1") == []
    assert len(get_history("user-b", "task-1")) == 1
