import importlib
import importlib.util
import math
import re
from datetime import datetime, timedelta

from app.tools.sec_filings import (
    get_companyfacts,
    get_latest_filing_metadata,
    normalize_us_ticker,
    ticker_to_cik,
)
from app.tools.market_symbols import MarketSymbol, normalize_market_symbol


METRIC_DEFINITIONS = {
    "revenue": {
        "us-gaap": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
        "ifrs-full": ["Revenue", "RevenueFromContractsWithCustomers"],
    },
    "gross_profit": {
        "us-gaap": ["GrossProfit"],
        "ifrs-full": ["GrossProfit"],
    },
    "operating_income": {
        "us-gaap": ["OperatingIncomeLoss"],
        "ifrs-full": ["ProfitLossFromOperatingActivities"],
    },
    "net_income": {
        "us-gaap": ["NetIncomeLoss", "ProfitLoss"],
        "ifrs-full": ["ProfitLoss", "ProfitLossAttributableToOwnersOfParent"],
    },
    "eps_diluted": {
        "us-gaap": ["EarningsPerShareDiluted"],
        "ifrs-full": ["DilutedEarningsLossPerShare"],
    },
    "operating_cash_flow": {
        "us-gaap": ["NetCashProvidedByUsedInOperatingActivities"],
        "ifrs-full": ["CashFlowsFromUsedInOperatingActivities"],
    },
    "capex": {
        "us-gaap": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "ifrs-full": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"],
    },
    "cash": {
        "us-gaap": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
        "ifrs-full": ["CashAndCashEquivalents"],
    },
    "short_term_debt": {
        "us-gaap": ["ShortTermBorrowings", "ShortTermDebt"],
        "ifrs-full": ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "CurrentBorrowings"],
    },
    "long_term_debt": {
        "us-gaap": ["LongTermDebtAndFinanceLeaseObligations", "LongTermDebtNoncurrent"],
        "ifrs-full": ["LongtermBorrowings", "NoncurrentBorrowings"],
    },
    "total_assets": {
        "us-gaap": ["Assets"],
        "ifrs-full": ["Assets"],
    },
    "total_liabilities": {
        "us-gaap": ["Liabilities"],
        "ifrs-full": ["Liabilities"],
    },
    "shareholders_equity": {
        "us-gaap": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "ifrs-full": ["EquityAttributableToOwnersOfParent", "Equity"],
    },
}
ACCEPTED_FACT_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K"}
MONETARY_UNITS = {"USD", "EUR", "GBP", "CNY", "HKD", "JPY", "CAD", "AUD", "CHF", "SEK", "DKK", "NOK"}
AKSHARE_FINANCIAL_FIELDS = [
    "revenue",
    "net_income",
    "gross_margin_percent",
    "net_margin_percent",
    "roe_percent",
    "debt_to_asset_percent",
    "operating_cash_flow",
]
ANNOUNCEMENT_LOOKBACK_DAYS = 730

# Balance-sheet metrics are point-in-time facts; income/cash-flow metrics are period-duration facts.
# 资产负债表指标是时点数据，利润表/现金流指标是期间数据，筛选逻辑需要区分两类事实。
INSTANT_METRICS = {
    "cash",
    "short_term_debt",
    "long_term_debt",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
}


