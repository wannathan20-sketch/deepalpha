from urllib.parse import quote

import requests


def get_yahoo_chart(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict:
    """Fetch raw chart candles from Yahoo Finance and normalize them for the app.
    从 Yahoo Finance 获取 K 线数据，并标准化为应用内部使用的行情点。
    """
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        return {"symbol": symbol, "points": []}

    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(normalized_symbol)}",
        params={"range": range_, "interval": interval},
        headers={"User-Agent": "DeepAlpha/0.1"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    result = (data.get("chart", {}).get("result") or [{}])[0]
    timestamps = result.get("timestamp") or []
    quote_data = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    meta = result.get("meta") or {}

    points = []
    for index, timestamp in enumerate(timestamps):
        close = (quote_data.get("close") or [None] * len(timestamps))[index]
        if close is None:
            continue

        points.append(
            {
                "time": timestamp,
                "open": (quote_data.get("open") or [None] * len(timestamps))[index],
                "high": (quote_data.get("high") or [None] * len(timestamps))[index],
                "low": (quote_data.get("low") or [None] * len(timestamps))[index],
                "close": close,
                "volume": (quote_data.get("volume") or [None] * len(timestamps))[index],
            }
        )

    return {
        "provider": "yahoo",
        "symbol": normalized_symbol,
        "currency": meta.get("currency", ""),
        "exchange": meta.get("exchangeName", ""),
        "regular_market_price": meta.get("regularMarketPrice"),
        "range": range_,
        "interval": interval,
        "yahoo_chart_url": f"https://finance.yahoo.com/chart/{quote(normalized_symbol)}",
        "points": points,
    }


def get_market_chart(symbol: str, provider: str = "auto", range_: str = "6mo", interval: str = "1d") -> dict:
    """Resolve the best available market data provider.
    按 provider 参数选择可用行情源；auto 模式优先尝试 Yahoo，失败则返回空结果。
    """
    normalized_provider = provider.strip().lower() or "auto"

    if normalized_provider == "yahoo":
        return get_yahoo_chart(symbol, range_, interval)

    yahoo_error = None
    try:
        yahoo_data = get_yahoo_chart(symbol, range_, interval)
    except requests.RequestException as exc:
        yahoo_error = str(exc)
        yahoo_data = {"points": []}

    if yahoo_data.get("points"):
        yahoo_data["provider"] = "yahoo"
        yahoo_data["provider_mode"] = "auto"
        return yahoo_data

    empty_data = {
        "provider": "auto",
        "symbol": symbol,
        "range": range_,
        "interval": interval,
        "points": [],
    }
    if yahoo_error:
        empty_data["error"] = yahoo_error
    return empty_data
