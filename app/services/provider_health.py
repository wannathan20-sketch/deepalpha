from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import perf_counter
import re

from app.tools.market_data import get_market_chart


PROVIDER_PROBES = [
    {"provider": "akshare_hk_index", "market": "hk", "symbol": "^HSI", "exchange": "HKEX"},
    {"provider": "yahoo", "market": "hk", "symbol": "^HSI", "exchange": "HKEX"},
    {"provider": "nasdaq", "market": "us", "symbol": "^IXIC", "exchange": "US"},
    {"provider": "akshare", "market": "cn", "symbol": "000001.SH", "exchange": "SSE"},
    {"provider": "efinance", "market": "cn", "symbol": "000001.SH", "exchange": "SSE"},
    {"provider": "baostock", "market": "cn", "symbol": "000001.SH", "exchange": "SSE"},
    {"provider": "finnhub", "market": "us", "symbol": "AAPL", "exchange": "US"},
]
CORE_MARKETS = ["cn", "hk", "us"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_reason(reason: str) -> str:
    clean = str(reason or "").strip()
    if not clean:
        return ""
    http_match = re.search(r"\bHTTP\s+\d{3}\b", clean, flags=re.IGNORECASE)
    if http_match:
        return http_match.group(0).upper()
    known_reasons = {
        "Provider is not configured or installed.",
        "Provider returned insufficient points.",
        "Provider does not support this market.",
        "All market data providers failed.",
        "No market data provider is configured.",
    }
    if clean in known_reasons:
        return clean
    if clean.endswith("Error") or clean.endswith("Exception") or clean.endswith("Timeout"):
        return clean[:80]
    return "Provider probe failed."


def _attempt_from_chart(chart: dict, provider: str) -> dict:
    attempts = [
        attempt
        for attempt in chart.get("provider_attempts", [])
        if attempt.get("provider") == provider
    ]
    return attempts[-1] if attempts else {}


def _probe_provider(spec: dict) -> dict:
    started = perf_counter()
    checked_at = _now_iso()
    provider = spec["provider"]
    try:
        chart = get_market_chart(
            spec["symbol"],
            provider,
            "1mo",
            "1d",
            exchange=spec.get("exchange"),
        )
        attempt = _attempt_from_chart(chart, provider)
        points = chart.get("points", [])
        attempt_status = attempt.get("status", "")
        healthy = attempt_status == "success" and len(points) >= 2
        status = "healthy" if healthy else "unavailable" if attempt_status == "unavailable" else "degraded"
        reason = "" if healthy else _sanitize_reason(attempt.get("reason") or chart.get("error") or attempt_status)
        source_url = chart.get("source_url") or chart.get("yahoo_chart_url") or ""
    except Exception as exc:
        status = "degraded"
        reason = _sanitize_reason(type(exc).__name__)
        source_url = ""

    return {
        "provider": provider,
        "market": spec["market"],
        "symbol": spec["symbol"],
        "status": status,
        "latency_ms": round((perf_counter() - started) * 1000),
        "reason": reason,
        "source_url": source_url,
        "checked_at": checked_at,
    }


def _market_coverage(providers: list[dict]) -> dict:
    markets = {}
    for market in CORE_MARKETS:
        healthy_providers = [
            item["provider"]
            for item in providers
            if item["market"] == market and item["status"] == "healthy"
        ]
        markets[market] = {
            "healthy": bool(healthy_providers),
            "healthy_providers": healthy_providers,
        }
    return markets


def _overall_status(markets: dict) -> str:
    healthy_count = sum(1 for item in markets.values() if item["healthy"])
    if healthy_count == len(CORE_MARKETS):
        return "ok"
    if healthy_count:
        return "degraded"
    return "unavailable"


def build_provider_health(ttl_seconds: int = 300) -> dict:
    with ThreadPoolExecutor(max_workers=len(PROVIDER_PROBES)) as executor:
        futures = [executor.submit(_probe_provider, spec) for spec in PROVIDER_PROBES]
        providers = [future.result() for future in as_completed(futures)]

    order = {spec["provider"]: index for index, spec in enumerate(PROVIDER_PROBES)}
    providers.sort(key=lambda item: order.get(item["provider"], 999))
    markets = _market_coverage(providers)
    return {
        "status": _overall_status(markets),
        "checked_at": _now_iso(),
        "ttl_seconds": ttl_seconds,
        "providers": providers,
        "markets": markets,
    }
