from datetime import timezone
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import AnalysisContextPack, ContextItem, ContextStatus, DataQuality
from app.services.analysis_context import build_analysis_context


def test_analysis_context_pack_defaults_to_version_one() -> None:
    pack = AnalysisContextPack(
        company="NVIDIA",
        market=ContextItem(status=ContextStatus.AVAILABLE, value={"latest_close": 120.0}),
        financials=ContextItem(status=ContextStatus.MISSING),
        rag=ContextItem(status=ContextStatus.FALLBACK),
        data_quality=DataQuality(overall_score=53, level="limited"),
    )

    assert pack.version == "1.0"
    assert pack.created_at.tzinfo == timezone.utc
    assert pack.model_dump(mode="json")["market"]["status"] == "available"


def test_analysis_context_pack_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        AnalysisContextPack(
            version="2.0",
            company="NVIDIA",
            market=ContextItem(status=ContextStatus.MISSING),
            financials=ContextItem(status=ContextStatus.MISSING),
            rag=ContextItem(status=ContextStatus.MISSING),
            data_quality=DataQuality(overall_score=20, level="poor"),
        )


def test_builder_classifies_available_market_and_mock_rag() -> None:
    pack = build_analysis_context(
        "NVIDIA",
        market_profile={
            "enabled": True,
            "context_status": "available",
            "provider": "yahoo",
            "latest_close": 120.0,
            "points_count": 120,
        },
        financial_profile={
            "enabled": False,
            "context_status": "not_supported",
            "source": "sec_companyfacts",
            "reason": "Market is not supported.",
        },
        rag_context={
            "vector_store": "in_memory",
            "chunks": [
                {
                    "title": "Mock context",
                    "content": "Mock content",
                    "source_type": "mock",
                    "source_provider": "mock",
                }
            ],
        },
    )

    assert pack.market.status == ContextStatus.AVAILABLE
    assert pack.financials.status == ContextStatus.NOT_SUPPORTED
    assert pack.rag.status == ContextStatus.FALLBACK
    assert pack.rag.fallback_from == "real_search"


def test_builder_classifies_provider_failure() -> None:
    pack = build_analysis_context(
        "FailureCo",
        market_profile={
            "enabled": False,
            "context_status": "fetch_failed",
            "provider": "yahoo",
            "reason": "Provider timeout",
        },
        financial_profile={},
        rag_context={"chunks": []},
    )

    assert pack.market.status == ContextStatus.FETCH_FAILED
    assert pack.market.missing_reason == "Provider timeout"
    assert pack.financials.status == ContextStatus.MISSING
    assert pack.rag.status == ContextStatus.MISSING


def test_degraded_inputs_reduce_quality_score() -> None:
    available = build_analysis_context(
        "QualityCo",
        market_profile={"enabled": True, "context_status": "available", "latest_close": 10},
        financial_profile={"enabled": True, "context_status": "available", "revenue": 100},
        rag_context={"chunks": [{"content": "evidence", "source_type": "news"}]},
    )
    degraded = build_analysis_context(
        "QualityCo",
        market_profile={"enabled": False, "context_status": "fetch_failed", "reason": "timeout"},
        financial_profile={"enabled": False, "context_status": "missing", "reason": "no symbol"},
        rag_context={"chunks": [{"content": "mock", "source_type": "mock"}]},
    )

    assert available.data_quality.overall_score == 100
    assert available.data_quality.level == "good"
    assert degraded.data_quality.overall_score < available.data_quality.overall_score
    assert degraded.data_quality.level == "poor"
    assert len(degraded.data_quality.limitations) == 3


def test_market_profile_marks_provider_error_as_fetch_failed(monkeypatch) -> None:
    from app.services.market_summary import build_market_profile

    monkeypatch.setattr(
        "app.services.market_summary.get_market_chart",
        lambda *args, **kwargs: {"provider": "auto", "points": [], "error": "timeout"},
    )

    profile = build_market_profile(symbol="NASDAQ:NVDA", yahoo_symbol="NVDA")

    assert profile["enabled"] is False
    assert profile["context_status"] == "fetch_failed"
    assert profile["reason"] == "timeout"


def test_market_profile_marks_successful_provider_fallback(monkeypatch) -> None:
    from app.services.market_summary import build_market_profile

    monkeypatch.setattr(
        "app.services.market_summary.get_market_chart",
        lambda *args, **kwargs: {
            "provider": "yahoo",
            "provider_mode": "auto",
            "fallback_from": "akshare",
            "provider_attempts": [
                {"provider": "akshare", "status": "failed", "reason": "TimeoutError", "duration_ms": 1},
                {"provider": "yahoo", "status": "success", "reason": "", "duration_ms": 2},
            ],
            "market": "cn",
            "exchange": "SH",
            "points": [
                {"time": 1, "close": 10},
                {"time": 2, "close": 11},
            ],
        },
    )

    profile = build_market_profile(symbol="SH600519", exchange="SSE")

    assert profile["context_status"] == "fallback"
    assert profile["fallback_from"] == "akshare"
    assert profile["provider_attempts"][0]["status"] == "failed"


def test_financial_profile_distinguishes_missing_and_unsupported() -> None:
    from app.services.financials import build_financial_profile

    missing = build_financial_profile(None)
    unsupported = build_financial_profile("BTC-USD", "CRYPTO")

    assert missing["context_status"] == "missing"
    assert unsupported["context_status"] == "not_supported"


def test_rag_node_adds_analysis_context(monkeypatch) -> None:
    from app.graph import rag_node

    monkeypatch.setattr(
        "app.graph.retrieve_industry_context",
        lambda company, query: {
            "vector_store": "in_memory",
            "chunks": [{"content": "mock", "source_type": "mock", "source_provider": "mock"}],
        },
    )
    state = {
        "company_name": "ContextCo",
        "market_profile": {"enabled": True, "context_status": "available", "latest_close": 10},
        "financial_profile": {"enabled": False, "context_status": "missing"},
        "analysis_context": {},
        "context": {},
        "trace": {"steps": []},
    }

    result = rag_node(state)

    assert result["analysis_context"]["version"] == "1.0"
    assert result["analysis_context"]["rag"]["status"] == "fallback"
    assert result["context"]["analysis_context"] == result["analysis_context"]
