import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.tools.market_symbols import normalize_market_symbol
from app.tools.market_data import get_market_chart
from app.tools.market_providers import (
    AkShareProvider,
    BaostockProvider,
    EfinanceProvider,
    FinnhubProvider,
    MarketChartRequest,
    YahooProvider,
    normalize_points,
)


@pytest.mark.parametrize(
    ("raw", "exchange", "market", "canonical", "yahoo", "local"),
    [
        ("600519", None, "cn", "SH600519", "600519.SS", "600519"),
        ("SZ000001", None, "cn", "SZ000001", "000001.SZ", "000001"),
        ("920748.BJ", None, "cn", "BJ920748", "920748.BJ", "920748"),
        ("HK00700", None, "hk", "HK00700", "0700.HK", "00700"),
        ("0700.HK", None, "hk", "HK00700", "0700.HK", "00700"),
        ("AAPL", None, "us", "AAPL", "AAPL", "AAPL"),
        ("NASDAQ:AAPL", None, "us", "AAPL", "AAPL", "AAPL"),
        ("00700", "HKEX", "hk", "HK00700", "0700.HK", "00700"),
    ],
)
def test_normalize_market_symbol(
    raw: str,
    exchange: str | None,
    market: str,
    canonical: str,
    yahoo: str,
    local: str,
) -> None:
    result = normalize_market_symbol(raw, exchange)

    assert result.market == market
    assert result.canonical_symbol == canonical
    assert result.yahoo_symbol == yahoo
    assert result.local_symbol == local


def test_normalize_market_symbol_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="Market symbol is required"):
        normalize_market_symbol("   ")


def test_normalize_points_sorts_deduplicates_and_drops_invalid_rows() -> None:
    points = normalize_points(
        [
            {"time": "2026-01-03", "open": "10", "high": "12", "low": "9", "close": "11", "volume": "100"},
            {"time": "2026-01-02", "open": 8, "high": 10, "low": 7, "close": 9, "volume": None},
            {"time": "2026-01-03", "open": 10, "high": 13, "low": 9, "close": 12, "volume": 120},
            {"time": "2026-01-04", "close": None},
        ]
    )

    assert [point["close"] for point in points] == [9.0, 12.0]
    assert points[0]["time"] == int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
    assert points[0]["volume"] is None


def test_optional_provider_availability(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.market_providers.importlib.util.find_spec", lambda name: None)

    assert AkShareProvider().is_available() is False
    assert EfinanceProvider().is_available() is False
    assert BaostockProvider().is_available() is False


def test_finnhub_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    assert FinnhubProvider().is_available() is False


class FakeFrame:
    empty = False

    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return self.records


def provider_request(raw_symbol: str) -> MarketChartRequest:
    return MarketChartRequest(
        symbol=normalize_market_symbol(raw_symbol),
        range_="6mo",
        interval="1d",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )


@pytest.mark.parametrize(
    ("provider", "markets"),
    [
        (YahooProvider(), {"cn", "hk", "us"}),
        (AkShareProvider(), {"cn", "hk"}),
        (EfinanceProvider(), {"cn"}),
        (BaostockProvider(), {"cn"}),
        (FinnhubProvider(), {"us"}),
    ],
)
def test_provider_support_matrix(provider, markets: set[str]) -> None:
    assert {market for market in {"cn", "hk", "us"} if provider.supports(market)} == markets


def test_akshare_adapter_maps_chinese_columns(monkeypatch) -> None:
    frame = FakeFrame([{"日期": "2026-01-02", "开盘": 10, "最高": 12, "最低": 9, "收盘": 11, "成交量": 100}])
    module = SimpleNamespace(stock_zh_a_hist=lambda **kwargs: frame)
    monkeypatch.setattr(AkShareProvider, "_module", lambda self: module)

    result = AkShareProvider().fetch_chart(provider_request("600519"))

    assert result["points"][0]["close"] == 11.0
    assert result["exchange"] == "SH"


def test_efinance_adapter_maps_chinese_columns(monkeypatch) -> None:
    frame = FakeFrame([{"日期": "2026-01-02", "开盘": 10, "最高": 12, "最低": 9, "收盘": 11, "成交量": 100}])
    stock = SimpleNamespace(get_quote_history=lambda *args, **kwargs: frame)
    monkeypatch.setattr(EfinanceProvider, "_module", lambda self: SimpleNamespace(stock=stock))

    result = EfinanceProvider().fetch_chart(provider_request("600519"))

    assert result["points"][0]["volume"] == 100.0


def test_yahoo_adapter_maps_chart_payload(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1],
                        "meta": {"currency": "USD", "exchangeName": "NMS"},
                        "indicators": {"quote": [{"open": [10], "high": [12], "low": [9], "close": [11], "volume": [100]}]},
                    }]
                }
            }

    monkeypatch.setattr("app.tools.market_providers.requests.get", lambda *args, **kwargs: Response())

    result = YahooProvider().fetch_chart(provider_request("AAPL"))

    assert result["points"][0]["close"] == 11.0
    assert result["currency"] == "USD"


def test_finnhub_adapter_maps_candles(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"s": "ok", "t": [1], "o": [10], "h": [12], "l": [9], "c": [11], "v": [100]}

    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr("app.tools.market_providers.requests.get", lambda *args, **kwargs: Response())

    result = FinnhubProvider().fetch_chart(provider_request("AAPL"))

    assert result["points"][0]["close"] == 11.0


