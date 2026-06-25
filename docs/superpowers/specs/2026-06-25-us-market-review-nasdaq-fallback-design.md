# US Market Review Nasdaq Fallback Design

## Goal

Restore DeepAlpha's US market review when Yahoo Finance rate-limits the Zeabur
outbound IP. Add a small, keyless Nasdaq data adapter to the existing market
provider chain without changing the `/market/review` response contract or
fabricating index prices.

## Scope

This change covers the three instruments used by the US market review:

- S&P 500;
- Nasdaq Composite;
- Dow Jones Industrial Average.

It does not replace the general US equity provider path, add intraday trading
features, or introduce a broad symbol-mapping catalog.

## Provider Strategy

The automatic US order becomes:

```text
Yahoo -> Nasdaq -> Finnhub
```

Yahoo remains primary to preserve the existing behavior. Nasdaq is a keyless
fallback that is usable from Zeabur. Finnhub remains the final optional source
when `FINNHUB_API_KEY` is configured.

Nasdaq Composite uses Nasdaq's `COMP` index data. Nasdaq's public endpoint does
not expose the S&P 500 and Dow symbols through the same chart route, so those
two entries use liquid ETF proxies:

| Review entry | Nasdaq request | Data meaning |
| --- | --- | --- |
| S&P 500 | `SPY`, asset class `etf` | SPDR S&P 500 ETF proxy |
| Nasdaq | `COMP`, asset class `index` | Nasdaq Composite index |
| Dow | `DIA`, asset class `etf` | SPDR Dow Jones Industrial Average ETF proxy |

Proxy instruments keep their original review labels for UI continuity, but
the response explicitly marks them as proxies. Consumers must not interpret a
proxy close price as the numerical index level.

## Adapter And Mapping

Add a `NasdaqProvider` implementing the existing `MarketDataProvider`
interface. It supports the US market and requires no API key.

The adapter uses a deliberately small mapping keyed by the existing Yahoo
symbols:

```text
^GSPC -> SPY / etf / proxy
^IXIC -> COMP / index / direct
^DJI  -> DIA / etf / proxy
```

Other US symbols return an empty result so the router may continue to Finnhub.
The adapter parses Nasdaq chart timestamps and close values into the existing
normalized point schema. The source URL points to the corresponding Nasdaq
market-activity page.

Successful adapter results add:

```text
instrument_type: index | etf_proxy
proxy_symbol: SPY | DIA
proxy_for: ^GSPC | ^DJI
```

Proxy fields are omitted for direct index data.

## Market Review Output

`_index_from_chart` passes through `instrument_type`, `proxy_symbol`, and
`proxy_for`. Existing fields remain compatible.

When one or more review entries use an ETF proxy:

- `context_status` remains `available` if all three entries are present;
- each proxied entry is visibly marked;
- the summary adds a data-quality sentence stating that S&P 500 or Dow uses an
  ETF proxy and should be verified against an index terminal for exact levels.

No mock data is introduced. If Yahoo, Nasdaq, and configured Finnhub sources
all fail, the endpoint continues returning `fetch_failed` with provider
attempts.

## Configuration

The built-in and example US provider order becomes:

```text
MARKET_DATA_PROVIDER_ORDER_US=yahoo,nasdaq,finnhub
```

No new secret or runtime dependency is required.

## Testing

Tests remain deterministic and mock network calls.

Coverage includes:

- Nasdaq provider support and availability;
- direct Nasdaq Composite response parsing;
- SPY and DIA proxy mapping and metadata;
- unsupported symbols returning no points;
- automatic routing from Yahoo failure to Nasdaq success;
- market-review proxy metadata and quality warning;
- unchanged all-provider failure behavior;
- complete backend suite and frontend production build.

## Production Verification

After deployment:

1. confirm the Zeabur deployment reaches `RUNNING`;
2. request `/market/review?market=us`;
3. verify all three entries are returned;
4. verify Yahoo's HTTP 429 attempt is retained and Nasdaq succeeds;
5. verify S&P 500 and Dow are marked as ETF proxies;
6. verify no mock fallback appears.
