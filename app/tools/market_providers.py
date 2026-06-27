from __future__ import annotations

import importlib
import importlib.util
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol
from urllib.parse import quote

import requests

from app.tools.market_symbols import MarketSymbol


@dataclass(frozen=True)
class MarketChartRequest:
    symbol: MarketSymbol
    range_: str
    interval: str
    start_date: date
    end_date: date


class MarketDataProvider(Protocol):
    name: str

    def supports(self, market: str) -> bool: ...

    def is_available(self) -> bool: ...

    def fetch_chart(self, request: MarketChartRequest) -> dict: ...


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _formatted_number(value: object) -> float | None:
    if isinstance(value, str):
        value = (
            value.strip()
            .replace("$", "")
            .replace(",", "")
            .replace("%", "")
            .replace("+", "")
        )
    return _number(value)


def _timestamp(value: object) -> int | None:
    if isinstance(value, datetime):
        current = value
    elif isinstance(value, date):
        current = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)):
        raw = float(value)
        return int(raw / 1000 if raw > 10_000_000_000 else raw)
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            current = datetime.fromisoformat(text)
        except ValueError:
            return None
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return int(current.timestamp())


def normalize_points(rows: list[dict]) -> list[dict]:
    deduplicated: dict[int, dict] = {}
    for row in rows:
        timestamp = _timestamp(row.get("time"))
        close = _number(row.get("close"))
        if timestamp is None or close is None:
            continue
        deduplicated[timestamp] = {
            "time": timestamp,
            "open": _number(row.get("open")),
            "high": _number(row.get("high")),
            "low": _number(row.get("low")),
            "close": close,
            "volume": _number(row.get("volume")),
        }
    return [deduplicated[key] for key in sorted(deduplicated)]


def _records(frame: object) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        return []
    records = frame.to_dict("records")
    return records if isinstance(records, list) else []


class _ImportProvider:
    module_name = ""

    def is_available(self) -> bool:
        return importlib.util.find_spec(self.module_name) is not None

    def _module(self):
        return importlib.import_module(self.module_name)


class YahooProvider:
    name = "yahoo"

    def supports(self, market: str) -> bool:
        return market in {"cn", "hk", "us"}

    def is_available(self) -> bool:
        return True

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        symbol = request.symbol.yahoo_symbol
        hosts = [
            host.strip()
            for host in os.getenv(
                "YAHOO_FINANCE_HOSTS",
                "query1.finance.yahoo.com,query2.finance.yahoo.com",
            ).split(",")
            if host.strip()
        ]
        response = None
        last_error = None
        selected_host = ""
        for host in hosts:
            try:
                current = requests.get(
                    f"https://{host}/v8/finance/chart/{quote(symbol)}",
                    params={"range": request.range_, "interval": request.interval},
                    headers={"User-Agent": "DeepAlpha/0.1"},
                    timeout=int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "10")),
                )
                current.raise_for_status()
                response = current
                selected_host = host
                break
            except requests.RequestException as exc:
                last_error = exc
        if response is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("No Yahoo Finance host is configured.")
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [{}])[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for index, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "time": timestamp,
                    "open": (quotes.get("open") or [None] * len(timestamps))[index],
                    "high": (quotes.get("high") or [None] * len(timestamps))[index],
                    "low": (quotes.get("low") or [None] * len(timestamps))[index],
                    "close": (quotes.get("close") or [None] * len(timestamps))[index],
                    "volume": (quotes.get("volume") or [None] * len(timestamps))[index],
                }
            )
        meta = result.get("meta") or {}
        source_url = f"https://finance.yahoo.com/chart/{quote(symbol)}"
        return {
            "symbol": symbol,
            "currency": meta.get("currency", ""),
            "exchange": meta.get("exchangeName", ""),
            "source_url": source_url,
            "yahoo_chart_url": source_url,
            "yahoo_host": selected_host,
            "points": normalize_points(rows),
        }


NASDAQ_REVIEW_SYMBOLS = {
    "^GSPC": {
        "symbol": "SPY",
        "asset_class": "etf",
        "instrument_type": "etf_proxy",
    },
    "^IXIC": {
        "symbol": "COMP",
        "asset_class": "index",
        "instrument_type": "index",
    },
    "^DJI": {
        "symbol": "DIA",
        "asset_class": "etf",
        "instrument_type": "etf_proxy",
    },
}


