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
    monkeypatch.setattr(
        "app.main.build_financial_profile",
        lambda symbol, exchange="": {
            "enabled": False,
            "symbol": symbol,
            "source": "sec_companyfacts",
            "reason": "test financial profile disabled",
            "summary": ["test financial profile disabled"],
        },
    )
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
    assert "embedding_provider" in data
    assert "chunks_count" in data
    assert "documents_count" in data
    assert "chunks" in data
    assert "sources" in data
    assert data["chunks_count"] >= 1
    first_chunk = data["chunks"][0]
    assert "chunk_id" in first_chunk
    assert "source_domain" in first_chunk
    assert "source_type" in first_chunk
    assert "retrieval_score" in first_chunk
    assert "source_grade" in first_chunk


def test_debug_routes_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_DEBUG_ROUTES", "false")

    response = client.get("/debug/architecture")

    assert response.status_code == 404


class FakeSearchResponse:
    def __init__(self, payload: dict | None = None, text: str = "", status_code: int = 200) -> None:
        self._payload = payload or {}
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": "text/html"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_brave_search_provider(monkeypatch) -> None:
    from app.tools.search import search_public_info

    def fake_get(url, headers=None, params=None, timeout=10):
        assert url == "https://api.search.brave.com/res/v1/web/search"
        assert headers["X-Subscription-Token"] == "brave-key"
        assert params["q"] == "Tesla AI"
        return FakeSearchResponse(
            {
                "web": {
                    "results": [
                        {
                            "title": "Tesla AI update",
                            "url": "https://example.com/tesla-ai",
                            "description": "Tesla AI search result",
                            "extra_snippets": ["extra context"],
                        }
                    ]
                }
            }
        )

    monkeypatch.setenv("SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setattr("app.tools.search.requests.get", fake_get)

    results = search_public_info("Tesla AI")

    assert results[0]["provider"] == "brave"
    assert results[0]["title"] == "Tesla AI update"
    assert "extra context" in results[0]["snippet"]


def test_blockbeats_search_provider(monkeypatch) -> None:
    from app.tools.search import search_public_info

    def fake_get(url, headers=None, params=None, timeout=10):
        assert url == "https://api-pro.theblockbeats.info/v1/search"
        assert headers["api-key"] == "blockbeats-key"
        assert params["name"] == "BTC ETF"
        return FakeSearchResponse(
            {
                "status": 0,
                "data": {
                    "data": [
                        {
                            "title": "BTC ETF flow update",
                            "url": "https://www.theblockbeats.info/news/test",
                            "content": "<p>BlockBeats 消息，BTC ETF 净流入。</p>",
                            "create_time": "2026-06-15 10:00:00",
                        }
                    ]
                },
            }
        )

    monkeypatch.setenv("SEARCH_PROVIDER", "blockbeats")
    monkeypatch.setenv("BLOCKBEATS_API_KEY", "blockbeats-key")
    monkeypatch.setattr("app.tools.search.requests.get", fake_get)

    results = search_public_info("BTC ETF")

    assert results[0]["provider"] == "blockbeats"
    assert results[0]["published_at"] == "2026-06-15 10:00:00"
    assert "BTC ETF" in results[0]["snippet"]


def test_multi_search_provider_merges_results(monkeypatch) -> None:
    from app.tools.search import search_public_info

    monkeypatch.setenv("SEARCH_PROVIDER", "multi")
    monkeypatch.setenv("SEARCH_PROVIDERS", "brave,blockbeats,tavily")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setenv("BLOCKBEATS_API_KEY", "blockbeats-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("SEARCH_MAX_WORKERS", "3")
    monkeypatch.setattr(
        "app.tools.search._search_with_brave",
        lambda query, api_key, limit: [
            {"title": "Brave result", "url": "https://example.com/brave", "snippet": "brave", "provider": "brave"}
        ],
    )
    monkeypatch.setattr(
        "app.tools.search._search_with_blockbeats",
        lambda query, api_key, limit: [
            {"title": "BlockBeats result", "url": "https://www.theblockbeats.info/news/test", "snippet": "blockbeats", "provider": "blockbeats"}
        ],
    )
    monkeypatch.setattr(
        "app.tools.search._search_with_tavily",
        lambda query, api_key, limit: [
            {"title": "Tavily result", "url": "https://example.com/tavily", "snippet": "tavily", "provider": "tavily"}
        ],
    )

    results = search_public_info("BTC ETF", limit=5)

    assert [result["provider"] for result in results] == ["brave", "blockbeats", "tavily"]


def test_multi_search_default_providers(monkeypatch) -> None:
    from app.tools.search import _configured_providers

    monkeypatch.setenv("SEARCH_PROVIDER", "multi")
    monkeypatch.delenv("SEARCH_PROVIDERS", raising=False)

    assert _configured_providers() == ["brave", "blockbeats", "tavily"]


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


def test_symbol_lookup_nokia_returns_adr_and_primary_listing() -> None:
    response = client.get("/symbol/lookup", params={"query": "诺基亚"})
    data = response.json()
    symbols = [match["symbol"] for match in data["matches"]]

    assert response.status_code == 200
    assert "NOK" in symbols
    assert "NOKIA.HE" in symbols
    assert data["needs_confirmation"] is True


def test_symbol_lookup_nok_exact_symbol_prefers_nyse_adr() -> None:
    response = client.get("/symbol/lookup", params={"query": "NOK"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "NOK"
    assert data["matches"][0]["ticker"] == "NYSE:NOK"
    assert data["matches"][0]["source"] == "exact_symbol"


def test_symbol_lookup_exact_symbol() -> None:
    response = client.get("/symbol/lookup", params={"query": "BABA"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "BABA"
    assert data["matches"][0]["source"] == "exact_symbol"


def test_symbol_lookup_popular_us_ai_name() -> None:
    response = client.get("/symbol/lookup", params={"query": "PLTR"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "PLTR"
    assert data["matches"][0]["exchange"] == "NASDAQ"
    assert data["matches"][0]["source"] == "exact_symbol"


def test_symbol_lookup_popular_dual_listed_china_name() -> None:
    response = client.get("/symbol/lookup", params={"query": "京东"})
    data = response.json()
    symbols = [match["symbol"] for match in data["matches"]]

    assert response.status_code == 200
    assert "9618.HK" in symbols
    assert "JD" in symbols
    assert data["needs_confirmation"] is True


def test_symbol_lookup_popular_cn_semiconductor_name() -> None:
    response = client.get("/symbol/lookup", params={"query": "中芯国际"})
    data = response.json()
    symbols = [match["symbol"] for match in data["matches"]]

    assert response.status_code == 200
    assert "688981.SS" in symbols
    assert "0981.HK" in symbols
    assert data["needs_confirmation"] is True


def test_symbol_lookup_zhipu_ai_hk_listing() -> None:
    response = client.get("/symbol/lookup", params={"query": "智谱AI"})
    data = response.json()

    assert response.status_code == 200
    assert data["matches"][0]["symbol"] == "2513.HK"
    assert data["matches"][0]["exchange"] == "HKEX"
    assert data["matches"][0]["ticker"] == "HKEX:2513"
    assert data["matches"][0]["source"] == "alias"


def test_symbol_resolve_batch_handles_success_ambiguity_and_failure(monkeypatch) -> None:
    def fake_lookup(query: str) -> dict:
        if query == "bad":
            raise RuntimeError("lookup exploded")
        if query == "京东":
            return {
                "query": query,
                "matched": True,
                "needs_confirmation": True,
                "candidates": [
                    {"symbol": "9618.HK", "name": "JD.com", "confidence": 0.95},
                    {"symbol": "JD", "name": "JD.com", "confidence": 0.94},
                ],
            }
        return {
            "query": query,
            "matched": True,
            "needs_confirmation": False,
            "candidates": [{"symbol": "NVDA", "name": "NVIDIA", "confidence": 0.99}],
        }

    monkeypatch.setattr("app.main.lookup_symbol", fake_lookup)

    response = client.post("/symbol/resolve-batch", json={"items": ["NVDA", "京东", "bad", "   "]})
    data = response.json()

    assert response.status_code == 200
    assert data["total"] == 3
    assert data["resolved_count"] == 1
    assert data["needs_confirmation_count"] == 1
    assert data["failed_count"] == 1
    assert data["results"][0]["input"] == "NVDA"
    assert data["results"][0]["resolved"]["symbol"] == "NVDA"
    assert data["results"][1]["needs_confirmation"] is True
    assert len(data["results"][1]["candidates"]) == 2
    assert data["results"][2]["input"] == "bad"
    assert data["results"][2]["resolved"] is None
    assert data["results"][2]["error"] == "lookup exploded"


def test_symbol_resolve_batch_accepts_text_payload(monkeypatch) -> None:
    captured = []

    def fake_lookup(query: str) -> dict:
        captured.append(query)
        return {
            "query": query,
            "matched": True,
            "needs_confirmation": False,
            "candidates": [{"symbol": query, "name": query, "confidence": 0.99}],
        }

    monkeypatch.setattr("app.main.lookup_symbol", fake_lookup)

    response = client.post("/symbol/resolve-batch", json={"text": "600519, 0700.HK\nNVDA"})

    assert response.status_code == 200
    assert captured == ["600519", "0700.HK", "NVDA"]


def test_market_chart_empty_symbol() -> None:
    for provider in ("auto", "yahoo"):
        response = client.get("/market/chart", params={"symbol": "   ", "provider": provider})
        data = response.json()

        assert response.status_code == 200
        assert data["points"] == []
        assert "cache_hit" in data


def test_market_chart_forwards_exchange(monkeypatch) -> None:
    captured = {}

    def fake_chart(symbol, provider, range_, interval, exchange=None):
        captured.update(symbol=symbol, provider=provider, exchange=exchange)
        return {"provider": "akshare", "points": []}

    monkeypatch.setattr("app.main.get_market_chart", fake_chart)
    response = client.get(
        "/market/chart",
        params={"symbol": "00700", "exchange": "HKEX", "provider": "auto"},
    )

    assert response.status_code == 200
    assert captured == {"symbol": "00700", "provider": "auto", "exchange": "HKEX"}


def test_market_chart_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_CHART_RATE_LIMIT", "1")

    first_response = client.get("/market/chart", params={"symbol": "   ", "provider": "auto"})
    second_response = client.get("/market/chart", params={"symbol": "   ", "provider": "auto"})

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_market_review_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.build_market_review",
        lambda market="auto": {
            "market": market,
            "context_status": "available",
            "reviews": {
                "cn": {
                    "market": "cn",
                    "context_status": "available",
                    "market_status": "up",
                    "indices": [
                        {
                            "name": "上证指数",
                            "symbol": "000001.SH",
                            "latest_close": 3100,
                            "change_percent": 1.2,
                            "volume": 100,
                            "provider": "akshare",
                            "provider_attempts": [{"provider": "akshare", "status": "success"}],
                        }
                    ],
                    "hotspots": [],
                    "summary": ["A 股主要指数偏强。"],
                    "provider_attempts": [{"provider": "akshare", "status": "success"}],
                }
            },
        },
        raising=False,
    )

    response = client.get("/market/review", params={"market": "cn"})
    data = response.json()

    assert response.status_code == 200
    assert data["market"] == "cn"
    assert data["context_status"] == "available"
    assert data["reviews"]["cn"]["indices"][0]["name"] == "上证指数"


def test_financials_latest(monkeypatch) -> None:
    def fake_build_financial_profile(symbol: str, exchange: str = "") -> dict:
        return {
            "enabled": True,
            "symbol": symbol,
            "source": "sec_companyfacts",
            "fiscal_period": "FY2026 Q2",
            "filing_type": "10-Q",
            "revenue": 1516000000,
            "gross_profit": 712000000,
            "gross_margin_percent": 46.97,
            "net_income": 185000000,
            "operating_cash_flow": 320000000,
            "cash": 980000000,
            "debt": 420000000,
            "filing_url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
            "summary": ["最新披露收入为 1,516,000,000。"],
        }

    monkeypatch.setattr("app.main.build_financial_profile", fake_build_financial_profile)

    response = client.get("/financials/latest", params={"symbol": "MRVL", "exchange": "NASDAQ"})
    data = response.json()

    assert response.status_code == 200
    assert data["enabled"] is True
    assert data["source"] == "sec_companyfacts"
    assert data["filing_type"] == "10-Q"
    assert data["revenue"] == 1516000000
    assert data["gross_margin_percent"] == 46.97
    assert data["cache_hit"] is False


def test_financial_profile_ignores_stale_balance_sheet_facts(monkeypatch) -> None:
    from app.services.financials import build_financial_profile

    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"val": 19335000000, "form": "10-Q", "fy": 2025, "fp": "Q1", "end": "2025-03-31", "filed": "2025-04-23", "start": "2025-01-01"},
                            {"val": 22387000000, "form": "10-Q", "fy": 2026, "fp": "Q1", "end": "2026-03-31", "filed": "2026-04-23", "start": "2026-01-01"},
                        ]
                    }
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {"val": 16603000000, "form": "10-Q", "fy": 2026, "fp": "Q1", "end": "2026-03-31", "filed": "2026-04-23"}
                        ]
                    }
                },
                "LongTermDebtNoncurrent": {
                    "units": {
                        "USD": [
                            {"val": 597600000, "form": "10-Q", "fy": 2014, "fp": "Q3", "end": "2014-09-30", "filed": "2014-11-07"}
                        ]
                    }
                },
            }
        }
    }

    monkeypatch.setattr(
        "app.services.financials.ticker_to_cik",
        lambda ticker: {"matched": True, "ticker": ticker, "cik": "0001318605", "company_name": "Tesla, Inc."},
    )
    monkeypatch.setattr("app.services.financials.get_companyfacts", lambda cik: companyfacts)
    monkeypatch.setattr(
        "app.services.financials.get_latest_filing_metadata",
        lambda cik: {"form": "10-Q", "report_date": "2026-03-31", "filing_date": "2026-04-23", "filing_url": "https://www.sec.gov/test.htm"},
    )

    profile = build_financial_profile("TSLA", "NASDAQ")

    assert profile["enabled"] is True
    assert profile["revenue"] == 22387000000
    assert profile["revenue_change_percent"] == 15.78
    assert profile["cash"] == 16603000000
    assert profile["debt"] is None
    assert profile["metrics"]["long_term_debt"]["value"] is None


