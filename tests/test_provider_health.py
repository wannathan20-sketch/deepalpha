import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _chart(provider: str, status: str = "success", *, reason: str = "", source_url: str = "") -> dict:
    points = [{"close": 1}, {"close": 2}] if status == "success" else []
    return {
        "provider": provider,
        "points": points,
        "source_url": source_url,
        "provider_attempts": [
            {
                "provider": provider,
                "status": status,
                "reason": reason,
                "duration_ms": 3,
            }
        ],
    }


def test_provider_health_marks_market_coverage_healthy(monkeypatch) -> None:
    from app.services.provider_health import build_provider_health

    def fake_get_market_chart(symbol, provider="auto", range_="1mo", interval="1d", exchange=None):
        if provider in {"nasdaq", "akshare", "yahoo"}:
            return _chart(provider, source_url=f"https://example.com/{provider}")
        return _chart(provider, "unavailable", reason="Provider is not configured or installed.")

    monkeypatch.setattr("app.services.provider_health.get_market_chart", fake_get_market_chart)

    health = build_provider_health(ttl_seconds=300)

    assert health["status"] == "ok"
    assert health["ttl_seconds"] == 300
    assert health["markets"]["us"]["healthy"] is True
    assert health["markets"]["cn"]["healthy"] is True
    assert health["markets"]["hk"]["healthy"] is True
    nasdaq = next(item for item in health["providers"] if item["provider"] == "nasdaq")
    assert nasdaq["status"] == "healthy"
    assert nasdaq["source_url"] == "https://example.com/nasdaq"


def test_provider_health_degrades_without_coverage_and_sanitizes_reason(monkeypatch) -> None:
    from app.services.provider_health import build_provider_health

    def fake_get_market_chart(symbol, provider="auto", range_="1mo", interval="1d", exchange=None):
        return _chart(
            provider,
            "failed",
            reason="HTTP 500 token=secret-key response body with private provider payload",
        )

    monkeypatch.setattr("app.services.provider_health.get_market_chart", fake_get_market_chart)

    health = build_provider_health(ttl_seconds=300)

    assert health["status"] == "unavailable"
    assert all(item["status"] == "degraded" for item in health["providers"])
    assert all("secret-key" not in item["reason"] for item in health["providers"])
    assert all("private provider payload" not in item["reason"] for item in health["providers"])
    assert any(item["reason"] == "HTTP 500" for item in health["providers"])

