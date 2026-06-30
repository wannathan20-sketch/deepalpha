import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_production_runtime_rejects_mock_llm(monkeypatch) -> None:
    from app.config import RuntimeConfigurationError, validate_runtime_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "search-key")

    with pytest.raises(RuntimeConfigurationError, match="LLM_PROVIDER"):
        validate_runtime_config()


def test_production_runtime_rejects_mock_search(monkeypatch) -> None:
    from app.config import RuntimeConfigurationError, validate_runtime_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setenv("SEARCH_PROVIDER", "mock")

    with pytest.raises(RuntimeConfigurationError, match="SEARCH_PROVIDER"):
        validate_runtime_config()


def test_production_runtime_requires_a_usable_search_provider(monkeypatch) -> None:
    from app.config import RuntimeConfigurationError, validate_runtime_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setenv("SEARCH_PROVIDER", "multi")
    monkeypatch.setenv("SEARCH_PROVIDERS", "brave,blockbeats,tavily")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("BLOCKBEATS_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(RuntimeConfigurationError, match="search API key"):
        validate_runtime_config()


def test_production_runtime_accepts_configured_x_search_adapter(monkeypatch) -> None:
    from app.config import validate_runtime_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setenv("SEARCH_PROVIDER", "multi")
    monkeypatch.setenv("SEARCH_PROVIDERS", "x")
    monkeypatch.setenv("X_MCP_SEARCH_URL", "http://127.0.0.1:8787/search")

    validate_runtime_config()


def test_fastapi_startup_validates_production_runtime(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config import RuntimeConfigurationError
    from app.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("SEARCH_PROVIDER", "mock")

    with pytest.raises(RuntimeConfigurationError):
        with TestClient(app):
            pass


def test_production_llm_provider_failure_is_explicit(monkeypatch) -> None:
    from app.llm.client import LLMProviderError, generate_text

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setattr(
        "app.llm.client._generate_with_openai_compatible",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError("provider timeout")),
    )

    with pytest.raises(LLMProviderError, match="deepseek"):
        generate_text("Analyze Tesla")


def test_production_empty_llm_response_is_explicit(monkeypatch) -> None:
    from app.llm.client import LLMProviderError, generate_text

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setattr(
        "app.llm.client._generate_with_openai_compatible",
        lambda **kwargs: "   ",
    )

    with pytest.raises(LLMProviderError, match="empty response"):
        generate_text("Analyze Tesla")


def test_development_mock_llm_remains_available(monkeypatch) -> None:
    from app.llm.client import generate_text

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    assert "Mock LLM response" in generate_text("test prompt")


def test_json_mode_forwards_to_the_provider(monkeypatch) -> None:
    from app.llm.client import generate_text

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return '{"answer":"ok"}'

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setattr("app.llm.client._generate_with_openai_compatible", fake_generate)

    generate_text("Question: risk?", json_mode=True)

    assert captured["json_mode"] is True


def test_json_mode_defaults_to_false(monkeypatch) -> None:
    from app.llm.client import generate_text

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "plain text response"

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "llm-key")
    monkeypatch.setattr("app.llm.client._generate_with_openai_compatible", fake_generate)

    generate_text("Question: risk?")

    assert captured["json_mode"] is False


def test_safe_agent_runner_propagates_llm_provider_errors() -> None:
    from app.errors import LLMProviderError
    from app.utils import safe_run_agent

    def failing_agent(company_name: str, context: dict) -> dict:
        raise LLMProviderError("LLM unavailable")

    with pytest.raises(LLMProviderError, match="LLM unavailable"):
        safe_run_agent("failing", failing_agent, "Tesla", {})


def test_committee_propagates_llm_provider_errors(monkeypatch) -> None:
    from app.agents import committee
    from app.errors import LLMProviderError

    monkeypatch.setattr(
        committee,
        "generate_text",
        lambda **kwargs: (_ for _ in ()).throw(LLMProviderError("LLM unavailable")),
    )

    with pytest.raises(LLMProviderError, match="LLM unavailable"):
        committee.analyze("Tesla", {"agent_outputs": {}})


def test_report_returns_503_for_llm_provider_failure(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.errors import LLMProviderError
    from app.main import app

    monkeypatch.setattr(
        "app.main._run_analysis",
        lambda request: (_ for _ in ()).throw(LLMProviderError("LLM provider unavailable")),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/report", json={"company_name": "Tesla"})

    assert response.status_code == 503
    assert response.json() == {"detail": "LLM provider unavailable"}


def test_production_search_failure_is_explicit(monkeypatch) -> None:
    import requests

    from app.errors import SearchProviderError
    from app.tools.search import search_public_info

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "search-key")
    monkeypatch.setattr(
        "app.tools.search.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("provider timeout")),
    )

    with pytest.raises(SearchProviderError, match="tavily"):
        search_public_info("Tesla earnings")


def test_rag_marks_search_failure_without_mock_documents(monkeypatch) -> None:
    from app.errors import SearchProviderError
    from app.rag.retriever import retrieve_industry_context
    from app.schemas import ContextStatus
    from app.services.analysis_context import build_analysis_context

    monkeypatch.setattr(
        "app.rag.retriever.load_company_industry_docs",
        lambda company_name: (_ for _ in ()).throw(SearchProviderError("search unavailable")),
    )

    rag_context = retrieve_industry_context("Tesla", "Tesla competitors")
    analysis_context = build_analysis_context(
        "Tesla",
        market_profile={},
        financial_profile={},
        rag_context=rag_context,
    )

    assert rag_context["context_status"] == "fetch_failed"
    assert rag_context["chunks"] == []
    assert rag_context["sources"] == []
    assert rag_context["error"] == "search unavailable"
    assert analysis_context.rag.status == ContextStatus.FETCH_FAILED


def test_safe_agent_runner_marks_search_failure_as_missing() -> None:
    from app.errors import SearchProviderError
    from app.utils import safe_run_agent

    def failing_agent(company_name: str, context: dict) -> dict:
        raise SearchProviderError("search unavailable")

    result = safe_run_agent("news", failing_agent, "Tesla", {})

    assert result["summary"] == "External search data is unavailable."
    assert result["key_points"] == [
        "Search provider request failed",
        "No synthetic sources were used",
    ]
    assert result["confidence"] == 0.0
    assert result["sources"] == []
    assert result["error"] == "search unavailable"


def test_development_search_keeps_mock_fallback(monkeypatch) -> None:
    from app.tools.search import search_public_info

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    results = search_public_info("test query")

    assert results
    assert all(result["provider"] == "mock" for result in results)
