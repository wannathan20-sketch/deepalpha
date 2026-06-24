import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.errors import LLMProviderError
from app.main import app
from app.services import report_tasks


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch) -> None:
    import app.memory.store as store

    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "report_chat.sqlite3")


def _completed_task(task_id: str = "chat-task") -> dict:
    report_tasks.create_task(task_id, {"company_name": "Tesla"})
    return report_tasks.complete_task(
        task_id,
        {
            "thread_id": "thread-1",
            "company_name": "Tesla",
            "status": "success",
            "final_report": {"recommendation": "watchlist"},
            "markdown_report": (
                "# Tesla report\n"
                "Revenue improved while margin risk remains.\n"
                "Source: https://example.com/filing"
            ),
            "report_editor": {},
            "source_quality": {
                "grade_counts": {"A": 1, "B": 0, "C": 0, "D": 0},
                "source_ratings": [
                    {
                        "title": "Company filing",
                        "url": "https://example.com/filing",
                        "grade": "A",
                    }
                ],
            },
            "market_profile": {
                "enabled": True,
                "latest_close": 321.5,
                "trend": "uptrend",
            },
            "financial_profile": {
                "enabled": True,
                "revenue": 1000,
                "gross_margin_percent": 21.5,
            },
            "citation_check": {},
            "trace_summary": {},
        },
    )


def test_report_chat_uses_completed_task_context_and_filters_citations(monkeypatch) -> None:
    _completed_task()
    captured = {}

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return json.dumps(
            {
                "answer": "Margin pressure is the main near-term concern.",
                "key_points": ["Revenue improved.", "Price trend is positive."],
                "risks": ["Margins may contract."],
                "cited_sources": [
                    {"title": "Company filing", "url": "https://example.com/filing"},
                    {"title": "Invented source", "url": "https://invented.example/source"},
                ],
                "data_quality_warning": "The report may not include post-report events.",
            }
        )

    monkeypatch.setattr("app.llm.client.generate_text", fake_generate_text)

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What is the biggest risk?",
            "task_id": "chat-task",
            "strategy": "risk",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Margin pressure is the main near-term concern.",
        "key_points": ["Revenue improved.", "Price trend is positive."],
        "risks": ["Margins may contract."],
        "cited_sources": [
            {"title": "Company filing", "url": "https://example.com/filing"}
        ],
        "data_quality_warning": "The report may not include post-report events.",
    }
    assert "321.5" in captured["prompt"]
    assert "gross_margin_percent" in captured["prompt"]
    assert "Company filing" in captured["prompt"]
    assert "Strategy: risk" in captured["prompt"]
    assert "only the supplied report context" in captured["system_prompt"]


def test_report_chat_accepts_direct_markdown(monkeypatch) -> None:
    captured = {}

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "answer": "The report supports a cautious view.",
                "key_points": ["Cash flow is stable."],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "Only submitted Markdown was available.",
            }
        )

    monkeypatch.setattr("app.llm.client.generate_text", fake_generate_text)

    response = client.post(
        "/chat/report",
        json={
            "company_name": "MarkdownCo",
            "question": "Summarize the conclusion.",
            "markdown_report": "# Report\nCash flow is stable.",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "The report supports a cautious view."
    assert "Cash flow is stable." in captured["prompt"]
    assert '"market_profile": {}' in captured["prompt"]
    assert '"financial_profile": {}' in captured["prompt"]


def test_report_chat_requires_report_context() -> None:
    response = client.post(
        "/chat/report",
        json={"company_name": "Tesla", "question": "What changed?"},
    )

    assert response.status_code == 422


def test_report_chat_returns_404_for_missing_task() -> None:
    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "task_id": "missing-task",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Report task not found"}


def test_report_chat_rejects_unfinished_task() -> None:
    report_tasks.create_task("queued-task", {"company_name": "Tesla"})

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "task_id": "queued-task",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Report task is not completed"}


@pytest.mark.parametrize("strategy", ["general", "risk", "valuation", "technical", "news"])
def test_report_chat_supports_strategy_focus(monkeypatch, strategy: str) -> None:
    prompts = []

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
        prompts.append(prompt)
        return json.dumps(
            {
                "answer": "Focused answer.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        )

    monkeypatch.setattr("app.llm.client.generate_text", fake_generate_text)

    response = client.post(
        "/chat/report",
        json={
            "company_name": "StrategyCo",
            "question": "Give me the focused view.",
            "markdown_report": "# StrategyCo report",
            "strategy": strategy,
        },
    )

    assert response.status_code == 200
    assert f"Strategy: {strategy}" in prompts[0]


def test_report_chat_rejects_unknown_strategy() -> None:
    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "markdown_report": "# Report",
            "strategy": "momentum",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question", "q" * 4001),
        ("markdown_report", "r" * 100_001),
    ],
)
def test_report_chat_rejects_oversized_input(field: str, value: str) -> None:
    payload = {
        "company_name": "Tesla",
        "question": "What changed?",
        "markdown_report": "# Report",
    }
    payload[field] = value

    response = client.post("/chat/report", json=payload)

    assert response.status_code == 422


def test_report_chat_returns_503_when_llm_fails(monkeypatch) -> None:
    def fail_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
        raise LLMProviderError("LLM provider unavailable")

    monkeypatch.setattr("app.llm.client.generate_text", fail_generate_text)

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "markdown_report": "# Report",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "LLM provider unavailable"}


def test_report_chat_returns_503_for_invalid_llm_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda prompt, system_prompt="", max_tokens=800: "not-json",
    )

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "markdown_report": "# Report",
        },
    )

    assert response.status_code == 503
    assert "invalid JSON" in response.json()["detail"]
