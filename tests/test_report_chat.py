import json
import sys
from pathlib import Path
from unittest.mock import ANY

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

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
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
        "message_id": ANY,
        "route": ANY,
        "report_citations": [],
        "web_citations": [],
        "freshness": ANY,
    }
    assert "321.5" in captured["prompt"]
    assert "gross_margin_percent" in captured["prompt"]
    assert "Company filing" in captured["prompt"]
    assert "Strategy: risk" in captured["prompt"]
    assert "only the supplied report context" in captured["system_prompt"]


def test_report_chat_accepts_direct_markdown(monkeypatch) -> None:
    captured = {}

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
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

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
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
    _completed_task()
    def fail_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
        raise LLMProviderError("LLM provider unavailable")

    monkeypatch.setattr("app.llm.client.generate_text", fail_generate_text)

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "What changed?",
            "task_id": "chat-task",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "LLM provider unavailable"}
    assert client.get("/chat/report/chat-task/history").json()["items"] == []


def test_report_chat_returns_503_for_invalid_llm_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: "not-json",
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


def test_report_chat_uses_structured_development_fallback_when_provider_fails(monkeypatch) -> None:
    _completed_task()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.llm.client._generate_with_openai_compatible",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "继续追问一下风险",
            "task_id": "chat-task",
            "search_mode": "report_only",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"]
    assert response.json()["data_quality_warning"]
    assert response.json()["message_id"]


def test_temporal_question_auto_searches_and_returns_web_citations(monkeypatch) -> None:
    _completed_task()
    monkeypatch.setattr(
        "app.services.report_chat.search_public_info",
        lambda query, limit=5: [
            {
                "title": "Latest filing update",
                "url": "https://example.com/latest",
                "snippet": "A new filing was published.",
                "published_at": "2026-06-24",
                "provider": "tavily",
            }
        ],
    )
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "A new filing was published.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "report_citations": [],
                "web_citations": [{"url": "https://example.com/latest"}],
                "data_quality_warning": "",
            }
        ),
    )

    response = client.post(
        "/chat/report",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={
            "company_name": "Tesla",
            "question": "今天有没有最新消息？",
            "task_id": "chat-task",
            "search_mode": "auto",
        },
    )

    assert response.status_code == 200
    assert response.json()["route"]["mode"] == "report_web_qa"
    assert response.json()["route"]["web_status"] == "success"
    assert response.json()["web_citations"][0]["url"] == "https://example.com/latest"
    assert response.json()["freshness"]["web_retrieved_at"]


def test_web_search_failure_degrades_to_report_context(monkeypatch) -> None:
    from app.errors import SearchProviderError

    _completed_task()
    monkeypatch.setattr(
        "app.services.report_chat.search_public_info",
        lambda query, limit=5: (_ for _ in ()).throw(SearchProviderError("search down")),
    )
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "Only the saved report can be confirmed.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        ),
    )

    response = client.post(
        "/chat/report",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={
            "company_name": "Tesla",
            "question": "最新情况如何？",
            "task_id": "chat-task",
        },
    )

    assert response.status_code == 200
    assert response.json()["route"]["web_status"] == "failed"
    assert "search down" in response.json()["data_quality_warning"]


def test_task_chat_persists_history_and_isolates_users(monkeypatch) -> None:
    _completed_task()
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "Persistent answer.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        ),
    )

    created = client.post(
        "/chat/report",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={
            "company_name": "Tesla",
            "question": "Remember this?",
            "task_id": "chat-task",
            "search_mode": "report_only",
        },
    )
    history_a = client.get(
        "/chat/report/chat-task/history",
        headers={"X-DeepAlpha-User-Id": "user-a"},
    )
    history_b = client.get(
        "/chat/report/chat-task/history",
        headers={"X-DeepAlpha-User-Id": "user-b"},
    )

    assert created.status_code == 200
    assert history_a.status_code == 200
    assert history_a.json()["items"][0]["question"] == "Remember this?"
    assert history_b.json()["items"] == []


def test_history_delete_only_clears_current_user(monkeypatch) -> None:
    _completed_task()
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "Answer.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        ),
    )
    for user in ("user-a", "user-b"):
        client.post(
            "/chat/report",
            headers={"X-DeepAlpha-User-Id": user},
            json={"company_name": "Tesla", "question": user, "task_id": "chat-task"},
        )

    deleted = client.delete(
        "/chat/report/chat-task/history",
        headers={"X-DeepAlpha-User-Id": "user-a"},
    )

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(
        "/chat/report/chat-task/history",
        headers={"X-DeepAlpha-User-Id": "user-a"},
    ).json()["items"] == []
    assert len(client.get(
        "/chat/report/chat-task/history",
        headers={"X-DeepAlpha-User-Id": "user-b"},
    ).json()["items"]) == 1


def test_seventh_question_prompt_contains_only_recent_six_turns(monkeypatch) -> None:
    _completed_task()
    prompts = []

    def fake_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
        prompts.append(prompt)
        return json.dumps(
            {
                "answer": "Answer.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        )

    monkeypatch.setattr("app.llm.client.generate_text", fake_generate_text)
    for index in range(8):
        response = client.post(
            "/chat/report",
            headers={"X-DeepAlpha-User-Id": "user-a"},
            json={
                "company_name": "Tesla",
                "question": f"Question-{index}",
                "task_id": "chat-task",
                "search_mode": "report_only",
            },
        )
        assert response.status_code == 200

    assert "Question-0" not in prompts[-1]
    assert "Question-1" in prompts[-1]
    assert "Question-6" in prompts[-1]


def test_direct_markdown_chat_does_not_create_history(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "Stateless.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "data_quality_warning": "",
            }
        ),
    )

    response = client.post(
        "/chat/report",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={
            "company_name": "MarkdownCo",
            "question": "Question",
            "markdown_report": "# Report",
        },
    )

    assert response.status_code == 200
    assert response.json()["message_id"] is None


def test_report_chat_filters_fabricated_section_citations(monkeypatch) -> None:
    _completed_task()
    monkeypatch.setattr(
        "app.llm.client.generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "Answer.",
                "key_points": [],
                "risks": [],
                "cited_sources": [],
                "report_citations": [
                    {
                        "section_id": "report-section-1-tesla-report",
                        "section_title": "Tesla report",
                        "excerpt": "Revenue improved while margin risk remains.",
                        "url": "https://example.com/filing",
                    },
                    {
                        "section_id": "report-section-1-tesla-report",
                        "section_title": "Tesla report",
                        "excerpt": "Fabricated evidence.",
                        "url": "",
                    },
                ],
                "data_quality_warning": "",
            }
        ),
    )

    response = client.post(
        "/chat/report",
        json={
            "company_name": "Tesla",
            "question": "Cite the report.",
            "task_id": "chat-task",
            "search_mode": "report_only",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["report_citations"]) == 1
    assert response.json()["report_citations"][0]["excerpt"].startswith("Revenue improved")
