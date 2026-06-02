import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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


@dataclass(frozen=True)
class StockMaster:
    symbol: str
    name: str
    exchange: str
    country: str
    currency: str
    aliases: tuple[str, ...]
    priority: int
    is_active: bool = True


STOCK_MASTER: tuple[StockMaster, ...] = (
    StockMaster("3690.HK", "Meituan", "HKEX", "CN", "HKD", ("美团", "美团点评", "meituan", "meituan dianping", "mt", "3690"), 100),
    StockMaster("9988.HK", "Alibaba Group", "HKEX", "CN", "HKD", ("阿里", "阿里巴巴", "alibaba", "baba hk", "alibaba hk", "9988"), 96),
    StockMaster("BABA", "Alibaba Group", "NYSE", "CN", "USD", ("阿里", "阿里巴巴", "alibaba", "baba", "alibaba us", "阿里美股"), 94),
    StockMaster("0700.HK", "Tencent Holdings", "HKEX", "CN", "HKD", ("腾讯", "腾讯控股", "tencent", "tcehy", "700", "0700"), 95),
    StockMaster("1810.HK", "Xiaomi Corporation", "HKEX", "CN", "HKD", ("小米", "小米集团", "xiaomi", "xiaomi group", "xiacy", "1810"), 93),
    StockMaster("BIDU", "Baidu", "NASDAQ", "CN", "USD", ("百度", "baidu", "bidu"), 90),
    StockMaster("PDD", "PDD Holdings", "NASDAQ", "CN", "USD", ("拼多多", "pinduoduo", "pdd", "temu"), 90),
    StockMaster("002594.SZ", "BYD", "SZSE", "CN", "CNY", ("比亚迪", "byd", "byd company", "002594"), 90),
    StockMaster("600519.SS", "Kweichow Moutai", "SSE", "CN", "CNY", ("贵州茅台", "茅台", "moutai", "kweichow moutai", "600519"), 90),
    StockMaster("300750.SZ", "Contemporary Amperex Technology", "SZSE", "CN", "CNY", ("宁德时代", "catl", "contemporary amperex", "300750"), 90),
    StockMaster("TSLA", "Tesla", "NASDAQ", "US", "USD", ("tesla", "特斯拉", "tesla motors", "tsla"), 88),
    StockMaster("NVDA", "NVIDIA", "NASDAQ", "US", "USD", ("nvidia", "英伟达", "辉达", "nvda"), 88),
    StockMaster("AAPL", "Apple", "NASDAQ", "US", "USD", ("apple", "苹果", "苹果公司", "aapl"), 88),
    StockMaster("MSFT", "Microsoft", "NASDAQ", "US", "USD", ("microsoft", "微软", "msft"), 88),
    StockMaster("AMZN", "Amazon", "NASDAQ", "US", "USD", ("amazon", "亚马逊", "amzn"), 88),
    StockMaster("META", "Meta Platforms", "NASDAQ", "US", "USD", ("meta", "facebook", "脸书", "meta platforms"), 88),
    StockMaster("GOOGL", "Alphabet", "NASDAQ", "US", "USD", ("alphabet", "google", "谷歌", "googl", "goog"), 88),
    StockMaster("MU", "Micron Technology", "NASDAQ", "US", "USD", ("micron", "micron technology", "美光", "美光科技", "mu"), 87),
    StockMaster("AMD", "Advanced Micro Devices", "NASDAQ", "US", "USD", ("amd", "advanced micro devices", "超威半导体"), 87),
    StockMaster("MCD", "McDonald's", "NYSE", "US", "USD", ("mcdonald's", "mcdonalds", "麦当劳", "mcd"), 86),
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _symbol_key(value: str) -> str:
    return value.strip().upper().replace(":", ".").lstrip("0")


def _market_from_symbol(symbol: str, exchange: str) -> str:
    suffix = symbol.rsplit(".", 1)[1].upper() if "." in symbol else ""
    if suffix == "HK" or exchange == "HKEX":
        return "HK"
    if suffix in {"SS", "SZ"} or exchange in {"SSE", "SZSE"}:
        return "CN"
    return "US" if exchange in {"NASDAQ", "NYSE", "AMEX", "OTC"} else exchange


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


def _stock_match(stock: StockMaster, query: str, confidence: float, source: str, score: int) -> dict:
    market = _market_from_symbol(stock.symbol, stock.exchange)
    ticker = _format_tradingview_symbol(stock.symbol, stock.exchange)
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "exchange": stock.exchange,
        "market": market,
        "country": stock.country,
        "currency": stock.currency,
        "confidence": confidence,
        "source": source,
        "query": query,
        "company": stock.name,
        "ticker": ticker,
        "raw_symbol": stock.symbol,
        "quote_type": "EQUITY",
        "score": score + stock.priority,
        "yahoo_chart_url": _yahoo_chart_url(stock.symbol),
    }


