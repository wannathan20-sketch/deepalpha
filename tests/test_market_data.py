import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import requests

from app.tools.market_symbols import normalize_market_symbol
from app.tools.market_data import get_market_chart
from app.tools.market_providers import (
    AkShareHKIndexProvider,
    AkShareProvider,
    BaostockProvider,
    EfinanceProvider,
    FinnhubProvider,
    MarketChartRequest,
    NasdaqProvider,
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
        ("^HSI", None, "hk", "HKHSI", "^HSI", "HSI"),
        ("^HSTECH", None, "hk", "HKHSTECH", "^HSTECH", "HSTECH"),
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
        (AkShareHKIndexProvider(), {"hk"}),
        (AkShareProvider(), {"cn", "hk"}),
        (EfinanceProvider(), {"cn"}),
        (BaostockProvider(), {"cn"}),
        (NasdaqProvider(), {"us"}),
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


def test_akshare_hk_index_adapter_maps_hang_seng_index(monkeypatch) -> None:
    frame = FakeFrame(
        [
            {"日期": "2026-01-02", "开盘": 22000, "最高": 22100, "最低": 21900, "收盘": 22050, "成交量": 100},
            {"日期": "2026-01-03", "开盘": 22050, "最高": 22200, "最低": 22000, "收盘": 22150, "成交量": 120},
        ]
    )
    captured = {}

    def fake_daily(symbol: str):
        captured["symbol"] = symbol
        return frame

    module = SimpleNamespace(stock_hk_index_daily_sina=fake_daily)
    monkeypatch.setattr(AkShareHKIndexProvider, "_module", lambda self: module)

    result = AkShareHKIndexProvider().fetch_chart(provider_request("^HSI"))

    assert captured["symbol"] == "HSI"
    assert result["symbol"] == "HSI"
    assert result["instrument_type"] == "index"
    assert result["source_url"] == "https://stock.finance.sina.com.cn/hkstock/quotes/HSI.html"
    assert [point["close"] for point in result["points"]] == [22050.0, 22150.0]


def test_akshare_hk_index_adapter_maps_hang_seng_tech(monkeypatch) -> None:
    frame = FakeFrame([{"日期": "2026-01-02", "收盘": 4300}])
    captured = {}

    def fake_daily(symbol: str):
        captured["symbol"] = symbol
        return frame

    module = SimpleNamespace(stock_hk_index_daily_sina=fake_daily)
    monkeypatch.setattr(AkShareHKIndexProvider, "_module", lambda self: module)

    result = AkShareHKIndexProvider().fetch_chart(provider_request("^HSTECH"))

    assert captured["symbol"] == "HSTECH"
    assert result["points"][0]["close"] == 4300.0


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


def test_yahoo_adapter_falls_back_to_query2_after_query1_http_error(monkeypatch) -> None:
    calls = []

    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                error = requests.HTTPError(f"HTTP {self.status_code}")
                error.response = self
                raise error

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1, 2],
                        "meta": {"currency": "USD", "exchangeName": "SNP"},
                        "indicators": {
                            "quote": [{
                                "open": [10, 11],
                                "high": [12, 13],
                                "low": [9, 10],
                                "close": [11, 12],
                                "volume": [100, 120],
                            }]
                        },
                    }]
                }
            }

    def fake_get(url, **kwargs):
        calls.append(url)
        return Response(429 if "query1" in url else 200)

    monkeypatch.setattr("app.tools.market_providers.requests.get", fake_get)

    result = YahooProvider().fetch_chart(provider_request("^GSPC"))

    assert len(result["points"]) == 2
    assert result["yahoo_host"] == "query2.finance.yahoo.com"
    assert [url.split("/")[2] for url in calls] == [
        "query1.finance.yahoo.com",
        "query2.finance.yahoo.com",
    ]


