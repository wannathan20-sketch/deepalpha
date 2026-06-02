import re
from urllib.parse import quote

import requests


EXCHANGE_PREFIX_MAP = {
    "AMS": "EURONEXT",
    "ASX": "ASX",
    "AX": "ASX",
    "BRU": "EURONEXT",
    "BSE": "BSE",
    "CO": "OMXCOP",
    "CPH": "OMXCOP",
    "DE": "XETR",
    "DU": "DUS",
    "FRA": "FWB",
    "F": "FWB",
    "GER": "XETR",
    "HE": "OMXHEX",
    "HKG": "HKEX",
    "HK": "HKEX",
    "HEL": "OMXHEX",
    "JK": "IDX",
    "KQ": "KRX",
    "KLS": "MYX",
    "KL": "MYX",
    "KRX": "KRX",
    "KOS": "KRX",
    "KS": "KRX",
    "L": "LSE",
    "LSE": "LSE",
    "MCE": "BME",
    "MC": "BME",
    "MIL": "MIL",
    "MI": "MIL",
    "MUN": "GETTEX",
    "NCM": "NASDAQ",
    "NGM": "NASDAQ",
    "NMS": "NASDAQ",
    "NSI": "NSE",
    "NS": "NSE",
    "NYQ": "NYSE",
    "NYS": "NYSE",
    "OL": "OSL",
    "OSL": "OSL",
    "PAR": "EURONEXT",
    "PA": "EURONEXT",
    "PNK": "OTC",
    "SA": "BMFBOVESPA",
    "SAO": "BMFBOVESPA",
    "SES": "SGX",
    "SI": "SGX",
    "SG": "SGX",
    "SHH": "SSE",
    "SS": "SSE",
    "SHZ": "SZSE",
    "SZ": "SZSE",
    "SW": "SIX",
    "STO": "OMXSTO",
    "ST": "OMXSTO",
    "T": "TSE",
    "TAI": "TWSE",
    "TO": "TSX",
    "TOR": "TSX",
    "TSE": "TSE",
    "TW": "TWSE",
    "TWO": "TPEX",
    "V": "TSXV",
    "VI": "VIE",
}

LOCAL_SYMBOLS = [
    {
        "company": "Micron Technology",
        "ticker": "NASDAQ:MU",
        "raw_symbol": "MU",
        "exchange": "NMS",
        "aliases": ["micron", "micron technology", "美光", "美光科技", "mu"],
    },
]


def _format_tradingview_symbol(symbol: str, exchange: str = "") -> str:
    clean_symbol = symbol.strip().upper()
    clean_exchange = exchange.strip().upper()

    yahoo_suffix = re.search(r"\.([A-Z]+)$", clean_symbol)
    if yahoo_suffix:
        suffix = yahoo_suffix.group(1)
        base_symbol = clean_symbol[: -len(suffix) - 1]
        prefix = EXCHANGE_PREFIX_MAP.get(suffix, suffix)
        return f"{prefix}:{base_symbol}"

    prefix = EXCHANGE_PREFIX_MAP.get(clean_exchange, clean_exchange)
    if prefix:
        return f"{prefix}:{clean_symbol}"

    return clean_symbol


def _yahoo_chart_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/chart/{quote(symbol)}"


def _local_lookup(query: str) -> dict | None:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return None

    for item in LOCAL_SYMBOLS:
        aliases = [item["company"], item["ticker"], item["raw_symbol"], *item.get("aliases", [])]
        normalized_aliases = [alias.lower() for alias in aliases]
        exact_match = normalized_query in normalized_aliases
        fuzzy_match = any(
            len(normalized_query) > 1 and (normalized_query in alias or alias in normalized_query)
            for alias in normalized_aliases
        )
        if exact_match or fuzzy_match:
            result = {
                "query": query,
                "matched": True,
                "company": item["company"],
                "ticker": item["ticker"],
                "raw_symbol": item["raw_symbol"],
                "exchange": item["exchange"],
                "quote_type": "EQUITY",
                "score": 120 if exact_match else 95,
                "source": "local_symbol_fallback",
                "yahoo_chart_url": _yahoo_chart_url(item["raw_symbol"]),
                "confidence": 0.9 if exact_match else 0.72,
                "needs_confirmation": False,
            }
            result["candidates"] = [dict(result)]
            return result

    return None


def _quote_name(item: dict) -> str:
    return item.get("shortname") or item.get("longname") or item.get("symbol", "")


def _score_quote(item: dict, query: str) -> int:
    normalized_query = query.lower().strip()
    symbol = item.get("symbol", "").lower()
    shortname = item.get("shortname", "").lower()
    longname = item.get("longname", "").lower()
    exchange = item.get("exchange", "").upper()
    quote_type = item.get("quoteType", "")
    searchable_name = f"{shortname} {longname}".strip()

    score = 0
    if symbol == normalized_query:
        score += 90
    if shortname == normalized_query or longname == normalized_query:
        score += 100
    if normalized_query and normalized_query in searchable_name:
        score += 70
    if normalized_query and all(part in searchable_name for part in normalized_query.split()):
        score += 40
    if quote_type == "EQUITY":
        score += 25
    elif quote_type == "ETF":
        score += 10
    elif quote_type == "INDEX":
        score -= 10
    if exchange in {"NYQ", "NYS", "NMS", "NGM", "NCM", "HKG", "HEL", "LSE", "TOR", "SHH", "SHZ"}:
        score += 8

    return score


def _format_quote(item: dict, query: str) -> dict:
    symbol = item.get("symbol", "")
    exchange = item.get("exchange", "")

    return {
        "query": query,
        "matched": True,
        "company": _quote_name(item),
        "ticker": _format_tradingview_symbol(symbol, exchange),
        "raw_symbol": symbol,
        "exchange": exchange,
        "quote_type": item.get("quoteType", ""),
        "score": _score_quote(item, query),
        "source": "yahoo_finance_search",
        "yahoo_chart_url": _yahoo_chart_url(symbol),
    }


def lookup_symbol(query: str) -> dict:
    normalized_query = query.strip()
    if not normalized_query:
        return {"query": query, "matched": False}

    local_match = _local_lookup(normalized_query)
    if local_match:
        return local_match

    response = requests.get(
        f"https://query2.finance.yahoo.com/v1/finance/search?q={quote(normalized_query)}",
        headers={"User-Agent": "DeepAlpha/0.1"},
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()

    quotes = [
        item
        for item in data.get("quotes", [])
        if item.get("symbol") and item.get("quoteType") in {"EQUITY", "ETF", "INDEX"}
    ]
    if not quotes:
        return {"query": query, "matched": False}

    candidates = sorted(
        [_format_quote(item, normalized_query) for item in quotes],
        key=lambda item: item["score"],
        reverse=True,
    )
    best = dict(candidates[0])
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0
    best["confidence"] = min(0.99, max(0.05, best["score"] / 170))
    best["needs_confirmation"] = best["score"] < 95 or best["score"] - second_score < 20
    best["candidates"] = [dict(candidate) for candidate in candidates[:5]]
    return best
