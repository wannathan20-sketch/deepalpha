# HK Index Provider Design

## Goal

Reduce `fetch_failed` / degraded market review results for Hong Kong indices when Yahoo Finance returns HTTP 429.

## Design

Add a lightweight `akshare_hk_index` market data provider for Hong Kong index symbols used by the market review:

- `^HSI` maps to AkShare/Sina code `HSI`.
- `^HSTECH` maps to AkShare/Sina code `HSTECH`.
- The provider returns normalized daily OHLCV points, `instrument_type=index`, and a Sina source URL.

Update symbol normalization so `^HSI` and `^HSTECH` are classified as `hk`, not `us`. This makes auto routing use the HK provider order.

Set the default HK provider order to:

```text
akshare_hk_index,yahoo,akshare
```

Yahoo remains as fallback; the general AkShare stock provider remains for HK stocks. No new API key or paid provider is required in this iteration.

## Testing

Tests cover:

- HK index symbol normalization.
- AkShare HK index adapter mapping.
- auto router preferring `akshare_hk_index` before Yahoo.
- HK market review recovering when Yahoo fails and AkShare index succeeds.
- provider health counting `akshare_hk_index` as HK coverage.