def test_nasdaq_adapter_maps_composite_index(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "symbol": "COMP",
                    "company": "NASDAQ Composite Index",
                    "lastSalePrice": "25,476.64",
                    "previousClose": "25,587.04",
                    "volume": None,
                    "chart": [
                        {"x": 1782293458000, "y": 25607.48},
                        {"x": 1782293518000, "y": 25613.18},
                    ],
                }
            }

    monkeypatch.setattr(
        "app.tools.market_providers.requests.get",
        lambda *args, **kwargs: Response(),
    )

    result = NasdaqProvider().fetch_chart(provider_request("^IXIC"))

    assert [point["close"] for point in result["points"]] == [25607.48, 25613.18]
    assert result["instrument_type"] == "index"
    assert "proxy_symbol" not in result


@pytest.mark.parametrize(
    ("raw_symbol", "expected_symbol"),
    [("^GSPC", "SPY"), ("^DJI", "DIA")],
)
def test_nasdaq_adapter_marks_etf_proxies(
    monkeypatch,
    raw_symbol: str,
    expected_symbol: str,
) -> None:
    requested = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "symbol": expected_symbol,
                    "chart": [
                        {"x": 1782293458000, "y": 500},
                        {"x": 1782293518000, "y": 501},
                    ],
                }
            }

    def fake_get(url, **kwargs):
        requested["url"] = url
        requested["params"] = kwargs.get("params")
        return Response()

    monkeypatch.setattr("app.tools.market_providers.requests.get", fake_get)

    result = NasdaqProvider().fetch_chart(provider_request(raw_symbol))

    assert expected_symbol in requested["url"]
    assert requested["params"] == {"assetclass": "etf"}
    assert result["instrument_type"] == "etf_proxy"
    assert result["proxy_symbol"] == expected_symbol
    assert result["proxy_for"] == raw_symbol


def test_nasdaq_adapter_fetches_individual_stocks(monkeypatch) -> None:
    """NasdaqProvider should now request individual stocks via assetclass=stocks
    and use full chart data when available."""
    import time as _time

    now_ms = int(_time.time() * 1000)
    day_ms = 86_400_000

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "chart": [
                        {"x": now_ms - day_ms * 5, "y": 275.0},
                        {"x": now_ms - day_ms * 4, "y": 278.0},
                        {"x": now_ms - day_ms * 3, "y": 282.0},
                        {"x": now_ms - day_ms * 2, "y": 280.0},
                        {"x": now_ms - day_ms, "y": 283.78},
                        {"x": now_ms, "y": 281.74},
                    ],
                    "lastSalePrice": "$281.74",
                    "previousClose": "$283.78",
                    "volume": "66,427,169",
                }
            }

    kwargs_captured = {}

    def fake_get(url, **kwargs):
        kwargs_captured["url"] = url
        kwargs_captured["params"] = kwargs.get("params", {})
        return Response()

    monkeypatch.setattr("app.tools.market_providers.requests.get", fake_get)

    result = NasdaqProvider().fetch_chart(provider_request("AAPL"))

    assert len(result["points"]) == 6
    assert result["points"][0]["close"] == 275.0
    assert result["symbol"] == "AAPL"
    assert result["instrument_type"] == "stock"
    assert kwargs_captured["params"]["assetclass"] == "stocks"


def test_nasdaq_adapter_still_handles_review_indices(monkeypatch) -> None:
    """^GSPC should still be mapped to SPY ETF proxy and use chart data."""
    import time as _time

    now_ms = int(_time.time() * 1000)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "chart": [
                        {"x": now_ms - 86_400_000, "y": 600.0},
                        {"x": now_ms, "y": 605.0},
                    ],
                    "lastSalePrice": "$605.00",
                    "previousClose": "$602.00",
                }
            }

    monkeypatch.setattr("app.tools.market_providers.requests.get", lambda *a, **kw: Response())

    result = NasdaqProvider().fetch_chart(provider_request("^GSPC"))

    assert len(result["points"]) == 2
    assert result["symbol"] == "SPY"
    assert result["instrument_type"] == "etf_proxy"
    assert result["proxy_for"] == "^GSPC"


