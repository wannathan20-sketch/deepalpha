# Production Reliability Iteration Design

## Goal

Deliver the next DeepAlpha production reliability slice:

1. deploy the backend only after the `CI` workflow is green on `main`;
2. make market review data easier to trust by exposing cache, provider, source, and ETF proxy labels;
3. add a sanitized `/health/providers` endpoint that actively probes market data providers and caches results.

## Approved approach

Use GitHub Actions as the deployment gate. A new deploy workflow listens for successful `CI` workflow runs on `main`, checks out the exact tested commit, runs the Zeabur CLI non-interactively with `ZEABUR_TOKEN`, deploys the existing backend service, then smoke-checks `/health`.

Keep market review simple. The backend keeps the current short TTL cache, documents the TTL env var, exposes the runtime value, and the frontend renders existing response fields (`cache_hit`, `generated_at`, `provider`, `source_url`, `instrument_type`, `proxy_symbol`).

Add provider health as a backend-only active probe. The endpoint checks Yahoo, Nasdaq, AkShare, Efinance, Baostock, and Finnhub with safe representative symbols through the existing market-data abstraction. It returns only status, latency, market, symbol, source URL, checked time, and sanitized reason strings.

## Data contracts

`GET /health/providers` returns:

```json
{
  "status": "ok",
  "cache_hit": false,
  "checked_at": "2026-06-26T00:00:00+00:00",
  "ttl_seconds": 300,
  "providers": [
    {
      "provider": "nasdaq",
      "market": "us",
      "symbol": "^IXIC",
      "status": "healthy",
      "latency_ms": 42,
      "reason": "",
      "source_url": "https://www.nasdaq.com/...",
      "checked_at": "2026-06-26T00:00:00+00:00"
    }
  ],
  "markets": {
    "us": {"healthy": true, "healthy_providers": ["nasdaq"]},
    "cn": {"healthy": true, "healthy_providers": ["akshare"]},
    "hk": {"healthy": false, "healthy_providers": []}
  }
}
```

Provider reasons are sanitized and derived from the existing safe attempt reasons such as `HTTP 429`, `Provider returned insufficient points.`, or `Provider is not configured or installed.` No exception bodies, API keys, env vars, or response payloads are returned.

## Error handling

- Zeabur deploy workflow fails visibly if `ZEABUR_TOKEN` is missing, deploy fails, status becomes failed, or `/health` smoke check fails.
- `/health/providers` never raises because one provider fails; failures are represented per provider.
- Market review caching does not serve stale data after TTL expiry in this iteration.
- Existing production LLM behavior remains unchanged: provider failures return explicit 503 and no mock fallback.

## Testing

- Backend tests cover provider health aggregation, cache hit behavior, and sanitization.
- API tests cover `/health/providers` response shape.
- Workflow tests check the deploy gate is tied to successful `CI` workflow runs on `main` and uses the expected Zeabur identifiers.
- Existing market review tests continue to cover ETF proxy metadata.
- Frontend build verifies the simple market review labels compile.

