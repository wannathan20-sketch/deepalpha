import os
from datetime import datetime, timedelta, timezone
from time import perf_counter

import requests

from app.tools.market_providers import (
    AkShareProvider,
    BaostockProvider,
    EfinanceProvider,
    FinnhubProvider,
    MarketChartRequest,
    YahooProvider,
)
from app.tools.market_symbols import normalize_market_symbol


DEFAULT_PROVIDER_ORDERS = {
    "cn": ["akshare", "efinance", "baostock", "yahoo"],
    "hk": ["yahoo", "akshare"],
    "us": ["yahoo", "finnhub"],
}
RANGE_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
    "5y": 1830,
    "max": 3650,
}


def _provider_registry() -> dict:
    providers = [
        YahooProvider(),
        AkShareProvider(),
        EfinanceProvider(),
        BaostockProvider(),
        FinnhubProvider(),
    ]
    return {provider.name: provider for provider in providers}


def _provider_order(market: str, registry: dict) -> list[str]:
    env_name = f"MARKET_DATA_PROVIDER_ORDER_{market.upper()}"
    configured = [
        item.strip().lower()
        for item in os.getenv(env_name, "").split(",")
        if item.strip()
    ]
    requested = configured or DEFAULT_PROVIDER_ORDERS[market]
    deduplicated = []
    for name in requested:
        if name in registry and name not in deduplicated:
            deduplicated.append(name)
    return deduplicated or [
        name for name in DEFAULT_PROVIDER_ORDERS[market] if name in registry
    ]


def _request(
    symbol: str,
    range_: str,
    interval: str,
    exchange: str | None,
) -> MarketChartRequest:
    normalized = normalize_market_symbol(symbol, exchange)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=RANGE_DAYS.get(range_, RANGE_DAYS["6mo"]))
    return MarketChartRequest(normalized, range_, interval, start, end)


def _attempt(
    provider: str,
    status: str,
    started: float,
    reason: str = "",
) -> dict:
    return {
        "provider": provider,
        "status": status,
        "reason": reason,
        "duration_ms": round((perf_counter() - started) * 1000),
    }


def _safe_failure_reason(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError):
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code:
            return f"HTTP {status_code}"
    return type(exc).__name__


def _empty_response(
    request: MarketChartRequest,
    provider_mode: str,
    attempts: list[dict],
    error: str = "",
) -> dict:
    result = {
        "provider": provider_mode,
        "provider_mode": provider_mode,
        "symbol": request.symbol.local_symbol,
        "canonical_symbol": request.symbol.canonical_symbol,
        "market": request.symbol.market,
        "exchange": request.symbol.exchange,
        "range": request.range_,
        "interval": request.interval,
        "provider_attempts": attempts,
        "points": [],
    }
    if error:
        result["error"] = error
    return result


def get_yahoo_chart(
    symbol: str,
    range_: str = "6mo",
    interval: str = "1d",
    exchange: str | None = None,
) -> dict:
    request = _request(symbol, range_, interval, exchange)
    return YahooProvider().fetch_chart(request)


def get_market_chart(
    symbol: str,
    provider: str = "auto",
    range_: str = "6mo",
    interval: str = "1d",
    exchange: str | None = None,
) -> dict:
    provider_mode = str(provider or "auto").strip().lower() or "auto"
    try:
        request = _request(symbol, range_, interval, exchange)
    except ValueError:
        return {
            "provider": provider_mode,
            "symbol": symbol,
            "range": range_,
            "interval": interval,
            "points": [],
        }

    registry = _provider_registry()
    names = (
        _provider_order(request.symbol.market, registry)
        if provider_mode == "auto"
        else [provider_mode]
    )
    attempts = []
    first_failed = None

    for name in names:
        started = perf_counter()
        current = registry.get(name)
        if current is None or not current.supports(request.symbol.market):
            attempts.append(
                _attempt(
                    name,
                    "unsupported",
                    started,
                    "Provider does not support this market.",
                )
            )
            first_failed = first_failed or name
            continue
        if not current.is_available():
            attempts.append(
                _attempt(
                    name,
                    "unavailable",
                    started,
                    "Provider is not configured or installed.",
                )
            )
            first_failed = first_failed or name
            continue
        try:
            data = current.fetch_chart(request)
        except Exception as exc:
            attempts.append(_attempt(name, "failed", started, _safe_failure_reason(exc)))
            first_failed = first_failed or name
            continue
        points = data.get("points", [])
        if len(points) < 2:
            attempts.append(
                _attempt(
                    name,
                    "empty",
                    started,
                    "Provider returned insufficient points.",
                )
            )
            first_failed = first_failed or name
            continue

        attempts.append(_attempt(name, "success", started))
        result = {
            **data,
            "provider": name,
            "provider_mode": provider_mode,
            "canonical_symbol": request.symbol.canonical_symbol,
            "market": request.symbol.market,
            "exchange": data.get("exchange") or request.symbol.exchange,
            "range": range_,
            "interval": interval,
            "provider_attempts": attempts,
        }
        if first_failed:
            result["fallback_from"] = first_failed
        return result

    return _empty_response(
        request,
        provider_mode,
        attempts,
        "All market data providers failed."
        if attempts
        else "No market data provider is configured.",
    )
