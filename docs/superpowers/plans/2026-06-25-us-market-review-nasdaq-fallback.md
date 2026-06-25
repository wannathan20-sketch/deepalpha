# US Market Review Nasdaq Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the US market review under Yahoo HTTP 429 responses by adding a keyless Nasdaq fallback with explicit ETF-proxy quality metadata.

**Architecture:** Add one `NasdaqProvider` behind the existing provider protocol and router. Limit its symbol mapping to the three US review instruments, pass proxy metadata through the existing market-review serializer, and preserve stable failures when no provider succeeds.

**Tech Stack:** Python 3.11, Requests, FastAPI service helpers, Pytest, Zeabur CLI.

---

## File Structure

- Modify `app/tools/market_providers.py`: implement Nasdaq request mapping, parsing, and proxy metadata.
- Modify `app/tools/market_data.py`: register Nasdaq and place it between Yahoo and Finnhub for US auto routing.
- Modify `app/services/market_review.py`: expose proxy metadata and add the quality warning to summaries.
- Modify `tests/test_market_data.py`: cover Nasdaq parsing, mapping, unsupported symbols, and routing.
- Modify `tests/test_market_review.py`: cover proxy metadata and quality warning.
- Modify `.env.example`, `.env.zeabur.example`, and `render.yaml`: document the new default provider order.
- Modify `README.md`: document Nasdaq fallback and ETF proxy semantics.

### Task 1: Nasdaq Provider Adapter

**Files:**
- Modify: `tests/test_market_data.py`
- Modify: `app/tools/market_providers.py`

- [ ] **Step 1: Write failing support and direct-index tests**

Add `NasdaqProvider` to the test imports and support matrix. Add a mocked Nasdaq
response test:

```python
def test_nasdaq_adapter_maps_composite_index(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "symbol": "COMP",
                    "company": "NASDAQ Composite Index",
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
```

- [ ] **Step 2: Run the direct-index test and verify RED**

Run:

```bash
pytest tests/test_market_data.py::test_nasdaq_adapter_maps_composite_index -q
```

Expected: collection or import failure because `NasdaqProvider` does not exist.

- [ ] **Step 3: Write failing ETF-proxy and unsupported-symbol tests**

```python
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


def test_nasdaq_adapter_returns_empty_for_unmapped_symbol(monkeypatch) -> None:
    called = False

    def fake_get(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.tools.market_providers.requests.get", fake_get)

    result = NasdaqProvider().fetch_chart(provider_request("AAPL"))

    assert result["points"] == []
    assert called is False
```

- [ ] **Step 4: Implement the minimal Nasdaq adapter**

In `app/tools/market_providers.py`, add:

```python
NASDAQ_REVIEW_SYMBOLS = {
    "^GSPC": {
        "symbol": "SPY",
        "asset_class": "etf",
        "instrument_type": "etf_proxy",
    },
    "^IXIC": {
        "symbol": "COMP",
        "asset_class": "index",
        "instrument_type": "index",
    },
    "^DJI": {
        "symbol": "DIA",
        "asset_class": "etf",
        "instrument_type": "etf_proxy",
    },
}


class NasdaqProvider:
    name = "nasdaq"

    def supports(self, market: str) -> bool:
        return market == "us"

    def is_available(self) -> bool:
        return True

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        original_symbol = request.symbol.yahoo_symbol
        mapping = NASDAQ_REVIEW_SYMBOLS.get(original_symbol)
        if mapping is None:
            return {"symbol": request.symbol.local_symbol, "points": []}

        symbol = mapping["symbol"]
        asset_class = mapping["asset_class"]
        response = requests.get(
            f"https://api.nasdaq.com/api/quote/{quote(symbol)}/chart",
            params={"assetclass": asset_class},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DeepAlpha/0.1)",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "10")),
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        rows = [
            {"time": item.get("x"), "close": item.get("y")}
            for item in data.get("chart") or []
        ]
        result = {
            "symbol": symbol,
            "exchange": "US",
            "instrument_type": mapping["instrument_type"],
            "source_url": (
                f"https://www.nasdaq.com/market-activity/"
                f"{asset_class}/{symbol.lower()}"
            ),
            "points": normalize_points(rows),
        }
        if mapping["instrument_type"] == "etf_proxy":
            result["proxy_symbol"] = symbol
            result["proxy_for"] = original_symbol
        return result
```

- [ ] **Step 5: Run adapter tests and verify GREEN**

Run:

```bash
pytest tests/test_market_data.py -q
```

Expected: all market-data tests pass.

- [ ] **Step 6: Commit the adapter**

```bash
git add app/tools/market_providers.py tests/test_market_data.py
git commit -m "Add Nasdaq market data provider"
```

### Task 2: US Auto-Routing

**Files:**
- Modify: `tests/test_market_data.py`
- Modify: `app/tools/market_data.py`

