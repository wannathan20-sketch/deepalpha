import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch) -> None:
    import app.memory.store as store
    from app.services.cache import cache
    from app.services.rate_limit import rate_limiter

    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "test_deepalpha.sqlite3")
    cache._items.clear()
    rate_limiter._hits.clear()


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config() -> None:
    response = client.get("/config")
    data = response.json()

    assert response.status_code == 200
    assert "llm_provider" in data
    assert "llm_model" in data
    assert "llm_enabled" in data
    assert "search_provider" in data
    assert "search_enabled" in data
    assert "debug_routes_enabled" in data
    assert "OPENAI_API_KEY" not in data
    assert "TAVILY_API_KEY" not in data


def test_debug_architecture() -> None:
    response = client.get("/debug/architecture")
    data = response.json()

    assert response.status_code == 200
    assert data["project"] == "DeepAlpha"
    assert data["capabilities"]["langgraph"] is True
    assert data["capabilities"]["rag"] is True
    assert data["capabilities"]["memory"] is True
    assert "Industry Analyst" in data["agents"]
    assert "RAG Retriever" in data["tools"]


def test_debug_rag() -> None:
    response = client.get("/debug/rag", params={"company_name": "Tesla"})
    data = response.json()

    assert response.status_code == 200
    assert data["company_name"] == "Tesla"
    assert "query" in data
    assert "vector_store" in data
    assert "chunks_count" in data
    assert "chunks" in data
    assert "sources" in data


def test_debug_routes_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "false")

    response = client.get("/debug/architecture")

    assert response.status_code == 404


def test_symbol_lookup_empty_query() -> None:
    response = client.get("/symbol/lookup", params={"query": "   "})
    data = response.json()

    assert response.status_code == 200
    assert data["matched"] is False
    assert data["matches"] == []
    assert "cache_hit" in data


