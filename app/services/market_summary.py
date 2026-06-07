from statistics import pstdev

from app.tools.market_data import get_market_chart


def build_market_profile(
    *,
    symbol: str | None = None,
    yahoo_symbol: str | None = None,
    exchange: str | None = None,
    provider: str | None = None,
) -> dict:
    """Summarize six-month price action into features useful for analysts.
    将 6 个月行情压缩为分析 Agent 可使用的趋势、收益率、波动率和均线特征。
    """
    provider_name = provider or "auto"
    resolved_symbol = (yahoo_symbol or symbol or "").strip()
    if ":" in resolved_symbol:
        resolved_symbol = resolved_symbol.split(":", 1)[1]

    if not resolved_symbol:
        return {
            "enabled": False,
            "reason": "No market symbol provided.",
        }

    chart = get_market_chart(resolved_symbol, provider_name, "6mo", "1d")
    points = chart.get("points", [])
    if len(points) < 2:
        return {
            "enabled": False,
            "reason": "Insufficient market data.",
            "symbol": resolved_symbol,
            "provider": chart.get("provider", provider_name),
            "exchange": exchange or chart.get("exchange", ""),
        }

    # Work from closes only so partially missing OHLCV rows do not break the trend summary.
    # 只使用收盘价计算核心摘要，避免部分 OHLCV 字段缺失导致趋势计算失败。
    closes = [point["close"] for point in points if point.get("close") is not None]
    latest = closes[-1]
    first = closes[0]
    period_return = ((latest - first) / first) * 100 if first else 0
    daily_returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1]
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    volatility = pstdev(daily_returns) * (252**0.5) * 100 if len(daily_returns) > 1 else 0
    ma20 = sum(closes[-20:]) / min(len(closes), 20)
    ma60 = sum(closes[-60:]) / min(len(closes), 60)

    trend = "uptrend" if latest >= ma20 >= ma60 else "downtrend" if latest <= ma20 <= ma60 else "mixed"

    return {
        "enabled": True,
        "symbol": symbol,
        "yahoo_symbol": resolved_symbol,
        "provider": chart.get("provider", provider_name),
        "provider_mode": chart.get("provider_mode", provider_name),
        "exchange": exchange or chart.get("exchange", ""),
        "currency": chart.get("currency", ""),
        "points_count": len(points),
        "latest_close": round(latest, 4),
        "period_return_percent": round(period_return, 2),
        "high_6m": round(max(closes), 4),
        "low_6m": round(min(closes), 4),
        "annualized_volatility_percent": round(volatility, 2),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "trend": trend,
        "source_url": chart.get("yahoo_chart_url", ""),
    }