def test_financial_profile_supports_ifrs_20f_foreign_issuer(monkeypatch) -> None:
    from app.services.financials import build_financial_profile

    companyfacts = {
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {
                        "EUR": [
                            {"val": 22400000000, "form": "20-F", "fy": 2024, "fp": "FY", "end": "2024-12-31", "filed": "2025-03-06", "start": "2024-01-01"},
                            {"val": 19767000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"},
                        ]
                    }
                },
                "GrossProfit": {
                    "units": {"EUR": [{"val": 8659000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"}]}
                },
                "ProfitLossFromOperatingActivities": {
                    "units": {"EUR": [{"val": 1384000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"}]}
                },
                "ProfitLoss": {
                    "units": {
                        "EUR": [
                            {"val": 660000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"}
                        ]
                    }
                },
                "DilutedEarningsLossPerShare": {
                    "units": {"EUR/shares": [{"val": 0.12, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"}]}
                },
                "CashFlowsFromUsedInOperatingActivities": {
                    "units": {"EUR": [{"val": 2071000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05", "start": "2025-01-01"}]}
                },
                "CashAndCashEquivalents": {
                    "units": {"EUR": [{"val": 5462000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
                "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": {
                    "units": {"EUR": [{"val": 1084000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
                "LongtermBorrowings": {
                    "units": {"EUR": [{"val": 2329000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
                "Assets": {
                    "units": {"EUR": [{"val": 37597000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
                "Liabilities": {
                    "units": {"EUR": [{"val": 16539000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
                "EquityAttributableToOwnersOfParent": {
                    "units": {"EUR": [{"val": 20967000000, "form": "20-F", "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-03-05"}]}
                },
            }
        }
    }

    monkeypatch.setattr(
        "app.services.financials.ticker_to_cik",
        lambda ticker: {"matched": True, "ticker": ticker, "cik": "0000924613", "company_name": "NOKIA CORP"},
    )
    monkeypatch.setattr("app.services.financials.get_companyfacts", lambda cik: companyfacts)
    monkeypatch.setattr(
        "app.services.financials.get_latest_filing_metadata",
        lambda cik: {"form": "20-F", "report_date": "2025-12-31", "filing_date": "2026-03-05", "filing_url": "https://www.sec.gov/nok.htm"},
    )

    profile = build_financial_profile("NOK", "NYSE")

    assert profile["enabled"] is True
    assert profile["symbol"] == "NOK"
    assert profile["filing_type"] == "20-F"
    assert profile["currency"] == "EUR"
    assert profile["fiscal_period"] == "FY2025 FY"
    assert profile["revenue"] == 19767000000
    assert profile["gross_margin_percent"] == 43.81
    assert profile["eps_diluted"] == 0.12
    assert profile["operating_cash_flow"] == 2071000000
    assert profile["cash"] == 5462000000
    assert profile["debt"] == 3413000000
    assert profile["revenue_change_percent"] == -11.75
    assert profile["metrics"]["revenue"]["taxonomy_namespace"] == "ifrs-full"


def test_rag_chunks_include_metadata(monkeypatch) -> None:
    from app.rag.retriever import retrieve_industry_context

    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "hash")
    rag_context = retrieve_industry_context("NVIDIA", "NVIDIA competitors regulation")

    assert rag_context["embedding_provider"] == "hash"
    assert rag_context["documents_count"] >= 1
    assert rag_context["chunks"]
    chunk = rag_context["chunks"][0]
    assert chunk["chunk_id"]
    assert chunk["company_name"] == "NVIDIA"
    assert chunk["source_type"] == "mock"
    assert isinstance(chunk["retrieval_score"], float)
    assert rag_context["sources"][0]["chunk_id"] == chunk["chunk_id"]


def test_citation_checker_reports_claim_coverage() -> None:
    from app.services.citation_checker import check_citations

    result = check_citations(
        {
            "industry": {
                "summary": "Industry summary",
                "key_points": ["Demand is growing"],
                "claims": [
                    {
                        "claim": "Demand is growing",
                        "source_url": "https://www.sec.gov/example",
                    },
                    {
                        "claim": "Competition is intense",
                        "source_url": "",
                    },
                ],
            }
        },
        [
            {
                "title": "SEC filing",
                "url": "https://www.sec.gov/example",
                "source_type": "regulatory_filing",
                "source_grade": "A",
                "retrieval_score": 0.9,
            }
        ],
    )

    assert result["passed"] is True
    assert result["total_claims"] == 2
    assert result["cited_claims"] == 1
    assert result["claim_citation_coverage"] == 0.5
    assert result["official_sources_count"] == 1
    assert result["retrieval_scores"] == [0.9]


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
    assert "financial_profile" in data
    assert "analysis_context" in data
    analysis_context = data["analysis_context"]
    assert analysis_context["version"] == "1.0"
    assert analysis_context["company"] == "OpenAI"
    assert set(analysis_context) >= {
        "market",
        "financials",
        "rag",
        "data_quality",
        "created_at",
    }
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
    assert "财报数据摘要" in data["markdown_report"]
    assert "估值与情景分析" in data["markdown_report"]
    assert "source_ratings" in source_quality
    assert "grade_counts" in source_quality
    assert "来源质量审查" in data["markdown_report"]
    assert "来源评级" in data["markdown_report"]
    assert "risks" in data["final_report"]
    assert "watch_items" in data["final_report"]
    assert "financial_profile" in data["final_report"]
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
    assert "market_profile" in data
    assert "financial_profile" in data
    assert "citation_check" in data
    assert "trace_summary" in data
    assert "行情数据摘要" in data["markdown_report"]
    assert "财报数据摘要" in data["markdown_report"]
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
    assert [step["name"] for step in status_data["steps"]] == [
        "queued",
        "fetch_market",
        "fetch_financials",
        "rag_search",
        "agent_analysis",
        "report_render",
        "completed",
        "failed",
    ]
    assert all("status" in step for step in status_data["steps"])


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
