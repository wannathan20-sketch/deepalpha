from datetime import datetime, timezone
from statistics import mean

from app.tools.market_data import get_market_chart


INDEX_GROUPS = {
    "cn": [
        {"name": "上证指数", "symbol": "000001.SH", "provider": "auto", "exchange": "SSE"},
        {"name": "深证成指", "symbol": "399001.SZ", "provider": "auto", "exchange": "SZSE"},
        {"name": "创业板指", "symbol": "399006.SZ", "provider": "auto", "exchange": "SZSE"},
        {"name": "科创50", "symbol": "000688.SH", "provider": "auto", "exchange": "SSE"},
    ],
    "hk": [
        {"name": "恒生指数", "symbol": "^HSI", "provider": "auto", "exchange": "HKEX"},
        {"name": "恒生科技指数", "symbol": "^HSTECH", "provider": "auto", "exchange": "HKEX"},
    ],
    "us": [
        {"name": "S&P 500", "symbol": "^GSPC", "provider": "auto", "exchange": "US"},
        {"name": "Nasdaq", "symbol": "^IXIC", "provider": "auto", "exchange": "US"},
        {"name": "Dow", "symbol": "^DJI", "provider": "auto", "exchange": "US"},
    ],
}
MARKET_LABELS = {"cn": "A 股", "hk": "港股", "us": "美股"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    rounded = round(float(value), digits)
    return int(rounded) if rounded.is_integer() else rounded


def _change_percent(latest: float | int | None, previous: float | int | None) -> float | None:
    if latest is None or previous in {None, 0}:
        return None
    return _round(((latest - previous) / abs(previous)) * 100)


def _index_from_chart(spec: dict, chart: dict) -> dict | None:
    points = [point for point in chart.get("points", []) if point.get("close") is not None]
    if len(points) < 2:
        return None

    latest = points[-1]
    previous = points[-2]
    item = {
        "name": spec["name"],
        "symbol": spec["symbol"],
        "latest_close": _round(latest.get("close"), 4),
        "change_percent": _change_percent(latest.get("close"), previous.get("close")),
        "volume": _round(latest.get("volume"), 2),
        "turnover": _round(latest.get("turnover"), 2),
        "provider": chart.get("provider", spec["provider"]),
        "provider_mode": chart.get("provider_mode", spec["provider"]),
        "provider_attempts": chart.get("provider_attempts", []),
        "source_url": chart.get("source_url") or chart.get("yahoo_chart_url", ""),
        "instrument_type": chart.get("instrument_type", "index"),
        "proxy_symbol": chart.get("proxy_symbol"),
        "proxy_for": chart.get("proxy_for"),
    }
    return {key: value for key, value in item.items() if value is not None}


def _market_status(indices: list[dict]) -> str:
    changes = [item["change_percent"] for item in indices if item.get("change_percent") is not None]
    if not changes:
        return "unknown"
    positives = sum(1 for change in changes if change > 0)
    negatives = sum(1 for change in changes if change < 0)
    if positives == len(changes):
        return "up"
    if negatives == len(changes):
        return "down"
    return "mixed"


def _review_status(indices: list[dict], attempts: list[dict], errors: list[str], expected_count: int) -> str:
    if len(indices) == expected_count:
        return "available"
    if indices:
        return "partial"
    if errors or any(attempt.get("status") in {"failed", "empty", "unavailable"} for attempt in attempts):
        return "fetch_failed"
    return "missing"


def _summary(market: str, status: str, indices: list[dict], errors: list[str]) -> list[str]:
    label = MARKET_LABELS.get(market, market.upper())
    if not indices:
        reason = errors[0] if errors else "No index data returned."
        return [f"{label}复盘暂不可用：{reason}"]

    changes = [item["change_percent"] for item in indices if item.get("change_percent") is not None]
    avg_change = _round(mean(changes)) if changes else None
    status_text = {"up": "偏强", "down": "走弱", "mixed": "分化", "unknown": "待确认"}[_market_status(indices)]
    leaders = sorted(indices, key=lambda item: item.get("change_percent") or -999, reverse=True)[:2]
    leader_text = "、".join(
        f"{item['name']} {item['latest_close']}（{item['change_percent']:+.2f}%）"
        for item in leaders
        if item.get("change_percent") is not None and item.get("latest_close") is not None
    )
    lines = [f"{label}主要指数{status_text}，平均涨跌幅 {avg_change if avg_change is not None else 'N/A'}%。"]
    if leader_text:
        lines.append(f"相对强势指数：{leader_text}。")
    if status == "partial":
        lines.append("部分指数或板块数据缺失，需结合交易所/行情终端复核。")
    if any(item.get("instrument_type") == "etf_proxy" for item in indices):
        lines.append("部分指数通过 ETF 拟合，数据仅供参考。")
    return lines


def _build_single_market_review(market: str) -> dict:
    specs = INDEX_GROUPS[market]
    indices = []
    provider_attempts = []
    errors = []

    for spec in specs:
        chart = get_market_chart(
            spec["symbol"],
            spec["provider"],
            "1mo",
            "1d",
            exchange=spec.get("exchange"),
        )
        attempts = chart.get("provider_attempts", [])
        provider_attempts.extend(attempts)
        index = _index_from_chart(spec, chart)
        if index:
            indices.append(index)
        else:
            reason = str(chart.get("error") or "Insufficient index data.").strip()
            errors.append(f"{spec['name']}: {reason}")

    status = _review_status(indices, provider_attempts, errors, len(specs))
    return {
        "market": market,
        "context_status": status,
        "market_status": _market_status(indices),
        "indices": indices,
        "breadth": None,
        "hotspots": [],
        "summary": _summary(market, status, indices, errors),
        "provider_attempts": provider_attempts,
        "errors": errors,
    }


def build_market_review(market: str = "auto") -> dict:
    market_name = str(market or "auto").strip().lower() or "auto"
    if market_name == "auto":
        selected_markets = ["cn", "hk", "us"]
    elif market_name in INDEX_GROUPS:
        selected_markets = [market_name]
    else:
        return {
            "market": market_name,
            "context_status": "not_supported",
            "source": "market_review",
            "reason": f"Unsupported market: {market_name}",
            "reviews": {},
            "generated_at": _now_iso(),
        }

    reviews = {item: _build_single_market_review(item) for item in selected_markets}
    statuses = [review["context_status"] for review in reviews.values()]
    if statuses and all(status == "available" for status in statuses):
        context_status = "available"
    elif any(status in {"available", "partial"} for status in statuses):
        context_status = "partial" if any(status != "available" for status in statuses) else "available"
    elif any(status == "fetch_failed" for status in statuses):
        context_status = "fetch_failed"
    else:
        context_status = "missing"

    return {
        "market": market_name,
        "context_status": context_status,
        "source": "market_review",
        "reviews": reviews,
        "generated_at": _now_iso(),
    }
