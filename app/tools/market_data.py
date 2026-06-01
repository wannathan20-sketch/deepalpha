import csv
from datetime import datetime
from io import StringIO
from urllib.parse import quote

import requests


STOOQ_SUFFIX_BY_YAHOO_SUFFIX = {
    "AX": "au",
    "DE": "de",
    "HK": "hk",
    "L": "uk",
    "MI": "it",
    "PA": "fr",
    "SS": "cn",
    "SZ": "cn",
    "TO": "ca",
    "T": "jp",
}


def get_yahoo_chart(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict:
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


def _to_stooq_symbol(symbol: str) -> str:
    normalized_symbol = symbol.strip().lower()
    if not normalized_symbol:
        return ""

    if "." not in normalized_symbol:
        return f"{normalized_symbol}.us"

    base_symbol, suffix = normalized_symbol.rsplit(".", 1)
    stooq_suffix = STOOQ_SUFFIX_BY_YAHOO_SUFFIX.get(suffix.upper(), suffix)
    return f"{base_symbol}.{stooq_suffix}"


def get_stooq_chart(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict:
    normalized_symbol = symbol.strip()
    stooq_symbol = _to_stooq_symbol(normalized_symbol)
    if not stooq_symbol:
        return {"provider": "stooq", "symbol": symbol, "points": []}

    response = requests.get(
        "https://stooq.com/q/d/l/",
        params={"s": stooq_symbol, "i": "d"},
        headers={"User-Agent": "DeepAlpha/0.1"},
        timeout=10,
    )
    response.raise_for_status()

    rows = list(csv.DictReader(StringIO(response.text)))
    points = []
    for row in rows[-140:]:
        try:
            close = float(row["Close"])
            points.append(
                {
                    "time": int(datetime.strptime(row["Date"], "%Y-%m-%d").timestamp()),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": close,
                    "volume": int(float(row.get("Volume") or 0)),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "provider": "stooq",
        "symbol": stooq_symbol,
        "source_symbol": normalized_symbol,
        "currency": "",
        "exchange": "Stooq",
        "regular_market_price": points[-1]["close"] if points else None,
        "range": range_,
        "interval": interval,
        "yahoo_chart_url": f"https://stooq.com/q/?s={quote(stooq_symbol)}",
        "points": points,
    }


def get_market_chart(symbol: str, provider: str = "auto", range_: str = "6mo", interval: str = "1d") -> dict:
    normalized_provider = provider.strip().lower() or "auto"

    if normalized_provider == "yahoo":
        return get_yahoo_chart(symbol, range_, interval)
    if normalized_provider == "stooq":
        return get_stooq_chart(symbol, range_, interval)

    yahoo_data = get_yahoo_chart(symbol, range_, interval)
    if yahoo_data.get("points"):
        yahoo_data["provider"] = "yahoo"
        yahoo_data["provider_mode"] = "auto"
        return yahoo_data

    stooq_data = get_stooq_chart(symbol, range_, interval)
    stooq_data["provider_mode"] = "auto"
    return stooq_data