def _round_number(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    rounded = round(value, digits)
    return int(rounded) if rounded.is_integer() else rounded


def _records(frame: object) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        return []
    records = frame.to_dict("records")
    return records if isinstance(records, list) else []


def _akshare_module():
    if importlib.util.find_spec("akshare") is None:
        raise RuntimeError("AkShare is not installed.")
    return importlib.import_module("akshare")


def _normalize_column_name(value: object) -> str:
    return re.sub(r"[\s_()（）%/\\:：,，.-]+", "", str(value or "")).lower()


def _matching_column(record: dict, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in record:
            return candidate

    normalized = {key: _normalize_column_name(key) for key in record}
    for candidate in candidates:
        clean_candidate = _normalize_column_name(candidate)
        if not clean_candidate:
            continue
        for key, clean_key in normalized.items():
            if clean_key == clean_candidate:
                return key
        for key, clean_key in normalized.items():
            if len(clean_candidate) >= 4 and (clean_candidate in clean_key or clean_key in clean_candidate):
                return key
    return ""


def _column_scale(column: str) -> int:
    if "亿元" in column:
        return 100_000_000
    if "万元" in column:
        return 10_000
    return 1


def _coerce_number(value: object, scale: int = 1) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value or "").strip()
        if text in {"", "-", "--", "—", "nan", "None", "不适用"}:
            return None
        negative = text.startswith("(") and text.endswith(")")
        text = (
            text.strip("()")
            .replace(",", "")
            .replace("，", "")
            .replace("%", "")
            .replace("亿元", "")
            .replace("万元", "")
            .replace("元", "")
        )
        try:
            number = float(text)
        except ValueError:
            return None
        if negative:
            number = -number
    if not math.isfinite(number):
        return None
    return _round_number(number * scale)


def _extract_numeric(record: dict, candidates: list[str]) -> float | int | None:
    column = _matching_column(record, candidates)
    if not column:
        return None
    return _coerce_number(record.get(column), _column_scale(column))


def _extract_text(record: dict, candidates: list[str]) -> str:
    column = _matching_column(record, candidates)
    if not column:
        return ""
    return str(record.get(column) or "").strip()


def _date_text(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text:
        return ""
    text = text.split(" ", 1)[0].replace("/", "-")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _record_date(record: dict) -> str:
    return _date_text(
        _extract_text(
            record,
            [
                "REPORT_DATE",
                "报告日期",
                "报告期",
                "报表日期",
                "截止日期",
                "日期",
                "公告日期",
                "披露日期",
                "NOTICE_DATE",
            ],
        )
    )


def _latest_record(records: list[dict]) -> dict:
    if not records:
        return {}
    return sorted(records, key=lambda record: _record_date(record), reverse=True)[0]


def _safe_akshare_records(function: object, *args, **kwargs) -> tuple[list[dict], str]:
    try:
        return _records(function(*args, **kwargs)), ""
    except Exception as exc:
        return [], type(exc).__name__


def _announcement_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    function = getattr(ak, "stock_individual_notice_report", None)
    if function is None:
        return [], []

    end_date = datetime.now().date()
    begin_date = end_date - timedelta(days=ANNOUNCEMENT_LOOKBACK_DAYS)
    records, error = _safe_akshare_records(
        function,
        symbol.local_symbol,
        symbol="财务报告",
        begin_date=begin_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
    )
    return records, [error] if error else []


def _announcements_from_records(records: list[dict], source: str) -> list[dict]:
    announcements = []
    for record in sorted(records, key=lambda item: _record_date(item), reverse=True)[:5]:
        title = _extract_text(record, ["公告标题", "标题", "title", "NOTICE_TITLE", "ANNOUNCEMENT_TITLE"])
        url = _extract_text(record, ["公告链接", "链接", "url", "URL", "attach_url", "ATTACHMENT_URL"])
        if not title and not url:
            continue
        announcements.append(
            {
                "date": _record_date(record),
                "title": title,
                "url": url,
                "type": _extract_text(record, ["公告类型", "类型", "notice_type", "ANNOUNCEMENT_TYPE"]),
                "source": source,
            }
        )
    return announcements


def _akshare_summary(profile: dict) -> list[str]:
    if not profile.get("enabled"):
        return [profile.get("reason", "财报数据暂不可用。")]

    summary = []
    revenue = profile.get("revenue")
    net_income = profile.get("net_income")
    gross_margin = profile.get("gross_margin_percent")
    net_margin = profile.get("net_margin_percent")
    roe = profile.get("roe_percent")
    debt_to_asset = profile.get("debt_to_asset_percent")
    ocf = profile.get("operating_cash_flow")

    if revenue is not None:
        summary.append(f"最新披露收入为 {revenue:,}。")
    if net_income is not None:
        summary.append(f"净利润为 {net_income:,}。")
    if gross_margin is not None or net_margin is not None:
        summary.append(f"毛利率 {gross_margin if gross_margin is not None else '待补充'}%，净利率 {net_margin if net_margin is not None else '待补充'}%。")
    if roe is not None or debt_to_asset is not None:
        summary.append(f"ROE {roe if roe is not None else '待补充'}%，资产负债率 {debt_to_asset if debt_to_asset is not None else '待补充'}%。")
    if ocf is not None:
        summary.append(f"经营现金流为 {ocf:,}。")
    if profile.get("announcements"):
        summary.append(f"已获取 {len(profile['announcements'])} 条财报/公告链接。")
    return summary or ["财报来源已返回，但结构化字段仍需进一步映射。"]


def _pct(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return _round_number((numerator / denominator) * 100)


def _change(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None
    return _round_number(((current - previous) / abs(previous)) * 100)


def _is_duration_fact(fact: dict) -> bool:
    return bool(fact.get("start")) and bool(fact.get("end"))


def _is_instant_fact(fact: dict) -> bool:
    return not fact.get("start") and bool(fact.get("end"))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _days_between(left: str | None, right: str | None) -> int | None:
    left_date = _parse_date(left)
    right_date = _parse_date(right)
    if not left_date or not right_date:
        return None
    return abs((left_date - right_date).days)


def _score_fact(fact: dict, prefer_instant: bool, anchor_end: str | None = None) -> tuple:
    """Rank SEC facts by recency, filing quality, period type, and filing date.
    按时效、报表类型、事实类型与披露日期对 SEC fact 候选项排序。
    """
    form_rank = {"10-Q": 5, "10-K": 4, "20-F": 4, "40-F": 4, "6-K": 2, "8-K": 1}.get(fact.get("form", ""), 0)
    frame_rank = 1 if fact.get("frame") else 0
    kind_rank = 1 if (prefer_instant and _is_instant_fact(fact)) or (not prefer_instant and _is_duration_fact(fact)) else 0
    distance = _days_between(fact.get("end"), anchor_end)
    proximity_rank = -distance if distance is not None else -999999
    return (proximity_rank, fact.get("end", ""), fact.get("filed", ""), form_rank, kind_rank, frame_rank)


def _fact_candidates(companyfacts: dict, metric: str, anchor_end: str | None = None) -> list[dict]:
    """Collect normalized metric candidates across US GAAP and IFRS taxonomies.
    跨 US GAAP 与 IFRS 分类收集同一指标的候选 fact，并统一为内部结构。
    """
    facts_by_taxonomy = companyfacts.get("facts", {})
    candidates: list[dict] = []

    for taxonomy_namespace, taxonomy_names in METRIC_DEFINITIONS[metric].items():
        taxonomy = facts_by_taxonomy.get(taxonomy_namespace, {})
        for taxonomy_name in taxonomy_names:
            taxonomy_fact = taxonomy.get(taxonomy_name, {})
            units = taxonomy_fact.get("units", {})
            for unit, facts in units.items():
                if metric == "eps_diluted" and not unit.endswith("/shares"):
                    continue
                if metric != "eps_diluted" and unit not in MONETARY_UNITS:
                    continue
                for fact in facts:
                    if "val" not in fact or fact.get("form") not in ACCEPTED_FACT_FORMS:
                        continue
                    candidates.append({**fact, "taxonomy": taxonomy_name, "taxonomy_namespace": taxonomy_namespace, "unit": unit})

    # SEC datasets may store capex as an outflow; normalize it to a positive spend value.
    # SEC 数据中资本开支可能以现金流出负数呈现，这里统一转换为正的支出金额。
    if metric == "capex":
        for fact in candidates:
            if fact.get("val", 0) < 0:
                fact["val"] = abs(fact["val"])

    prefer_instant = metric in INSTANT_METRICS
    if prefer_instant and anchor_end:
        # Keep balance-sheet facts near the income-statement anchor so ratios compare the same reporting period.
        # 资产负债表指标需贴近利润表锚点，避免把不同报告期的数据混在一起计算。
        anchored_candidates = []
        for fact in candidates:
            if fact.get("end", "") > anchor_end:
                continue
            distance = _days_between(fact.get("end"), anchor_end)
            if distance is None or distance > 120:
                continue
            anchored_candidates.append(fact)
        candidates = anchored_candidates

    return sorted(candidates, key=lambda fact: _score_fact(fact, prefer_instant, anchor_end), reverse=True)


def _latest_fact(companyfacts: dict, metric: str, anchor_end: str | None = None) -> dict | None:
    candidates = _fact_candidates(companyfacts, metric, anchor_end)
    return candidates[0] if candidates else None


def _previous_fact(companyfacts: dict, metric: str, current: dict | None, anchor_end: str | None = None) -> dict | None:
    if not current:
        return None

    candidates = [
        fact
        for fact in _fact_candidates(companyfacts, metric, anchor_end=None)
        if fact.get("end", "") < current.get("end", "")
        and (not current.get("fp") or fact.get("fp") == current.get("fp"))
        and (not current.get("form") or fact.get("form") == current.get("form"))
    ]
    return candidates[0] if candidates else None


def _extract_metric(companyfacts: dict, metric: str, anchor_end: str | None = None) -> dict:
    current = _latest_fact(companyfacts, metric, anchor_end)
    previous = _previous_fact(companyfacts, metric, current, anchor_end)
    current_value = current.get("val") if current else None
    previous_value = previous.get("val") if previous else None
    return {
        "value": current_value,
        "previous_value": previous_value,
        "change_percent": _change(current_value, previous_value),
        "taxonomy": current.get("taxonomy") if current else "",
        "taxonomy_namespace": current.get("taxonomy_namespace") if current else "",
        "unit": current.get("unit") if current else "",
        "form": current.get("form") if current else "",
        "fy": current.get("fy") if current else None,
        "fp": current.get("fp") if current else "",
        "end": current.get("end") if current else "",
        "filed": current.get("filed") if current else "",
        "stale": False,
    }


def _metric_value(metrics: dict, key: str) -> float | int | None:
    return metrics.get(key, {}).get("value")


def _profile_currency(metrics: dict) -> str:
    for key in ("revenue", "cash", "total_assets"):
        unit = metrics.get(key, {}).get("unit", "")
        if unit and not unit.endswith("/shares"):
            return unit
    return ""


def _build_summary(profile: dict) -> list[str]:
    if not profile.get("enabled"):
        return [profile.get("reason", "SEC 财报数据暂不可用。")]

    summary = []
    revenue = profile.get("revenue")
    net_income = profile.get("net_income")
    gross_margin = profile.get("gross_margin_percent")
    operating_margin = profile.get("operating_margin_percent")
    ocf = profile.get("operating_cash_flow")
    cash = profile.get("cash")
    debt = profile.get("debt")

    if revenue is not None:
        line = f"最新披露收入为 {revenue:,}"
        if profile.get("revenue_change_percent") is not None:
            line += f"，可比期变化 {profile['revenue_change_percent']}%"
        summary.append(line + "。")
    if gross_margin is not None or operating_margin is not None:
        summary.append(f"毛利率 {gross_margin if gross_margin is not None else '待补充'}%，营业利润率 {operating_margin if operating_margin is not None else '待补充'}%。")
    if net_income is not None:
        summary.append(f"净利润为 {net_income:,}。")
    if ocf is not None:
        summary.append(f"经营现金流为 {ocf:,}。")
    if cash is not None or debt is not None:
        summary.append(f"现金 {cash if cash is not None else '待补充'}，总债务 {debt if debt is not None else '待补充'}。")

    return summary or [f"{profile.get('source', '财报来源')} 已返回，但核心字段仍需进一步映射。"]


AKSHARE_FIELD_CANDIDATES = {
    "revenue": [
        "TOTAL_OPERATE_INCOME",
        "OPERATE_INCOME",
        "营业总收入",
        "营业收入",
        "主营业务收入",
        "主营业务收入(万元)",
        "收入",
        "营业额",
        "Revenue",
    ],
    "gross_profit": ["GROSS_PROFIT", "毛利润", "毛利", "Gross Profit"],
    "net_income": [
        "PARENT_NETPROFIT",
        "NETPROFIT",
        "归属于母公司股东的净利润",
        "归属母公司股东的净利润",
        "归母净利润",
        "净利润",
        "净利润(万元)",
        "Net Profit",
    ],
    "gross_margin_percent": ["GROSS_PROFIT_RATIO", "销售毛利率", "销售毛利率(%)", "毛利率", "Gross Margin"],
    "net_margin_percent": ["NETPROFIT_MARGIN", "销售净利率", "销售净利率(%)", "净利率", "Net Margin"],
    "roe_percent": ["ROE_WEIGHT", "ROE", "加权净资产收益率", "净资产收益率", "净资产收益率(%)"],
    "debt_to_asset_percent": ["DEBT_ASSET_RATIO", "资产负债率", "资产负债率(%)"],
    "operating_cash_flow": [
        "NETCASH_OPERATE",
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "经营现金流量净额",
        "经营现金净流量",
        "经营现金净流量(万元)",
        "Operating Cash Flow",
    ],
    "total_assets": ["TOTAL_ASSETS", "资产总计", "总资产", "Total Assets"],
    "total_liabilities": ["TOTAL_LIABILITIES", "负债合计", "总负债", "Total Liabilities"],
}


def _akshare_values_from_record(record: dict, cash_flow_record: dict | None = None) -> dict:
    cash_flow_record = cash_flow_record or {}
    values = {
        key: _extract_numeric(record, candidates)
        for key, candidates in AKSHARE_FIELD_CANDIDATES.items()
    }
    if values["operating_cash_flow"] is None and cash_flow_record:
        values["operating_cash_flow"] = _extract_numeric(cash_flow_record, AKSHARE_FIELD_CANDIDATES["operating_cash_flow"])
    if values["total_assets"] and values["total_liabilities"] and values["debt_to_asset_percent"] is None:
        values["debt_to_asset_percent"] = _pct(values["total_liabilities"], values["total_assets"])
    if values["revenue"] and values["gross_margin_percent"] is not None and values["gross_profit"] is None:
        values["gross_profit"] = _round_number(values["revenue"] * values["gross_margin_percent"] / 100)
    return values


def _akshare_profile_from_values(
    *,
    symbol: MarketSymbol,
    source: str,
    currency: str,
    report_date: str,
    values: dict,
    announcements: list[dict],
    errors: list[str],
) -> dict:
    missing_fields = [field for field in AKSHARE_FINANCIAL_FIELDS if values.get(field) is None]
    has_metric = any(value is not None for value in values.values())
    if not has_metric and not announcements:
        status = "fetch_failed" if errors else "missing"
        reason = errors[0] if errors else "No AkShare financial or announcement records returned."
        return {
            "enabled": False,
            "context_status": status,
            "market": symbol.market,
            "symbol": symbol.canonical_symbol,
            "source": source,
            "reason": reason,
            "summary": [reason],
        }

    status = "partial" if missing_fields or not has_metric else "available"
    profile = {
        "enabled": True,
        "context_status": status,
        "market": symbol.market,
        "symbol": symbol.canonical_symbol,
        "source": source,
        "currency": currency,
        "fiscal_period": report_date,
        "filing_type": "财务报告",
        "filing_url": announcements[0]["url"] if announcements else "",
        "report_date": report_date,
        "filing_date": announcements[0]["date"] if announcements else "",
        "revenue": values.get("revenue"),
        "gross_profit": values.get("gross_profit"),
        "gross_margin_percent": values.get("gross_margin_percent"),
        "operating_income": None,
        "operating_margin_percent": None,
        "net_income": values.get("net_income"),
        "net_margin_percent": values.get("net_margin_percent"),
        "eps_diluted": None,
        "operating_cash_flow": values.get("operating_cash_flow"),
        "capex": None,
        "free_cash_flow": None,
        "cash": None,
        "debt": None,
        "total_assets": values.get("total_assets"),
        "total_liabilities": values.get("total_liabilities"),
        "shareholders_equity": None,
        "roe_percent": values.get("roe_percent"),
        "debt_to_asset_percent": values.get("debt_to_asset_percent"),
        "missing_fields": missing_fields,
        "announcements": announcements,
        "metrics": {
            key: {"value": value, "source": source, "report_date": report_date}
            for key, value in values.items()
        },
    }
    warnings = [f"AkShare call failed: {error}" for error in errors if error]
    if missing_fields:
        warnings.append(f"Missing structured fields: {', '.join(missing_fields)}")
    if warnings:
        profile["warnings"] = warnings
    profile["summary"] = _akshare_summary(profile)
    return profile


def _fetch_cn_financial_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    errors = []
    function = getattr(ak, "stock_financial_analysis_indicator_em", None)
    if function is not None:
        records, error = _safe_akshare_records(function, f"{symbol.local_symbol}.{symbol.exchange}", indicator="按报告期")
        if records:
            return records, errors
        if error:
            errors.append(error)

    function = getattr(ak, "stock_financial_analysis_indicator", None)
    if function is not None:
        records, error = _safe_akshare_records(function, symbol.local_symbol, start_year=str(datetime.now().year - 5))
        if records:
            return records, errors
        if error:
            errors.append(error)
    return [], errors


def _fetch_cn_cash_flow_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    function = getattr(ak, "stock_cash_flow_sheet_by_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, symbol.canonical_symbol)
    return records, [error] if error else []


def _build_cn_financial_profile(symbol: MarketSymbol) -> dict:
    source = "akshare_cn"
    try:
        ak = _akshare_module()
    except Exception as exc:
        reason = type(exc).__name__
        return {
            "enabled": False,
            "context_status": "fetch_failed",
            "market": "cn",
            "symbol": symbol.canonical_symbol,
            "source": source,
            "reason": reason,
            "summary": [str(exc)],
        }

    records, errors = _fetch_cn_financial_records(ak, symbol)
    latest = _latest_record(records)
    cash_records, cash_errors = _fetch_cn_cash_flow_records(ak, symbol)
    announcements_records, announcement_errors = _announcement_records(ak, symbol)
    errors.extend(cash_errors)
    errors.extend(announcement_errors)
    values = _akshare_values_from_record(latest, _latest_record(cash_records)) if latest else {}
    return _akshare_profile_from_values(
        symbol=symbol,
        source=source,
        currency="CNY",
        report_date=_record_date(latest),
        values=values,
        announcements=_announcements_from_records(announcements_records, source),
        errors=errors,
    )


def _fetch_hk_financial_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    function = getattr(ak, "stock_financial_hk_analysis_indicator_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, symbol.local_symbol, indicator="年度")
    return records, [error] if error else []


def _fetch_hk_cash_flow_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    function = getattr(ak, "stock_financial_hk_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, stock=symbol.local_symbol, symbol="现金流量表", indicator="年度")
    return records, [error] if error else []


def _build_hk_financial_profile(symbol: MarketSymbol) -> dict:
    source = "akshare_hk"
    try:
        ak = _akshare_module()
    except Exception as exc:
        reason = type(exc).__name__
        return {
            "enabled": False,
            "context_status": "fetch_failed",
            "market": "hk",
            "symbol": symbol.canonical_symbol,
            "source": source,
            "reason": reason,
            "summary": [str(exc)],
        }

    records, errors = _fetch_hk_financial_records(ak, symbol)
    cash_records, cash_errors = _fetch_hk_cash_flow_records(ak, symbol)
    announcements_records, announcement_errors = _announcement_records(ak, symbol)
    errors.extend(cash_errors)
    errors.extend(announcement_errors)
    latest = _latest_record(records)
    values = _akshare_values_from_record(latest, _latest_record(cash_records)) if latest else {}
    return _akshare_profile_from_values(
        symbol=symbol,
        source=source,
        currency="HKD",
        report_date=_record_date(latest),
        values=values,
        announcements=_announcements_from_records(announcements_records, source),
        errors=errors,
    )


def _build_sec_financial_profile(symbol: str | None, exchange: str | None = None) -> dict:
    """Build a compact financial profile from SEC Companyfacts.
    基于 SEC Companyfacts 构建前端和 Agent 可直接使用的财务画像。
    """
    ticker = normalize_us_ticker(symbol, exchange)
    if not ticker:
        has_symbol = bool(str(symbol or "").strip())
        return {
            "enabled": False,
            "context_status": "not_supported" if has_symbol else "missing",
            "symbol": symbol,
            "source": "sec_companyfacts",
            "reason": (
                "Financial profile currently supports US SEC tickers plus A-share/HK AkShare symbols."
                if has_symbol
                else "No financial symbol provided."
            ),
            "summary": [
                "当前财报画像支持美股 SEC companyfacts，以及 A 股/港股 AkShare 可用财务与公告接口。"
                if has_symbol
                else "未提供可用于财报查询的股票代码。"
            ],
        }

    cik_match = ticker_to_cik(ticker)
    if not cik_match.get("matched"):
        return {
            "enabled": False,
            "context_status": "missing",
            "symbol": ticker,
            "source": "sec_companyfacts",
            "reason": cik_match.get("reason", "Ticker CIK lookup failed."),
            "summary": [cik_match.get("reason", "Ticker CIK lookup failed.")],
        }

    cik = cik_match["cik"]
    companyfacts = get_companyfacts(cik)
    revenue_metric = _extract_metric(companyfacts, "revenue")
    try:
        filing_metadata = get_latest_filing_metadata(cik)
    except Exception as exc:
        filing_metadata = {
            "form": revenue_metric.get("form", ""),
            "report_date": revenue_metric.get("end", ""),
            "filing_date": revenue_metric.get("filed", ""),
            "filing_url": "",
            "metadata_error": str(exc),
        }
    # Revenue usually gives the best period anchor; other metrics are selected around the same report date.
    # 收入通常是最稳定的期间锚点，其他指标围绕同一报告日期选取以保持口径一致。
    anchor_end = filing_metadata.get("report_date") or revenue_metric.get("end", "")
    metrics = {
        metric: revenue_metric if metric == "revenue" else _extract_metric(companyfacts, metric, anchor_end)
        for metric in METRIC_DEFINITIONS
    }

    revenue = _metric_value(metrics, "revenue")
    gross_profit = _metric_value(metrics, "gross_profit")
    operating_income = _metric_value(metrics, "operating_income")
    net_income = _metric_value(metrics, "net_income")
    operating_cash_flow = _metric_value(metrics, "operating_cash_flow")
    capex = _metric_value(metrics, "capex")
    short_term_debt = _metric_value(metrics, "short_term_debt") or 0
    long_term_debt = _metric_value(metrics, "long_term_debt") or 0
    debt = short_term_debt + long_term_debt if short_term_debt or long_term_debt else None

    fiscal_period = ""
    if revenue_metric.get("fy") and revenue_metric.get("fp"):
        fiscal_period = f"FY{revenue_metric['fy']} {revenue_metric['fp']}"

    profile = {
        "enabled": True,
        "context_status": "partial" if filing_metadata.get("metadata_error") else "available",
        "symbol": ticker,
        "cik": cik,
        "company_name": cik_match.get("company_name", ""),
        "source": "sec_companyfacts",
        "currency": _profile_currency(metrics),
        "fiscal_period": fiscal_period,
        "filing_type": filing_metadata.get("form") or revenue_metric.get("form", ""),
        "filing_url": filing_metadata.get("filing_url", ""),
        "report_date": filing_metadata.get("report_date") or revenue_metric.get("end", ""),
        "filing_date": filing_metadata.get("filing_date") or revenue_metric.get("filed", ""),
        "metadata_error": filing_metadata.get("metadata_error", ""),
        "revenue": revenue,
        "gross_profit": gross_profit,
        "gross_margin_percent": _pct(gross_profit, revenue),
        "operating_income": operating_income,
        "operating_margin_percent": _pct(operating_income, revenue),
        "net_income": net_income,
        "net_margin_percent": _pct(net_income, revenue),
        "eps_diluted": _metric_value(metrics, "eps_diluted"),
        "operating_cash_flow": operating_cash_flow,
        "capex": capex,
        "free_cash_flow": operating_cash_flow - capex if operating_cash_flow is not None and capex is not None else None,
        "cash": _metric_value(metrics, "cash"),
        "debt": debt,
        "total_assets": _metric_value(metrics, "total_assets"),
        "total_liabilities": _metric_value(metrics, "total_liabilities"),
        "shareholders_equity": _metric_value(metrics, "shareholders_equity"),
        "revenue_change_percent": metrics["revenue"]["change_percent"],
        "net_income_change_percent": metrics["net_income"]["change_percent"],
        "operating_cash_flow_change_percent": metrics["operating_cash_flow"]["change_percent"],
        "metrics": metrics,
    }
    profile["summary"] = _build_summary(profile)
    return profile


def build_financial_profile(symbol: str | None, exchange: str | None = None) -> dict:
    has_symbol = bool(str(symbol or "").strip())
    if not has_symbol:
        return _build_sec_financial_profile(symbol, exchange)

    try:
        market_symbol = normalize_market_symbol(symbol or "", exchange)
    except ValueError:
        return _build_sec_financial_profile(symbol, exchange)

    if market_symbol.market == "cn":
        return _build_cn_financial_profile(market_symbol)
    if market_symbol.market == "hk":
        return _build_hk_financial_profile(market_symbol)
    return _build_sec_financial_profile(symbol, exchange)