- [ ] **Step 1: Write a failing Yahoo-to-Nasdaq routing test**

```python
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
```

- [ ] **Step 2: Run the routing test and verify RED**

Run:

```bash
pytest tests/test_market_data.py::test_us_auto_router_falls_back_from_yahoo_to_nasdaq -q
```

Expected: failure because the default US order does not include Nasdaq.

- [ ] **Step 3: Register Nasdaq and update the default order**

Import `NasdaqProvider`, change:

```python
"us": ["yahoo", "nasdaq", "finnhub"],
```

and instantiate `NasdaqProvider()` between Yahoo and Finnhub in
`_provider_registry`.

- [ ] **Step 4: Run routing tests and verify GREEN**

Run:

```bash
pytest tests/test_market_data.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit routing**

```bash
git add app/tools/market_data.py tests/test_market_data.py
git commit -m "Route US market data through Nasdaq fallback"
```

### Task 3: Market Review Proxy Quality Metadata

**Files:**
- Modify: `tests/test_market_review.py`
- Modify: `app/services/market_review.py`

- [ ] **Step 1: Write a failing proxy-output test**

```python
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
```

- [ ] **Step 2: Run the proxy-output test and verify RED**

Run:

```bash
pytest tests/test_market_review.py::test_market_review_exposes_etf_proxy_warning -q
```

Expected: failure because metadata and summary warning are not passed through.

- [ ] **Step 3: Pass metadata through and append a quality warning**

In `_index_from_chart`, include:

```python
"instrument_type": chart.get("instrument_type", "index"),
"proxy_symbol": chart.get("proxy_symbol"),
"proxy_for": chart.get("proxy_for"),
```

Remove `None` proxy fields before returning the item. In `_summary`, detect
`instrument_type == "etf_proxy"` and append:

```python
lines.append(
    "S&P 500、Dow 中的可用项可能采用 ETF 代理，精确指数点位请结合指数行情终端复核。"
)
```

- [ ] **Step 4: Run market-review tests and verify GREEN**

Run:

```bash
pytest tests/test_market_review.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit review metadata**

```bash
git add app/services/market_review.py tests/test_market_review.py
git commit -m "Expose market review proxy data quality"
```

### Task 4: Configuration And Documentation

**Files:**
- Modify: `.env.example`
- Modify: `.env.zeabur.example`
- Modify: `render.yaml`
- Modify: `README.md`

- [ ] **Step 1: Update provider-order examples**

Change every US default to:

```text
MARKET_DATA_PROVIDER_ORDER_US=yahoo,nasdaq,finnhub
```

- [ ] **Step 2: Document provider and proxy semantics**

In the market-review README section, state that Yahoo remains primary, Nasdaq
is the keyless fallback, Nasdaq Composite is direct index data, and S&P 500 /
Dow may use SPY / DIA ETF proxies with explicit metadata.

- [ ] **Step 3: Verify documentation consistency**

Run:

```bash
rg -n "MARKET_DATA_PROVIDER_ORDER_US|ETF proxy|ETF 代理|nasdaq" \
  .env.example .env.zeabur.example render.yaml README.md
git diff --check
```

Expected: all three configuration files show the same order and diff check
produces no output.

- [ ] **Step 4: Commit configuration and docs**

```bash
git add .env.example .env.zeabur.example render.yaml README.md
git commit -m "Document Nasdaq market review fallback"
```

### Task 5: Verification, Push, Deploy, And Production Smoke Test

**Files:**
- No additional source files expected.

- [ ] **Step 1: Run targeted backend tests**

```bash
pytest tests/test_market_data.py tests/test_market_review.py tests/test_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the complete backend suite**

```bash
pytest -q
```

Expected: all tests pass with no new warnings.

- [ ] **Step 3: Run frontend regression checks**

```bash
cd frontend
npm test -- --run
npm run build
```

Expected: frontend tests and Vite build pass.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

Expected: the latest implementation commits appear on `origin/main`.

- [ ] **Step 5: Deploy a clean archive to the existing Zeabur service**

Create a temporary archive from `HEAD`, then run:

```bash
zeabur deploy \
  --project-id 6a1e814b8fd5d6b81d7ad706 \
  --service-id 6a1e8248d8f8814aa285d8a6 \
  --environment-id 6a1e814bb0fc054c4cc406d0 \
  --json
```

Expected: Zeabur accepts the deployment for the existing `deepalpha` service.

- [ ] **Step 6: Verify production behavior**

Request:

```bash
curl -fsS 'https://deepalpha.zeabur.app/market/review?market=us'
```

Expected:

- top-level and US `context_status` are `available`;
- three indices are present;
- Yahoo HTTP 429 attempts remain visible when rate-limited;
- Nasdaq attempts succeed;
- S&P 500 contains `proxy_symbol=SPY`;
- Dow contains `proxy_symbol=DIA`;
- summary contains the ETF proxy warning;
- no mock data is returned.