def test_nasdaq_adapter_falls_back_when_chart_empty(monkeypatch) -> None:
    """When chart data is empty, fall back to synthetic 2-point row from
    lastSalePrice + previousClose."""
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "chart": [],
                    "lastSalePrice": "$281.74",
                    "previousClose": "$283.78",
                    "volume": "66,427,169",
                }
            }

    monkeypatch.setattr("app.tools.market_providers.requests.get", lambda *a, **kw: Response())

    result = NasdaqProvider().fetch_chart(provider_request("AAPL"))

    assert len(result["points"]) == 2
    assert result["points"][1]["close"] == 281.74


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


def test_us_auto_router_falls_back_from_yahoo_to_nasdaq(monkeypatch) -> None:
    yahoo = FakeProvider(
        "yahoo",
        markets={"us"},
        error=requests.HTTPError("rate limited"),
    )
    nasdaq = FakeProvider("nasdaq", markets={"us"}, points=VALID_POINTS)
    finnhub = FakeProvider("finnhub", markets={"us"}, available=False)
    monkeypatch.setattr(
        "app.tools.market_data._provider_registry",
        lambda: {
            "yahoo": yahoo,
            "nasdaq": nasdaq,
            "finnhub": finnhub,
        },
    )
    monkeypatch.delenv("MARKET_DATA_PROVIDER_ORDER_US", raising=False)

    result = get_market_chart("^IXIC", "auto")

    assert result["provider"] == "nasdaq"
    assert result["fallback_from"] == "yahoo"
    assert [item["provider"] for item in result["provider_attempts"]] == [
        "yahoo",
        "nasdaq",
    ]


def test_hk_auto_router_prefers_akshare_index_before_yahoo(monkeypatch) -> None:
    akshare_hk_index = FakeProvider("akshare_hk_index", markets={"hk"}, points=VALID_POINTS)
    yahoo = FakeProvider("yahoo", markets={"hk"}, points=VALID_POINTS)
    akshare = FakeProvider("akshare", markets={"hk"}, points=VALID_POINTS)
    monkeypatch.setattr(
        "app.tools.market_data._provider_registry",
        lambda: {
            "akshare_hk_index": akshare_hk_index,
            "yahoo": yahoo,
            "akshare": akshare,
        },
    )
    monkeypatch.delenv("MARKET_DATA_PROVIDER_ORDER_HK", raising=False)

    result = get_market_chart("^HSI", "auto")

    assert result["provider"] == "akshare_hk_index"
    assert [item["provider"] for item in result["provider_attempts"]] == ["akshare_hk_index"]
    assert yahoo.calls == 0
    assert akshare.calls == 0


def test_http_failure_attempt_records_status_code_without_body(monkeypatch) -> None:
    response = SimpleNamespace(status_code=429, text="secret response body")
    error = requests.HTTPError("Too Many Requests", response=response)
    yahoo = FakeProvider("yahoo", markets={"us"}, error=error)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"yahoo": yahoo})

    result = get_market_chart("AAPL", "auto")

    assert result["provider_attempts"][0]["reason"] == "HTTP 429"
    assert "secret response body" not in str(result)


def test_invalid_or_duplicate_order_entries_are_ignored(monkeypatch) -> None:
    yahoo = FakeProvider("yahoo", markets={"us"}, points=VALID_POINTS)
    monkeypatch.setattr("app.tools.market_data._provider_registry", lambda: {"yahoo": yahoo})
    monkeypatch.setenv("MARKET_DATA_PROVIDER_ORDER_US", "unknown,yahoo,yahoo")

    result = get_market_chart("AAPL", "auto")

    assert result["provider"] == "yahoo"
    assert yahoo.calls == 1
