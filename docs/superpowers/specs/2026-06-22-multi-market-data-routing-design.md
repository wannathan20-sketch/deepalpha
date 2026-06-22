# Multi-Market Data Routing Design

## Goal

Extend DeepAlpha's daily market-data path from a single Yahoo Finance source to
a small, reliable provider chain for A-share, Hong Kong, and US equities. Keep
the existing `/market/chart` and full-analysis contracts compatible while
making provider selection, fallback, and failure visible to
`AnalysisContextPack`.

## Scope

This phase covers six-month daily OHLCV market data only.

It does not add A-share or Hong Kong financial statements, persistent news
feeds, intraday streaming quotes, portfolio valuation, or trading calendars.
Those remain separate phases so provider failures in one domain do not expand
the blast radius of this change.

## Provider Strategy

Automatic routing uses a short provider chain inspired by
`daily_stock_analysis`, without copying its full provider inventory.

| Market | Automatic provider order | Availability |
| --- | --- | --- |
| A-share | Efinance, AkShare, Baostock, Yahoo | First three are local Python adapters; Yahoo is the final delayed-data fallback |
| Hong Kong | Yahoo, AkShare | Both work without a paid account |
| US | Yahoo, Finnhub | Finnhub is skipped unless `FINNHUB_API_KEY` is configured |

Yahoo remains first for Hong Kong and US stocks to preserve current behavior.
SEC Companyfacts remains the US financial source and is not changed by this
phase.

Efinance, AkShare, and Baostock are added to the project's pinned runtime
dependencies because A-share support is a core target. They are still loaded
lazily: a broken or unavailable installation is recorded as an unavailable
attempt instead of preventing application startup.

## Architecture

### Normalized request

A focused symbol-normalization function derives:

- `market`: `cn`, `hk`, or `us`;
- `canonical_symbol`: stable symbol stored in diagnostics;
- provider-specific symbols such as `600519`, `0700.HK`, or `AAPL`.

Supported input examples include `600519`, `SH600519`, `600519.SH`,
`SZ000001`, `HK00700`, `0700.HK`, `NASDAQ:AAPL`, and `AAPL`.

Six-digit numeric symbols default to A-share semantics. Five-digit numeric or
`.HK` symbols use Hong Kong semantics. Alphabetic tickers default to US
semantics. An explicit exchange takes precedence when the caller provides it.

### Provider interface

Each provider adapter implements the same behavior:

```python
class MarketDataProvider(Protocol):
    name: str

    def supports(self, market: str) -> bool: ...
    def is_available(self) -> bool: ...
    def fetch_chart(self, request: MarketChartRequest) -> dict: ...
```

Provider-specific parsing stays inside its adapter. The router only receives
normalized chart dictionaries and does not know AkShare, Efinance, Baostock,
Yahoo, or Finnhub response shapes.

### Router

`get_market_chart` remains the public entry point.

- `provider=auto` detects the market and tries the configured chain in order.
- An explicit provider tries only that provider. It does not silently switch
  sources.
- A provider succeeds only when it returns at least two valid close prices.
- Unsupported, unavailable, empty, and failed attempts are recorded
  independently.
- The router stops at the first successful provider.

The existing response fields remain. Successful responses add:

```text
market
canonical_symbol
provider_mode
provider_attempts
fallback_from
```

`fallback_from` is absent for a primary-source success and contains the first
failed provider when a later provider succeeds.

If every provider fails, the response contains `points=[]`, `market`,
`canonical_symbol`, `provider="auto"`, `provider_attempts`, and a stable summary
under `error`. It never fabricates price points.

## Data Normalization

All adapters return the current chart schema:

```text
time, open, high, low, close, volume
```

Rows without a timestamp or close are discarded. Numeric values are converted
to plain Python numbers. Results are ordered by ascending timestamp and
duplicate timestamps are removed. This keeps `build_market_profile` unchanged
for trend, return, moving-average, and volatility calculations.

## Reliability And Observability

Every attempt records:

```text
provider, status, reason, duration_ms
```

Allowed attempt statuses are `success`, `empty`, `unavailable`, `unsupported`,
and `failed`. Exception details are reduced to a stable reason string; secrets
and API keys are never included.

`build_market_profile` continues to emit `available`, `missing`, or
`fetch_failed`. On fallback success it additionally emits `context_status` as
`fallback` and includes `fallback_from`, so the existing analysis-context
builder can reduce the quality score without rejecting usable data.

## Configuration

The existing `data_provider` request field remains valid. Supported values
become `auto`, `yahoo`, `efinance`, `akshare`, `baostock`, and `finnhub`.

New environment configuration is limited to:

```text
MARKET_DATA_PROVIDER_ORDER_CN
MARKET_DATA_PROVIDER_ORDER_HK
MARKET_DATA_PROVIDER_ORDER_US
FINNHUB_API_KEY
MARKET_DATA_TIMEOUT_SECONDS
```

Invalid or duplicate provider names are ignored. If an override produces an
empty chain, the built-in market order is used.

## Testing

Tests use provider fakes and do not call live networks.

Coverage includes:

- symbol and market detection for A-share, Hong Kong, and US formats;
- exact provider order for each market;
- skipping unavailable optional providers;
- fallback after exception or empty data;
- no fallback for an explicitly selected provider;
- normalized ordering and duplicate removal;
- complete diagnostic attempts when every source fails;
- `build_market_profile` marking fallback success correctly;
- existing `/market/chart` and `/analyze` compatibility;
- complete backend suite and frontend production build.

## Delivery Boundaries

Implementation must preserve all unrelated dirty worktree changes. Provider
adapters, routing, and tests are committed separately where practical. Live
provider smoke tests are optional diagnostics and are not part of deterministic
CI verification.
