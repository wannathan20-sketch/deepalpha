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
    StockMaster("2513.HK", "Knowledge Atlas Technology", "HKEX", "CN", "HKD", ("智谱", "智谱AI", "智谱科技", "zhipu", "zhipu ai", "z.ai", "glm", "chatglm", "02513", "2513"), 89),
    StockMaster("9618.HK", "JD.com", "HKEX", "CN", "HKD", ("京东", "京东集团", "jd.com", "jd hk", "9618"), 90),
    StockMaster("JD", "JD.com", "NASDAQ", "CN", "USD", ("京东", "京东集团", "jd.com", "jd us", "京东美股"), 89),
    StockMaster("1024.HK", "Kuaishou Technology", "HKEX", "CN", "HKD", ("快手", "快手科技", "kuaishou", "ks", "1024"), 88),
    StockMaster("9999.HK", "NetEase", "HKEX", "CN", "HKD", ("网易", "netease", "ntes hk", "9999"), 88),
    StockMaster("NTES", "NetEase", "NASDAQ", "CN", "USD", ("网易", "netease", "ntes", "网易美股"), 87),
    StockMaster("9888.HK", "Baidu", "HKEX", "CN", "HKD", ("百度", "baidu", "baidu hk", "9888"), 88),
    StockMaster("1211.HK", "BYD Company", "HKEX", "CN", "HKD", ("比亚迪", "byd", "byd hk", "1211"), 89),
    StockMaster("9868.HK", "XPeng", "HKEX", "CN", "HKD", ("小鹏", "小鹏汽车", "xpeng", "xpev hk", "9868"), 87),
    StockMaster("XPEV", "XPeng", "NYSE", "CN", "USD", ("小鹏", "小鹏汽车", "xpeng", "xpev", "小鹏美股"), 86),
    StockMaster("2015.HK", "Li Auto", "HKEX", "CN", "HKD", ("理想", "理想汽车", "li auto", "li hk", "2015"), 87),
    StockMaster("LI", "Li Auto", "NASDAQ", "CN", "USD", ("理想", "理想汽车", "li auto", "li", "理想美股"), 86),
    StockMaster("002594.SZ", "BYD", "SZSE", "CN", "CNY", ("比亚迪", "byd", "byd company", "002594"), 90),
    StockMaster("600519.SS", "Kweichow Moutai", "SSE", "CN", "CNY", ("贵州茅台", "茅台", "moutai", "kweichow moutai", "600519"), 90),
    StockMaster("300750.SZ", "Contemporary Amperex Technology", "SZSE", "CN", "CNY", ("宁德时代", "catl", "contemporary amperex", "300750"), 90),
    StockMaster("688981.SS", "SMIC", "SSE", "CN", "CNY", ("中芯国际", "smic", "semiconductor manufacturing international", "688981"), 89),
    StockMaster("0981.HK", "SMIC", "HKEX", "CN", "HKD", ("中芯国际", "smic hk", "semiconductor manufacturing international", "981", "0981"), 88),
    StockMaster("601127.SS", "Seres Group", "SSE", "CN", "CNY", ("赛力斯", "seres", "赛力斯集团", "601127"), 88),
    StockMaster("601899.SS", "Zijin Mining", "SSE", "CN", "CNY", ("紫金矿业", "zijin", "zijin mining", "601899"), 87),
    StockMaster("600036.SS", "China Merchants Bank", "SSE", "CN", "CNY", ("招商银行", "招行", "cmb", "china merchants bank", "600036"), 87),
    StockMaster("601318.SS", "Ping An Insurance", "SSE", "CN", "CNY", ("中国平安", "平安", "ping an", "ping an insurance", "601318"), 87),
    StockMaster("2318.HK", "Ping An Insurance", "HKEX", "CN", "HKD", ("中国平安", "平安", "ping an", "ping an hk", "2318"), 86),
    StockMaster("000858.SZ", "Wuliangye", "SZSE", "CN", "CNY", ("五粮液", "wuliangye", "000858"), 86),
    StockMaster("000333.SZ", "Midea Group", "SZSE", "CN", "CNY", ("美的", "美的集团", "midea", "midea group", "000333"), 86),
    StockMaster("002475.SZ", "Luxshare Precision", "SZSE", "CN", "CNY", ("立讯精密", "luxshare", "luxshare precision", "002475"), 86),
    StockMaster("300760.SZ", "Mindray", "SZSE", "CN", "CNY", ("迈瑞医疗", "mindray", "300760"), 86),
    StockMaster("601012.SS", "LONGi Green Energy", "SSE", "CN", "CNY", ("隆基绿能", "隆基股份", "longi", "longi green energy", "601012"), 86),
    StockMaster("002230.SZ", "iFlytek", "SZSE", "CN", "CNY", ("科大讯飞", "iflytek", "002230"), 85),
    StockMaster("000725.SZ", "BOE Technology", "SZSE", "CN", "CNY", ("京东方", "京东方a", "boe", "boe technology", "000725"), 85),
    StockMaster("600276.SS", "Hengrui Medicine", "SSE", "CN", "CNY", ("恒瑞医药", "hengrui", "hengrui medicine", "600276"), 85),
    StockMaster("603259.SS", "WuXi AppTec", "SSE", "CN", "CNY", ("药明康德", "wuxi apptec", "603259"), 85),
    StockMaster("2269.HK", "WuXi Biologics", "HKEX", "CN", "HKD", ("药明生物", "wuxi biologics", "2269"), 85),
    StockMaster("1299.HK", "AIA Group", "HKEX", "HK", "HKD", ("友邦", "友邦保险", "aia", "aia group", "1299"), 85),
    StockMaster("0941.HK", "China Mobile", "HKEX", "CN", "HKD", ("中国移动", "china mobile", "941", "0941"), 85),
    StockMaster("0388.HK", "Hong Kong Exchanges and Clearing", "HKEX", "HK", "HKD", ("港交所", "香港交易所", "hkex", "0388", "388"), 85),
    StockMaster("0883.HK", "CNOOC", "HKEX", "CN", "HKD", ("中国海洋石油", "中海油", "cnooc", "883", "0883"), 85),
    StockMaster("TSLA", "Tesla", "NASDAQ", "US", "USD", ("tesla", "特斯拉", "tesla motors", "tsla"), 88),
    StockMaster("NVDA", "NVIDIA", "NASDAQ", "US", "USD", ("nvidia", "英伟达", "辉达", "nvda"), 88),
    StockMaster("AAPL", "Apple", "NASDAQ", "US", "USD", ("apple", "苹果", "苹果公司", "aapl"), 88),
    StockMaster("MSFT", "Microsoft", "NASDAQ", "US", "USD", ("microsoft", "微软", "msft"), 88),
    StockMaster("AMZN", "Amazon", "NASDAQ", "US", "USD", ("amazon", "亚马逊", "amzn"), 88),
    StockMaster("META", "Meta Platforms", "NASDAQ", "US", "USD", ("meta", "facebook", "脸书", "meta platforms"), 88),
    StockMaster("GOOGL", "Alphabet", "NASDAQ", "US", "USD", ("alphabet", "google", "谷歌", "googl", "goog"), 88),
    StockMaster("MU", "Micron Technology", "NASDAQ", "US", "USD", ("micron", "micron technology", "美光", "美光科技", "mu"), 87),
    StockMaster("AMD", "Advanced Micro Devices", "NASDAQ", "US", "USD", ("amd", "advanced micro devices", "超威半导体"), 87),
    StockMaster("MRVL", "Marvell Technology", "NASDAQ", "US", "USD", ("marvell", "marvell technology", "迈威尔", "美满电子", "mrvl"), 87),
    StockMaster("AVGO", "Broadcom", "NASDAQ", "US", "USD", ("broadcom", "博通", "avgo"), 88),
    StockMaster("PLTR", "Palantir", "NASDAQ", "US", "USD", ("palantir", "palantir technologies", "帕兰提尔", "pltr"), 88),
    StockMaster("ARM", "Arm Holdings", "NASDAQ", "GB", "USD", ("arm", "arm holdings", "安谋", "arm chip"), 87),
    StockMaster("TSM", "Taiwan Semiconductor Manufacturing", "NYSE", "TW", "USD", ("tsmc", "台积电", "taiwan semiconductor", "tsm"), 87),
    StockMaster("SMCI", "Super Micro Computer", "NASDAQ", "US", "USD", ("super micro", "supermicro", "超微电脑", "smci"), 86),
    StockMaster("COIN", "Coinbase", "NASDAQ", "US", "USD", ("coinbase", "coinbase global", "coin"), 86),
    StockMaster("MSTR", "MicroStrategy", "NASDAQ", "US", "USD", ("microstrategy", "strategy", "mstr"), 86),
    StockMaster("HOOD", "Robinhood", "NASDAQ", "US", "USD", ("robinhood", "robinhood markets", "hood"), 85),
    StockMaster("SOFI", "SoFi Technologies", "NASDAQ", "US", "USD", ("sofi", "sofi technologies"), 85),
    StockMaster("NFLX", "Netflix", "NASDAQ", "US", "USD", ("netflix", "奈飞", "nflx"), 86),
    StockMaster("ORCL", "Oracle", "NYSE", "US", "USD", ("oracle", "甲骨文", "orcl"), 86),
    StockMaster("CRM", "Salesforce", "NYSE", "US", "USD", ("salesforce", "赛富时", "crm"), 85),
    StockMaster("JPM", "JPMorgan Chase", "NYSE", "US", "USD", ("jpmorgan", "摩根大通", "jp morgan", "jpm"), 85),
    StockMaster("COST", "Costco", "NASDAQ", "US", "USD", ("costco", "好市多", "cost"), 85),
    StockMaster("LLY", "Eli Lilly", "NYSE", "US", "USD", ("eli lilly", "礼来", "lilly", "lly"), 85),
    StockMaster("NOK", "Nokia Oyj ADR", "NYSE", "FI", "USD", ("nokia", "nokia oyj", "诺基亚", "诺基亚公司", "nok", "nokia adr", "nokia us", "诺基亚美股"), 87),
    StockMaster("NOKIA.HE", "Nokia Oyj", "OMXHEX", "FI", "EUR", ("nokia", "nokia oyj", "诺基亚", "诺基亚公司", "nokia.hel", "nokia.he"), 86),
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