def test_symbol_lookup_meituan_prefers_hk_alias() -> None:
    response = client.get("/symbol/lookup", params={"query": "美团"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "3690.HK"
    assert data["matches"][0]["exchange"] == "HKEX"
    assert data["matches"][0]["market"] == "HK"
    assert data["matches"][0]["source"] == "alias"
    assert data["matches"][0]["confidence"] >= 0.9


def test_symbol_lookup_alibaba_returns_hk_and_us() -> None:
    response = client.get("/symbol/lookup", params={"query": "阿里"})
    data = response.json()
    symbols = [match["symbol"] for match in data["matches"]]

    assert response.status_code == 200
    assert "9988.HK" in symbols
    assert "BABA" in symbols
    assert data["needs_confirmation"] is True


def test_symbol_lookup_exact_symbol() -> None:
    response = client.get("/symbol/lookup", params={"query": "BABA"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "BABA"
    assert data["matches"][0]["source"] == "exact_symbol"


def test_market_chart_empty_symbol() -> None:
    for provider in ("auto", "yahoo"):
        response = client.get("/market/chart", params={"symbol": "   ", "provider": provider})
        data = response.json()

        assert response.status_code == 200
        assert data["points"] == []
        assert "cache_hit" in data


def test_market_chart_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_CHART_RATE_LIMIT", "1")

    first_response = client.get("/market/chart", params={"symbol": "   ", "provider": "auto"})
    second_response = client.get("/market/chart", params={"symbol": "   ", "provider": "auto"})

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_analyze() -> None:
    response = client.post("/analyze", json={"company_name": "OpenAI"})
    data = response.json()

    assert response.status_code == 200
    assert data["company_name"] == "OpenAI"
    assert data["status"] == "success"
    assert "planner_result" in data
    assert "rag_chunks" in data
    assert "agent_outputs" in data
    assert "final_decision" in data
    assert "research_plan" in data
    assert "team_results" in data
    assert "final_report" in data
    assert "markdown_report" in data
    assert "report_editor" in data
    assert "market_profile" in data
    assert "citation_check" in data
    assert "passed" in data["citation_check"]
    assert "checked_agents" in data["citation_check"]
    assert "issues" in data["citation_check"]
    assert "sources_count" in data["citation_check"]
    assert "trace" in data
    fundamental = data["agent_outputs"]["fundamental"]
    financial = data["agent_outputs"]["financial"]
    valuation = data["agent_outputs"]["valuation"]
    source_quality = data["agent_outputs"]["source_quality"]
    assert "verdict" in fundamental
    assert "claims" in fundamental
    assert "data_quality" in fundamental
    assert "watch_items" in fundamental
    assert isinstance(fundamental["claims"], list)
    assert "claims" in financial
    assert "watch_items" in financial
    assert "data_quality" in valuation
    assert "Executive Summary" in data["markdown_report"]
    assert "核心矛盾" in data["markdown_report"]
    assert "估值与情景分析" in data["markdown_report"]
    assert "source_ratings" in source_quality
    assert "grade_counts" in source_quality
    assert "来源质量审查" in data["markdown_report"]
    assert "来源评级" in data["markdown_report"]
    assert "risks" in data["final_report"]
    assert "watch_items" in data["final_report"]
    assert "edits" in data["report_editor"]
    assert "report_editor_completed" in [step["step_name"] for step in data["trace"]["steps"]]


def test_report_editor_cleans_pdf_artifacts() -> None:
    from app.agents.report_editor import edit_report

    raw_report = """
# **测试报告**

好的，作为分析师，以下是重点。
好的，作为分析师，以下是重点。
---
- **收入增长需要复核**
- **收入增长需要复核**
暂无 summary。
```
"""

    result = edit_report("ArtifactCo", raw_report)
    edited = result["markdown_report"]

    assert result["edits"]["removed_duplicates"] >= 1
    assert result["edits"]["removed_artifacts"] >= 1
    assert "**" not in edited
    assert "好的" not in edited
    assert "作为分析师" not in edited
    assert "暂无可用摘要" in edited


def test_report() -> None:
    company_name = "ReportHistoryCo"
    before_history = client.get("/memory/history").json()

    response = client.post(
        "/report",
        json={
            "company_name": company_name,
            "symbol": "NASDAQ:RHC",
            "yahoo_symbol": "RHC",
            "data_provider": "auto",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["company_name"] == company_name
    assert data["status"] == "success"
    assert "final_report" in data
    assert "markdown_report" in data
    assert "report_editor" in data
    assert "source_quality" in data
    assert "citation_check" in data
    assert "trace_summary" in data
    assert "行情数据摘要" in data["markdown_report"]
    assert "trace_id" in data["trace_summary"]
    assert "duration_seconds" in data["trace_summary"]
    assert "steps_count" in data["trace_summary"]
    assert "team_results" not in data
    assert "trace" not in data

    after_history = client.get("/memory/history").json()
    assert len(after_history) == len(before_history) + 1
    assert after_history[0]["company_name"] == company_name
    assert after_history[0]["symbol"] == "NASDAQ:RHC"
    assert after_history[0]["yahoo_symbol"] == "RHC"
    assert after_history[0]["data_provider"] == "auto"


def test_report_task() -> None:
    response = client.post("/report/tasks", json={"company_name": "AsyncReportCo"})
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "queued"
    assert "task_id" in data

    status_response = client.get(f"/report/tasks/{data['task_id']}")
    status_data = status_response.json()

    assert status_response.status_code == 200
    assert status_data["task_id"] == data["task_id"]
    assert status_data["status"] in {"queued", "running", "success", "failed"}


def test_report_task_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_USER_DAILY_LIMIT", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_DAY", "10")
    monkeypatch.setenv("REPORT_GLOBAL_DAILY_LIMIT", "50")

    first_response = client.post("/report/tasks", json={"company_name": "RateLimitCo"})
    second_response = client.post("/report/tasks", json={"company_name": "RateLimitCo"})

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_report_global_daily_limit(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_USER_DAILY_LIMIT", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_DAY", "10")
    monkeypatch.setenv("REPORT_GLOBAL_DAILY_LIMIT", "1")

    first_response = client.post("/report/tasks", json={"company_name": "GlobalLimitCo"})
    second_response = client.post("/report/tasks", json={"company_name": "GlobalLimitCo"})

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_report_access_code_required(monkeypatch) -> None:
    monkeypatch.setenv("DEEPALPHA_ACCESS_CODE", "secret-code")

    missing_response = client.post("/report/tasks", json={"company_name": "AccessCodeCo"})
    invalid_response = client.post(
        "/report/tasks",
        headers={"X-DeepAlpha-Access-Code": "wrong-code"},
        json={"company_name": "AccessCodeCo"},
    )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401


def test_report_access_code_allows_valid_request(monkeypatch) -> None:
    monkeypatch.setenv("DEEPALPHA_ACCESS_CODE", "secret-code")
    monkeypatch.setenv("REPORT_USER_DAILY_LIMIT", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_DAY", "10")
    monkeypatch.setenv("REPORT_GLOBAL_DAILY_LIMIT", "50")

    response = client.post(
        "/report/tasks",
        headers={
            "X-DeepAlpha-Access-Code": "secret-code",
            "X-DeepAlpha-User-Id": "user-a",
        },
        json={"company_name": "AccessCodeCo"},
    )

    assert response.status_code == 200


def test_report_user_daily_limit(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_USER_DAILY_LIMIT", "1")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("REPORT_CREATE_RATE_LIMIT_PER_DAY", "10")
    monkeypatch.setenv("REPORT_GLOBAL_DAILY_LIMIT", "50")

    first_response = client.post(
        "/report/tasks",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={"company_name": "UserLimitCo"},
    )
    second_response = client.post(
        "/report/tasks",
        headers={"X-DeepAlpha-User-Id": "user-a"},
        json={"company_name": "UserLimitCo"},
    )
    other_user_response = client.post(
        "/report/tasks",
        headers={"X-DeepAlpha-User-Id": "user-b"},
        json={"company_name": "UserLimitCo"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert other_user_response.status_code == 200


def test_memory_watchlist() -> None:
    response = client.post(
        "/memory/watchlist",
        json={
            "company_name": "Tesla",
            "symbol": "NASDAQ:TSLA",
            "yahoo_symbol": "TSLA",
            "data_provider": "auto",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["company_name"] == "Tesla"
    assert data["symbol"] == "NASDAQ:TSLA"
    assert data["yahoo_symbol"] == "TSLA"
    assert "created_at" in data
    assert "last_analyzed_at" in data

    list_response = client.get("/memory/watchlist")
    assert list_response.status_code == 200
    assert isinstance(list_response.json(), list)


def test_memory_history() -> None:
    response = client.get("/memory/history")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
