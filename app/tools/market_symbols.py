from dataclasses import dataclass


CN_EXCHANGE_HINTS = {
    "SH": "SH",
    "SSE": "SH",
    "SHSE": "SH",
    "SZ": "SZ",
    "SZSE": "SZ",
    "BJ": "BJ",
    "BSE": "BJ",
}
HK_EXCHANGE_HINTS = {"HK", "HKEX", "SEHK"}
US_EXCHANGE_HINTS = {"NASDAQ", "NYSE", "AMEX", "OTC", "US"}
HK_INDEX_SYMBOLS = {"^HSI": "HSI", "^HSTECH": "HSTECH"}


@dataclass(frozen=True)
class MarketSymbol:
    original_symbol: str
    market: str
    canonical_symbol: str
    yahoo_symbol: str
    local_symbol: str
    exchange: str


def _infer_cn_exchange(code: str, hint: str = "") -> str:
    mapped = CN_EXCHANGE_HINTS.get(hint.upper())
    if mapped:
        return mapped
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _cn_symbol(original: str, code: str, exchange: str) -> MarketSymbol:
    suffix = {"SH": "SS", "SZ": "SZ", "BJ": "BJ"}[exchange]
    return MarketSymbol(
        original_symbol=original,
        market="cn",
        canonical_symbol=f"{exchange}{code}",
        yahoo_symbol=f"{code}.{suffix}",
        local_symbol=code,
        exchange=exchange,
    )


def _hk_symbol(original: str, digits: str) -> MarketSymbol:
    numeric = str(int(digits))
    return MarketSymbol(
        original_symbol=original,
        market="hk",
        canonical_symbol=f"HK{numeric.zfill(5)}",
        yahoo_symbol=f"{numeric.zfill(4)}.HK",
        local_symbol=numeric.zfill(5),
        exchange="HK",
    )


def _hk_index_symbol(original: str, code: str) -> MarketSymbol:
    local = code.upper().lstrip("^")
    return MarketSymbol(
        original_symbol=original,
        market="hk",
        canonical_symbol=f"HK{local}",
        yahoo_symbol=f"^{local}",
        local_symbol=local,
        exchange="HK",
    )


def _us_symbol(original: str, ticker: str, exchange: str = "US") -> MarketSymbol:
    normalized = ticker.upper()
    return MarketSymbol(
        original_symbol=original,
        market="us",
        canonical_symbol=normalized,
        yahoo_symbol=normalized,
        local_symbol=normalized,
        exchange=exchange or "US",
    )


def normalize_market_symbol(symbol: str, exchange: str | None = None) -> MarketSymbol:
    original = str(symbol or "").strip()
    if not original:
        raise ValueError("Market symbol is required.")

    value = original.upper().replace(" ", "")
    hint = str(exchange or "").strip().upper()

    if ":" in value:
        prefix, value = value.split(":", 1)
        hint = hint or prefix

    if value in HK_INDEX_SYMBOLS:
        return _hk_index_symbol(original, HK_INDEX_SYMBOLS[value])
    if hint in HK_EXCHANGE_HINTS and value in {"HSI", "HSTECH"}:
        return _hk_index_symbol(original, value)
    if value.startswith("HK") and value[2:].isdigit():
        return _hk_symbol(original, value[2:])
    if value.endswith(".HK") and value[:-3].isdigit():
        return _hk_symbol(original, value[:-3])
    if hint in HK_EXCHANGE_HINTS and value.isdigit():
        return _hk_symbol(original, value)

    prefix = ""
    code = value
    if len(value) == 8 and value[:2] in {"SH", "SZ", "BJ"} and value[2:].isdigit():
        prefix, code = value[:2], value[2:]
    elif "." in value:
        base, suffix = value.rsplit(".", 1)
        if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
            code = base
            prefix = "SH" if suffix in {"SH", "SS"} else suffix

    if code.isdigit() and len(code) == 6:
        return _cn_symbol(original, code, _infer_cn_exchange(code, hint or prefix))
    if code.isdigit() and len(code) <= 5:
        return _hk_symbol(original, code)

    us_exchange = hint if hint in US_EXCHANGE_HINTS else "US"
    return _us_symbol(original, code, us_exchange)