class NasdaqProvider:
    name = "nasdaq"

    def supports(self, market: str) -> bool:
        return market == "us"

    def is_available(self) -> bool:
        return True

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        original_symbol = request.symbol.yahoo_symbol
        mapping = NASDAQ_REVIEW_SYMBOLS.get(original_symbol)
        if mapping is None:
            return {"symbol": request.symbol.local_symbol, "points": []}

        symbol = mapping["symbol"]
        asset_class = mapping["asset_class"]
        response = requests.get(
            f"https://api.nasdaq.com/api/quote/{quote(symbol)}/chart",
            params={"assetclass": asset_class},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DeepAlpha/0.1)",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "10")),
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        chart = data.get("chart") or []
        latest_close = _formatted_number(data.get("lastSalePrice"))
        previous_close = _formatted_number(data.get("previousClose"))
        if latest_close is not None and previous_close is not None:
            latest_timestamp = (
                _timestamp(chart[-1].get("x")) if chart else None
            ) or int(datetime.now(timezone.utc).timestamp())
            rows = [
                {"time": latest_timestamp - 86_400, "close": previous_close},
                {
                    "time": latest_timestamp,
                    "close": latest_close,
                    "volume": _formatted_number(data.get("volume")),
                },
            ]
        else:
            rows = [
                {"time": item.get("x"), "close": item.get("y")}
                for item in chart
            ]
        result = {
            "symbol": symbol,
            "exchange": "US",
            "instrument_type": mapping["instrument_type"],
            "source_url": (
                f"https://www.nasdaq.com/market-activity/"
                f"{asset_class}/{symbol.lower()}"
            ),
            "points": normalize_points(rows),
        }
        if mapping["instrument_type"] == "etf_proxy":
            result["proxy_symbol"] = symbol
            result["proxy_for"] = original_symbol
        return result


class AkShareProvider(_ImportProvider):
    name = "akshare"
    module_name = "akshare"

    def supports(self, market: str) -> bool:
        return market in {"cn", "hk"}

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        ak = self._module()
        kwargs = {
            "symbol": request.symbol.local_symbol,
            "period": "daily",
            "start_date": request.start_date.strftime("%Y%m%d"),
            "end_date": request.end_date.strftime("%Y%m%d"),
            "adjust": "qfq",
        }
        frame = ak.stock_zh_a_hist(**kwargs) if request.symbol.market == "cn" else ak.stock_hk_hist(**kwargs)
        rows = [
            {
                "time": row.get("日期"),
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "volume": row.get("成交量"),
            }
            for row in _records(frame)
        ]
        return {
            "symbol": request.symbol.local_symbol,
            "exchange": request.symbol.exchange,
            "points": normalize_points(rows),
        }


HK_INDEX_SYMBOLS = {
    "^HSI": "HSI",
    "HSI": "HSI",
    "^HSTECH": "HSTECH",
    "HSTECH": "HSTECH",
}


class AkShareHKIndexProvider(_ImportProvider):
    name = "akshare_hk_index"
    module_name = "akshare"

    def supports(self, market: str) -> bool:
        return market == "hk"

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        ak = self._module()
        symbol = HK_INDEX_SYMBOLS.get(request.symbol.yahoo_symbol) or HK_INDEX_SYMBOLS.get(request.symbol.local_symbol)
        if symbol is None:
            return {"symbol": request.symbol.local_symbol, "points": []}
        frame = ak.stock_hk_index_daily_sina(symbol=symbol)
        rows = [
            {
                "time": row.get("date") or row.get("日期"),
                "open": row.get("open") or row.get("开盘"),
                "high": row.get("high") or row.get("最高"),
                "low": row.get("low") or row.get("最低"),
                "close": row.get("close") or row.get("收盘"),
                "volume": row.get("volume") or row.get("成交量"),
            }
            for row in _records(frame)
        ]
        return {
            "symbol": symbol,
            "exchange": "HK",
            "instrument_type": "index",
            "source_url": f"https://stock.finance.sina.com.cn/hkstock/quotes/{symbol}.html",
            "points": normalize_points(rows),
        }


class EfinanceProvider(_ImportProvider):
    name = "efinance"
    module_name = "efinance"

    def supports(self, market: str) -> bool:
        return market == "cn"

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        ef = self._module()
        frame = ef.stock.get_quote_history(
            request.symbol.local_symbol,
            beg=request.start_date.strftime("%Y%m%d"),
            end=request.end_date.strftime("%Y%m%d"),
            klt=101,
            fqt=1,
        )
        rows = [
            {
                "time": row.get("日期"),
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "volume": row.get("成交量"),
            }
            for row in _records(frame)
        ]
        return {
            "symbol": request.symbol.local_symbol,
            "exchange": request.symbol.exchange,
            "points": normalize_points(rows),
        }