def _alias_index() -> dict[str, list[StockMaster]]:
    index: dict[str, list[StockMaster]] = {}
    for stock in STOCK_MASTER:
        if not stock.is_active:
            continue
        for alias in stock.aliases:
            index.setdefault(_normalize(alias), []).append(stock)
    for stocks in index.values():
        stocks.sort(key=lambda item: item.priority, reverse=True)
    return index


ALIAS_MAP = _alias_index()


def _dedupe_matches(matches: list[dict]) -> list[dict]:
    by_symbol: dict[str, dict] = {}
    for match in matches:
        existing = by_symbol.get(match["symbol"])
        if not existing or (match["confidence"], match["score"]) > (existing["confidence"], existing["score"]):
            by_symbol[match["symbol"]] = match
    return sorted(by_symbol.values(), key=lambda item: (item["confidence"], item["score"]), reverse=True)


def _local_matches(query: str) -> list[dict]:
    normalized_query = _normalize(query)
    query_symbol = _symbol_key(query)
    if not normalized_query:
        return []

    symbol_matches = [
        _stock_match(stock, query, 0.99, "exact_symbol", 500)
        for stock in STOCK_MASTER
        if stock.is_active and query_symbol in {_symbol_key(stock.symbol), _symbol_key(stock.symbol.split(".", 1)[0])}
    ]
    if symbol_matches:
        return _dedupe_matches(symbol_matches)

    name_matches = [
        _stock_match(stock, query, 0.97, "exact_name", 400)
        for stock in STOCK_MASTER
        if stock.is_active and _normalize(stock.name) == normalized_query
    ]
    if name_matches:
        return _dedupe_matches(name_matches)

    alias_matches = [
        _stock_match(stock, query, 0.95, "alias", 300)
        for stock in ALIAS_MAP.get(normalized_query, [])
    ]
    if alias_matches:
        return _dedupe_matches(alias_matches)

    fuzzy_matches: list[dict] = []
    for stock in STOCK_MASTER:
        if not stock.is_active:
            continue
        names = [stock.name, *stock.aliases]
        best_ratio = max(SequenceMatcher(None, normalized_query, _normalize(name)).ratio() for name in names)
        contains = any(
            len(normalized_query) > 1
            and (normalized_query in _normalize(name) or _normalize(name) in normalized_query)
            for name in names
        )
        if contains or best_ratio >= 0.72:
            confidence = 0.82 if contains else min(0.8, 0.45 + best_ratio * 0.4)
            fuzzy_matches.append(_stock_match(stock, query, confidence, "fuzzy_name", int(200 * best_ratio)))

    return _dedupe_matches(fuzzy_matches)[:5]


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
    score = _score_quote(item, query)
    exchange_name = EXCHANGE_PREFIX_MAP.get(exchange.upper(), exchange.upper())
    return {
        "symbol": symbol,
        "name": _quote_name(item),
        "exchange": exchange_name,
        "market": _market_from_symbol(symbol, exchange_name),
        "confidence": min(0.78, max(0.2, score / 170)),
        "source": "external_provider",
        "query": query,
        "company": _quote_name(item),
        "ticker": _format_tradingview_symbol(symbol, exchange),
        "raw_symbol": symbol,
        "quote_type": item.get("quoteType", ""),
        "score": score,
        "yahoo_chart_url": _yahoo_chart_url(symbol),
    }


def _external_matches(query: str) -> list[dict]:
    response = requests.get(
        f"https://query2.finance.yahoo.com/v1/finance/search?q={quote(query)}",
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
    return sorted([_format_quote(item, query) for item in quotes], key=lambda item: item["score"], reverse=True)[:5]


def _response(query: str, matches: list[dict], error: str | None = None) -> dict:
    clean_matches = _dedupe_matches(matches)[:5]
    best = clean_matches[0] if clean_matches else None
    result = {
        "query": query,
        "matched": bool(best and best["confidence"] >= 0.7),
        "matches": clean_matches,
        "candidates": clean_matches,
        "needs_confirmation": len(clean_matches) != 1 or (best is not None and best["confidence"] < 0.9),
    }
    if best:
        result.update(best)
    if error:
        result["error"] = error
    return result


def lookup_symbol(query: str) -> dict:
    normalized_query = query.strip()
    if not normalized_query:
        return _response(query, [])

    local = _local_matches(normalized_query)
    if local and local[0]["confidence"] >= 0.8:
        return _response(query, local)

    try:
        external = _external_matches(normalized_query)
    except Exception as exc:
        return _response(query, local, str(exc))

    return _response(query, [*local, *external])