def test_baostock_adapter_logs_out(monkeypatch) -> None:
    class QueryResult:
        error_code = "0"
        fields = ["date", "open", "high", "low", "close", "volume"]

        def __init__(self) -> None:
            self.used = False

        def next(self) -> bool:
            if self.used:
                return False
            self.used = True
            return True

        def get_row_data(self) -> list[str]:
            return ["2026-01-02", "10", "12", "9", "11", "100"]

    calls = []
    module = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0"),
        query_history_k_data_plus=lambda *args, **kwargs: QueryResult(),
        logout=lambda: calls.append("logout"),
    )
    monkeypatch.setattr(BaostockProvider, "_module", lambda self: module)

    result = BaostockProvider().fetch_chart(provider_request("600519"))

    assert result["points"][0]["close"] == 11.0
    assert calls == ["logout"]


class FakeProvider:
    def __init__(self, name: str, *, markets: set[str], points=None, available=True, error=None) -> None:
        self.name = name
        self.markets = markets
        self.points = points if points is not None else []
        self.available = available
        self.error = error
        self.calls = 0

    def supports(self, market: str) -> bool:
        return market in self.markets

    def is_available(self) -> bool:
        return self.available

    def fetch_chart(self, request) -> dict:
        self.calls += 1
        if self.error:
            raise self.error
        return {"symbol": request.symbol.local_symbol, "points": self.points}


VALID_POINTS = [
    {"time": 1, "open": 9, "high": 11, "low": 8, "close": 10, "volume": 100},
    {"time": 2, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 120},
]


def test_auto_router_uses_market_specific_primary(monkeypatch) -> None:
    akshare = FakeProvider("akshare", markets={"cn", "hk"}, points=VALID_POINTS)
    yahoo = FakeProvider("yahoo", markets={"cn", "hk", "us"}, points=VALID_POINTS)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"akshare": akshare, "yahoo": yahoo})
    monkeypatch.setenv("MARKET_DATA_PROVIDER_ORDER_CN", "akshare,yahoo")

    result = get_market_chart("600519", "auto")

    assert result["provider"] == "akshare"
    assert result["market"] == "cn"
    assert result["canonical_symbol"] == "SH600519"
    assert result["provider_attempts"] == [
        {"provider": "akshare", "status": "success", "reason": "", "duration_ms": result["provider_attempts"][0]["duration_ms"]}
    ]
    assert yahoo.calls == 0


def test_auto_router_falls_back_and_records_attempts(monkeypatch) -> None:
    akshare = FakeProvider("akshare", markets={"cn"}, error=RuntimeError("secret=do-not-leak"))
    efinance = FakeProvider("efinance", markets={"cn"}, points=[])
    baostock = FakeProvider("baostock", markets={"cn"}, available=False)
    yahoo = FakeProvider("yahoo", markets={"cn"}, points=VALID_POINTS)
    monkeypatch.setattr(
        "app.tools.market_data._provider_registry",
        lambda: {item.name: item for item in (akshare, efinance, baostock, yahoo)},
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER_ORDER_CN", "akshare,efinance,baostock,yahoo")

    result = get_market_chart("600519", "auto")

    assert result["provider"] == "yahoo"
    assert result["provider_mode"] == "auto"
    assert result["fallback_from"] == "akshare"
    assert [attempt["status"] for attempt in result["provider_attempts"]] == [
        "failed",
        "empty",
        "unavailable",
        "success",
    ]
    assert "do-not-leak" not in str(result["provider_attempts"])


def test_explicit_provider_never_falls_back(monkeypatch) -> None:
    akshare = FakeProvider("akshare", markets={"cn"}, points=[])
    yahoo = FakeProvider("yahoo", markets={"cn"}, points=VALID_POINTS)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"akshare": akshare, "yahoo": yahoo})

    result = get_market_chart("600519", "akshare")

    assert result["points"] == []
    assert [attempt["provider"] for attempt in result["provider_attempts"]] == ["akshare"]
    assert yahoo.calls == 0


def test_all_provider_failures_return_stable_error(monkeypatch) -> None:
    yahoo = FakeProvider("yahoo", markets={"us"}, error=TimeoutError("network detail"))
    finnhub = FakeProvider("finnhub", markets={"us"}, available=False)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"yahoo": yahoo, "finnhub": finnhub})
    monkeypatch.setenv("MARKET_DATA_PROVIDER_ORDER_US", "yahoo,finnhub")

    result = get_market_chart("AAPL", "auto")

    assert result["points"] == []
    assert result["error"] == "All market data providers failed."
    assert [attempt["status"] for attempt in result["provider_attempts"]] == ["failed", "unavailable"]


def test_invalid_or_duplicate_order_entries_are_ignored(monkeypatch) -> None:
    yahoo = FakeProvider("yahoo", markets={"us"}, points=VALID_POINTS)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"yahoo": yahoo})
    monkeypatch.setenv("MARKET_DATA_PROVIDER_ORDER_US", "unknown,yahoo,yahoo")

    result = get_market_chart("AAPL", "auto")

    assert result["provider"] == "yahoo"
    assert yahoo.calls == 1
