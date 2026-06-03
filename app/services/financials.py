from app.tools.sec_filings import (
    get_companyfacts,
    get_latest_filing_metadata,
    normalize_us_ticker,
    ticker_to_cik,
)


METRIC_DEFINITIONS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_term_debt": ["ShortTermBorrowings", "ShortTermDebt"],
    "long_term_debt": ["LongTermDebtAndFinanceLeaseObligations", "LongTermDebtNoncurrent"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "shareholders_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}

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


def _score_fact(fact: dict, prefer_instant: bool) -> tuple:
    form_rank = {"10-Q": 4, "10-K": 3, "20-F": 2, "8-K": 1}.get(fact.get("form", ""), 0)
    frame_rank = 1 if fact.get("frame") else 0
    kind_rank = 1 if (prefer_instant and _is_instant_fact(fact)) or (not prefer_instant and _is_duration_fact(fact)) else 0
    return (fact.get("end", ""), fact.get("filed", ""), form_rank, kind_rank, frame_rank)


def _fact_candidates(companyfacts: dict, metric: str) -> list[dict]:
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    candidates: list[dict] = []

    for taxonomy_name in METRIC_DEFINITIONS[metric]:
        taxonomy_fact = us_gaap.get(taxonomy_name, {})
        units = taxonomy_fact.get("units", {})
        for unit, facts in units.items():
            if metric == "eps_diluted" and unit not in {"USD/shares", "USD/shares"}:
                continue
            if metric != "eps_diluted" and unit not in {"USD", "shares"}:
                continue
            for fact in facts:
                if "val" not in fact or fact.get("form") not in {"10-K", "10-Q"}:
                    continue
                candidates.append({**fact, "taxonomy": taxonomy_name, "unit": unit})

    prefer_instant = metric in INSTANT_METRICS
    return sorted(candidates, key=lambda fact: _score_fact(fact, prefer_instant), reverse=True)


def _latest_fact(companyfacts: dict, metric: str) -> dict | None:
    candidates = _fact_candidates(companyfacts, metric)
    return candidates[0] if candidates else None


def _previous_fact(companyfacts: dict, metric: str, current: dict | None) -> dict | None:
    if not current:
        return None

    candidates = [
        fact
        for fact in _fact_candidates(companyfacts, metric)
        if fact.get("end", "") < current.get("end", "")
        and (not current.get("fp") or fact.get("fp") == current.get("fp"))
        and (not current.get("form") or fact.get("form") == current.get("form"))
    ]
    return candidates[0] if candidates else None


def _extract_metric(companyfacts: dict, metric: str) -> dict:
    current = _latest_fact(companyfacts, metric)
    previous = _previous_fact(companyfacts, metric, current)
    current_value = current.get("val") if current else None
    previous_value = previous.get("val") if previous else None
    return {
        "value": current_value,
        "previous_value": previous_value,
        "change_percent": _change(current_value, previous_value),
        "taxonomy": current.get("taxonomy") if current else "",
        "unit": current.get("unit") if current else "",
        "form": current.get("form") if current else "",
        "fy": current.get("fy") if current else None,
        "fp": current.get("fp") if current else "",
        "end": current.get("end") if current else "",
        "filed": current.get("filed") if current else "",
    }


def _metric_value(metrics: dict, key: str) -> float | int | None:
    return metrics.get(key, {}).get("value")


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
    filing_metadata = get_latest_filing_metadata(cik)
    metrics = {metric: _extract_metric(companyfacts, metric) for metric in METRIC_DEFINITIONS}

    revenue = _metric_value(metrics, "revenue")
    gross_profit = _metric_value(metrics, "gross_profit")
    operating_income = _metric_value(metrics, "operating_income")
    net_income = _metric_value(metrics, "net_income")
    operating_cash_flow = _metric_value(metrics, "operating_cash_flow")
    capex = _metric_value(metrics, "capex")
    short_term_debt = _metric_value(metrics, "short_term_debt") or 0
    long_term_debt = _metric_value(metrics, "long_term_debt") or 0
    debt = short_term_debt + long_term_debt if short_term_debt or long_term_debt else None

    revenue_metric = metrics["revenue"]
    fiscal_period = ""
    if revenue_metric.get("fy") and revenue_metric.get("fp"):
        fiscal_period = f"FY{revenue_metric['fy']} {revenue_metric['fp']}"

    profile = {
        "enabled": True,
        "symbol": ticker,
        "cik": cik,
        "company_name": cik_match.get("company_name", ""),
        "source": "sec_companyfacts",
        "fiscal_period": fiscal_period,
        "filing_type": filing_metadata.get("form") or revenue_metric.get("form", ""),
        "filing_url": filing_metadata.get("filing_url", ""),
        "report_date": filing_metadata.get("report_date") or revenue_metric.get("end", ""),
        "filing_date": filing_metadata.get("filing_date") or revenue_metric.get("filed", ""),
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