class BaostockProvider(_ImportProvider):
    name = "baostock"
    module_name = "baostock"

    def supports(self, market: str) -> bool:
        return market == "cn"

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        bs = self._module()
        login = bs.login()
        if str(login.error_code) != "0":
            raise RuntimeError("Baostock login failed")
        code = f"{request.symbol.exchange.lower()}.{request.symbol.local_symbol}"
        try:
            result = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,volume",
                start_date=request.start_date.isoformat(),
                end_date=request.end_date.isoformat(),
                frequency="d",
                adjustflag="2",
            )
            if str(result.error_code) != "0":
                raise RuntimeError("Baostock history query failed")
            rows = []
            while result.next():
                values = dict(zip(result.fields, result.get_row_data()))
                rows.append({"time": values.get("date"), **values})
        finally:
            bs.logout()
        return {
            "symbol": code,
            "exchange": request.symbol.exchange,
            "points": normalize_points(rows),
        }


class YFinanceProvider(_ImportProvider):
    """Thin wrapper around `yfinance`, which accesses Yahoo Finance through
    a different internal endpoint than the direct v8/chart API.  It is more
    resilient from cloud IP ranges where the v8 API may be rate-limited.
    封装 yfinance，相比直接调 Yahoo v8 API，yfinance 对云服务器 IP 更宽容，
    可作为美股和港股的可靠兜底。
    The provider silently becomes unavailable when yfinance cannot be imported
    (missing dependency / broken env), so the backend still starts.
    当 yfinance 无法导入时静默标记为不可用，不影响后端启动。
    """
    name = "yfinance"
    module_name = "yfinance"
    _import_ok: bool | None = None

    def supports(self, market: str) -> bool:
        return market in {"us", "hk", "cn"}

    def is_available(self) -> bool:
        if self._import_ok is None:
            try:
                self._module()
                self._import_ok = True
            except Exception:
                self._import_ok = False
        return self._import_ok

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        yf = self._module()
        ticker = yf.Ticker(request.symbol.yahoo_symbol)
        hist = ticker.history(
            period="1y" if request.range_ in {"1y", "2y", "5y", "max"} else "6mo",
        )
        if hist.empty:
            return {"symbol": request.symbol.local_symbol, "points": []}
        rows = []
        for index, row in hist.iterrows():
            rows.append(
                {
                    "time": int(index.timestamp()),
                    "open": _number(row.get("Open")),
                    "high": _number(row.get("High")),
                    "low": _number(row.get("Low")),
                    "close": _number(row.get("Close")),
                    "volume": _number(row.get("Volume")),
                }
            )
        return {
            "symbol": request.symbol.local_symbol,
            "exchange": request.symbol.exchange,
            "source_url": (
                f"https://finance.yahoo.com/quote/"
                f"{request.symbol.yahoo_symbol}/"
            ),
            "points": normalize_points(rows),
        }


class FinnhubProvider:
    name = "finnhub"

    def supports(self, market: str) -> bool:
        return market == "us"

    def is_available(self) -> bool:
        return bool(os.getenv("FINNHUB_API_KEY", "").strip())

    def fetch_chart(self, request: MarketChartRequest) -> dict:
        response = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol": request.symbol.local_symbol,
                "resolution": "D",
                "from": int(
                    datetime.combine(
                        request.start_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ).timestamp()
                ),
                "to": int(
                    datetime.combine(
                        request.end_date,
                        datetime.max.time(),
                        tzinfo=timezone.utc,
                    ).timestamp()
                ),
                "token": os.getenv("FINNHUB_API_KEY", ""),
            },
            timeout=int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "10")),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("s") != "ok":
            return {"symbol": request.symbol.local_symbol, "points": []}
        rows = [
            {
                "time": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for timestamp, open_, high, low, close, volume in zip(
                payload.get("t", []),
                payload.get("o", []),
                payload.get("h", []),
                payload.get("l", []),
                payload.get("c", []),
                payload.get("v", []),
            )
        ]
        return {
            "symbol": request.symbol.local_symbol,
            "exchange": request.symbol.exchange,
            "points": normalize_points(rows),
        }
