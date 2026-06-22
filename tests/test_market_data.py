import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.tools.market_symbols import normalize_market_symbol


@pytest.mark.parametrize(
    ("raw", "exchange", "market", "canonical", "yahoo", "local"),
    [
        ("600519", None, "cn", "SH600519", "600519.SS", "600519"),
        ("SZ000001", None, "cn", "SZ000001", "000001.SZ", "000001"),
        ("920748.BJ", None, "cn", "BJ920748", "920748.BJ", "920748"),
        ("HK00700", None, "hk", "HK00700", "0700.HK", "00700"),
        ("0700.HK", None, "hk", "HK00700", "0700.HK", "00700"),
        ("AAPL", None, "us", "AAPL", "AAPL", "AAPL"),
        ("NASDAQ:AAPL", None, "us", "AAPL", "AAPL", "AAPL"),
        ("00700", "HKEX", "hk", "HK00700", "0700.HK", "00700"),
    ],
)
def test_normalize_market_symbol(
    raw: str,
    exchange: str | None,
    market: str,
    canonical: str,
    yahoo: str,
    local: str,
) -> None:
    result = normalize_market_symbol(raw, exchange)

    assert result.market == market
    assert result.canonical_symbol == canonical
    assert result.yahoo_symbol == yahoo
    assert result.local_symbol == local


def test_normalize_market_symbol_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="Market symbol is required"):
        normalize_market_symbol("   ")
