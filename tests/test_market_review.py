import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _chart(symbol: str, provider: str, close: float, previous: float, volume: float = 1000) -> dict:
    return {
        "symbol": symbol,
        "provider": provider,
        "provider_mode": provider,
        "points": [
            {"time": 1, "close": previous, "volume": volume / 2},
            {"time": 2, "close": close, "volume": volume},
        ],
        "provider_attempts": [{"provider": provider, "status": "success", "reason": "", "duration_ms": 1}],
    }


def test_market_review_routes_cn_hk_us_indices(monkeypatch) -> None:
    from app.services.market_review import build_market_review

    calls = []

    def fake_get_market_chart(symbol, provider="auto", range_="1mo", interval="1d", exchange=None):
        calls.append((symbol, provider, exchange))
        return _chart(symbol, provider, 110, 100)

    monkeypatch.setattr("app.services.market_review.get_market_chart", fake_get_market_chart)

    review = build_market_review("auto")

    assert review["market"] == "auto"
    assert review["context_status"] == "available"
    assert set(review["reviews"]) == {"cn", "hk", "us"}
    assert [call[0] for call in calls] == [
        "000001.SH",
        "399001.SZ",
        "399006.SZ",
        "000688.SH",
        "^HSI",
        "^HSTECH",
        "^GSPC",
        "^IXIC",
        "^DJI",
    ]
    assert calls[0][1] == "auto"
    assert calls[4][1] == "auto"
    assert calls[6][1] == "auto"
    assert review["reviews"]["cn"]["indices"][0]["change_percent"] == 10


def test_market_review_marks_empty_data_missing_with_attempts(monkeypatch) -> None:
    from app.services.market_review import build_market_review

    def fake_get_market_chart(symbol, provider="auto", range_="1mo", interval="1d", exchange=None):
        return {
            "symbol": symbol,
            "provider": provider,
            "points": [],
            "error": "empty upstream",
            "provider_attempts": [{"provider": provider, "status": "empty", "reason": "no points", "duration_ms": 1}],
        }

    monkeypatch.setattr("app.services.market_review.get_market_chart", fake_get_market_chart)

    review = build_market_review("hk")
    hk = review["reviews"]["hk"]

    assert review["context_status"] == "fetch_failed"
    assert hk["context_status"] == "fetch_failed"
    assert hk["indices"] == []
    assert hk["provider_attempts"][0]["status"] == "empty"
    assert "empty upstream" in hk["summary"][0]


def test_market_review_exposes_etf_proxy_warning(monkeypatch) -> None:
    from app.services.market_review import build_market_review

    def fake_get_market_chart(
        symbol,
        provider="auto",
        range_="1mo",
        interval="1d",
        exchange=None,
    ):
        chart = _chart(symbol, "nasdaq", 501, 500)
        if symbol in {"^GSPC", "^DJI"}:
            chart.update(
                {
                    "instrument_type": "etf_proxy",
                    "proxy_symbol": "SPY" if symbol == "^GSPC" else "DIA",
                    "proxy_for": symbol,
                }
            )
        else:
            chart["instrument_type"] = "index"
        return chart

    monkeypatch.setattr(
        "app.services.market_review.get_market_chart",
        fake_get_market_chart,
    )

    review = build_market_review("us")["reviews"]["us"]

    assert review["context_status"] == "available"
    assert review["indices"][0]["proxy_symbol"] == "SPY"
    assert review["indices"][2]["proxy_symbol"] == "DIA"
    assert any("ETF 代理" in line for line in review["summary"])


def test_market_review_rejects_unknown_market() -> None:
    from app.services.market_review import build_market_review

    review = build_market_review("crypto")

    assert review["context_status"] == "not_supported"
    assert review["reason"] == "Unsupported market: crypto"
