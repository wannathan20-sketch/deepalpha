from datetime import datetime

from app.tools.sec_filings import (
    get_companyfacts,
    get_latest_filing_metadata,
    normalize_us_ticker,
    ticker_to_cik,
)


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
    form_rank = {"10-Q": 5, "10-K": 4, "20-F": 4, "40-F": 4, "6-K": 2, "8-K": 1}.get(fact.get("form", ""), 0)
    frame_rank = 1 if fact.get("frame") else 0
    kind_rank = 1 if (prefer_instant and _is_instant_fact(fact)) or (not prefer_instant and _is_duration_fact(fact)) else 0
    distance = _days_between(fact.get("end"), anchor_end)
    proximity_rank = -distance if distance is not None else -999999
    return (proximity_rank, fact.get("end", ""), fact.get("filed", ""), form_rank, kind_rank, frame_rank)


def _fact_candidates(companyfacts: dict, metric: str, anchor_end: str | None = None) -> list[dict]:
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

    if metric == "capex":
        for fact in candidates:
            if fact.get("val", 0) < 0:
                fact["val"] = abs(fact["val"])

    prefer_instant = metric in INSTANT_METRICS
    if prefer_instant and anchor_end:
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

    return summary or ["SEC companyfacts 已返回，但核心字段仍需进一步映射。"]


def build_financial_profile(symbol: str | None, exchange: str | None = None) -> dict:
    ticker = normalize_us_ticker(symbol, exchange)
    if not ticker:
        return {
            "enabled": False,
            "symbol": symbol,
            "source": "sec_companyfacts",
            "reason": "SEC companyfacts MVP currently supports US-listed tickers only.",
            "summary": ["当前仅支持美股 SEC companyfacts，港股/A 股需后续接 HKEX/交易所数据源。"],
        }

    cik_match = ticker_to_cik(ticker)
    if not cik_match.get("matched"):
        return {
            "enabled": False,
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
