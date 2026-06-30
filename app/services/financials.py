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
    "gross_profit",
    "net_income",
    "gross_margin_percent",
    "net_margin_percent",
    "roe_percent",
    "debt_to_asset_percent",
    "operating_cash_flow",
    "operating_income",
    "operating_margin_percent",
    "eps_diluted",
    "cash",
    "debt",
    "short_term_debt",
    "long_term_debt",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
]
ANNOUNCEMENT_TYPES = [
    "财务报告",
    "重大事项",
    "资产重组",
    "持股变动",
    "融资公告",
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
    """Fetch announcements across multiple types for a given stock."""
    function = getattr(ak, "stock_individual_notice_report", None)
    if function is None:
        return [], []

    end_date = datetime.now().date()
    begin_date = end_date - timedelta(days=ANNOUNCEMENT_LOOKBACK_DAYS)
    all_records: list[dict] = []
    all_errors: list[str] = []

    for ann_type in ANNOUNCEMENT_TYPES:
        records, error = _safe_akshare_records(
            function,
            symbol.local_symbol,
            symbol=ann_type,
            begin_date=begin_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if records:
            for record in records:
                record["_fetch_type"] = ann_type
            all_records.extend(records)
        if error:
            all_errors.append(f"{ann_type}:{error}")

    # Deduplicate by URL or title when records appear in multiple type queries
    seen: set[str] = set()
    deduped: list[dict] = []
    for record in all_records:
        key = str(record.get("网址") or record.get("公告链接") or record.get("url") or record.get("公告标题", ""))
        if key and key not in seen:
            seen.add(key)
            deduped.append(record)
        elif not key:
            deduped.append(record)

    return deduped, all_errors


def _classify_announcement_type(title: str, raw_type: str, fetch_type: str) -> str:
    """Classify announcement into standardized category based on title keywords and fetch type."""
    title_lower = title.lower()
    type_keywords = [
        ("performance_forecast", ["业绩预告", "业绩快报", "业绩预", "盈利预", "利润预"]),
        ("material_contract", ["重大合同", "合同签订", "合同公告", "中标", "框架协议"]),
        ("shareholder_meeting", ["股东大会", "临时股东", "年度股东", "股东周年大会"]),
        ("capital_change", ["股本变动", "股份变动", "回购", "增持", "减持", "股权变更", "注册资本"]),
        ("related_party", ["关联交易", "关联方", "关联人"]),
        ("dividend", ["分红", "派息", "权益分派", "利润分配", "股息"]),
        ("financial_report", ["财务报告", "年报", "半年报", "季报", "年度报告", "中期报告", "季度报告", "业绩公告", "annual report", "interim report"]),
        ("asset_restructuring", ["资产重组", "重大资产重组", "并购", "收购", "重组"]),
        ("financing", ["融资", "增发", "配股", "可转债", "债券", "非公开发行", "IPO"]),
        ("risk_warning", ["风险提示", "退市风险", "ST", "特别处理", "立案调查", "行政处罚"]),
        ("info_change", ["变更", "换届", "辞职", "聘任", "章程"]),
    ]
    for classified, keywords in type_keywords:
        for kw in keywords:
            if kw in title_lower:
                return classified
    fetch_map = {
        "财务报告": "financial_report",
        "重大事项": "material_event",
        "资产重组": "asset_restructuring",
        "持股变动": "capital_change",
        "融资公告": "financing",
    }
    return fetch_map.get(fetch_type, "other")


def _announcements_from_records(records: list[dict], source: str) -> list[dict]:
    announcements = []
    for record in sorted(records, key=lambda item: _record_date(item), reverse=True):
        title = _extract_text(record, ["公告标题", "标题", "title", "NOTICE_TITLE", "ANNOUNCEMENT_TITLE"])
        url = _extract_text(record, ["公告链接", "链接", "url", "URL", "attach_url", "ATTACHMENT_URL"])
        if not title and not url:
            continue
        raw_type = _extract_text(record, ["公告类型", "类型", "notice_type", "ANNOUNCEMENT_TYPE"])
        fetch_type = str(record.get("_fetch_type", ""))
        announcements.append(
            {
                "date": _record_date(record),
                "title": title,
                "url": url,
                "type": raw_type,
                "classified_type": _classify_announcement_type(title, raw_type, fetch_type),
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
    operating_income = profile.get("operating_income")
    operating_margin = profile.get("operating_margin_percent")
    roe = profile.get("roe_percent")
    debt_to_asset = profile.get("debt_to_asset_percent")
    ocf = profile.get("operating_cash_flow")
    eps = profile.get("eps_diluted")
    cash = profile.get("cash")
    debt = profile.get("debt")
    equity = profile.get("shareholders_equity")

    if revenue is not None:
        line = f"最新披露收入为 {revenue:,}"
        if profile.get("revenue_change_percent") is not None:
            line += f"，可比期变化 {profile['revenue_change_percent']}%"
        summary.append(line + "。")
    if net_income is not None:
        line = f"净利润为 {net_income:,}"
        if profile.get("net_income_change_percent") is not None:
            line += f"，可比期变化 {profile['net_income_change_percent']}%"
        summary.append(line + "。")
    if gross_margin is not None or net_margin is not None:
        summary.append(f"毛利率 {gross_margin if gross_margin is not None else '待补充'}%，净利率 {net_margin if net_margin is not None else '待补充'}%。")
    if operating_income is not None or operating_margin is not None:
        summary.append(f"营业利润 {operating_income if operating_income is not None else '待补充'}，营业利润率 {operating_margin if operating_margin is not None else '待补充'}%。")
    if eps is not None:
        summary.append(f"每股收益（稀释）为 {eps}。")
    if roe is not None or debt_to_asset is not None:
        summary.append(f"ROE {roe if roe is not None else '待补充'}%，资产负债率 {debt_to_asset if debt_to_asset is not None else '待补充'}%。")
    if ocf is not None:
        line = f"经营现金流为 {ocf:,}"
        if profile.get("operating_cash_flow_change_percent") is not None:
            line += f"，可比期变化 {profile['operating_cash_flow_change_percent']}%"
        summary.append(line + "。")
    if cash is not None or debt is not None or equity is not None:
        parts = []
        if cash is not None:
            parts.append(f"现金 {cash:,}")
        if debt is not None:
            parts.append(f"总债务 {debt:,}")
        if equity is not None:
            parts.append(f"股东权益 {equity:,}")
        summary.append("；".join(parts) + "。")
    if profile.get("announcements"):
        summary.append(f"已获取 {len(profile['announcements'])} 条财报/公告链接。")
    seg = profile.get("segment_data", {})
    if seg.get("enabled"):
        parts = []
        for key, label in [("by_product", "产品"), ("by_industry", "行业"), ("by_region", "地区")]:
            count = len(seg.get(key, []))
            if count:
                parts.append(f"{label}{count}项")
        if parts:
            summary.append(f"分业务数据已获取（{' / '.join(parts)}），报告期 {seg.get('report_date', '')}。")
    eg = profile.get("earnings_guidance", {})
    if eg.get("enabled"):
        pa = len(eg.get("pre_announcements", []))
        er = len(eg.get("express_reports", []))
        if pa or er:
            parts2 = []
            if pa:
                parts2.append(f"业绩预告{pa}条")
            if er:
                parts2.append(f"业绩快报{er}条")
            summary.append(f"管理层正式业绩指引已获取（{'，'.join(parts2)}）。")
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
    "eps_diluted": [
        "DILUTED_EPS",
        "DILUTEDEPS",
        "稀释每股收益",
        "稀释每股收益(元)",
        "基本每股收益",
        "每股收益",
    ],
    "operating_income": [
        "OPERATE_PROFIT",
        "OPERATING_PROFIT",
        "营业利润",
        "营业利润(万元)",
    ],
    "cash": [
        "MONETARYFUNDS",
        "货币资金",
        "货币资金(万元)",
        "现金及现金等价物",
    ],
    "short_term_debt": [
        "SHORT_LOAN",
        "短期借款",
        "短期借款(万元)",
    ],
    "long_term_debt": [
        "LONG_LOAN",
        "长期借款",
        "长期借款(万元)",
    ],
    "shareholders_equity": [
        "TOTAL_EQUITY",
        "TOTAL_PARENT_EQUITY",
        "股东权益合计",
        "归属于母公司股东权益合计",
        "归属于母公司所有者权益合计",
        "所有者权益合计",
    ],
}


def _akshare_values_from_record(
    record: dict,
    cash_flow_record: dict | None = None,
    balance_sheet_record: dict | None = None,
    profit_sheet_record: dict | None = None,
) -> dict:
    cash_flow_record = cash_flow_record or {}
    balance_sheet_record = balance_sheet_record or {}
    profit_sheet_record = profit_sheet_record or {}

    values = {
        key: _extract_numeric(record, candidates)
        for key, candidates in AKSHARE_FIELD_CANDIDATES.items()
    }

    # Cash flow fallback
    if values["operating_cash_flow"] is None and cash_flow_record:
        values["operating_cash_flow"] = _extract_numeric(cash_flow_record, AKSHARE_FIELD_CANDIDATES["operating_cash_flow"])

    # Balance sheet fallback — cash, debt, equity
    if values["cash"] is None and balance_sheet_record:
        values["cash"] = _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["cash"])
    if values["shareholders_equity"] is None and balance_sheet_record:
        values["shareholders_equity"] = _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["shareholders_equity"])
    if values["total_assets"] is None and balance_sheet_record:
        values["total_assets"] = _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["total_assets"])
    if values["total_liabilities"] is None and balance_sheet_record:
        values["total_liabilities"] = _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["total_liabilities"])
    short_term = (
        _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["short_term_debt"])
        if values["short_term_debt"] is None else values["short_term_debt"]
    )
    long_term = (
        _extract_numeric(balance_sheet_record, AKSHARE_FIELD_CANDIDATES["long_term_debt"])
        if values["long_term_debt"] is None else values["long_term_debt"]
    )
    values["short_term_debt"] = short_term
    values["long_term_debt"] = long_term
    if short_term is not None or long_term is not None:
        values["debt"] = (short_term or 0) + (long_term or 0)

    # Profit sheet fallback — EPS, operating income
    if values["eps_diluted"] is None and profit_sheet_record:
        values["eps_diluted"] = _extract_numeric(profit_sheet_record, AKSHARE_FIELD_CANDIDATES["eps_diluted"])
    if values["operating_income"] is None and profit_sheet_record:
        values["operating_income"] = _extract_numeric(profit_sheet_record, AKSHARE_FIELD_CANDIDATES["operating_income"])

    # Computed fields
    if values["total_assets"] and values["total_liabilities"] and values["debt_to_asset_percent"] is None:
        values["debt_to_asset_percent"] = _pct(values["total_liabilities"], values["total_assets"])
    if values["revenue"] and values["gross_margin_percent"] is not None and values["gross_profit"] is None:
        values["gross_profit"] = _round_number(values["revenue"] * values["gross_margin_percent"] / 100)
    if values["revenue"] and values["operating_income"] is not None:
        values["operating_margin_percent"] = _pct(values["operating_income"], values["revenue"])
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
    prev_values: dict | None = None,
    management_guidance: dict | None = None,
    segment_data: dict | None = None,
    earnings_guidance: dict | None = None,
    dividends: list[dict] | None = None,
    capital_flow_context: dict | None = None,
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
    # Build announcement summary grouped by classified type
    ann_summary: dict[str, list[dict]] = {}
    for ann in announcements:
        ct = ann.get("classified_type", "other")
        ann_summary.setdefault(ct, []).append(ann)

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
        "operating_income": values.get("operating_income"),
        "operating_margin_percent": values.get("operating_margin_percent"),
        "net_income": values.get("net_income"),
        "net_margin_percent": values.get("net_margin_percent"),
        "eps_diluted": values.get("eps_diluted"),
        "operating_cash_flow": values.get("operating_cash_flow"),
        "capex": None,
        "free_cash_flow": None,
        "cash": values.get("cash"),
        "debt": values.get("debt"),
        "short_term_debt": values.get("short_term_debt"),
        "long_term_debt": values.get("long_term_debt"),
        "total_assets": values.get("total_assets"),
        "total_liabilities": values.get("total_liabilities"),
        "shareholders_equity": values.get("shareholders_equity"),
        "roe_percent": values.get("roe_percent"),
        "debt_to_asset_percent": values.get("debt_to_asset_percent"),
        "revenue_change_percent": _change(values.get("revenue"), (prev_values or {}).get("revenue")),
        "net_income_change_percent": _change(values.get("net_income"), (prev_values or {}).get("net_income")),
        "operating_cash_flow_change_percent": _change(values.get("operating_cash_flow"), (prev_values or {}).get("operating_cash_flow")),
        "missing_fields": missing_fields,
        "announcements": announcements,
        "announcement_summary": ann_summary,
        "management_guidance": management_guidance or {"enabled": False, "source": "", "warnings": []},
        "segment_data": segment_data or {"enabled": False, "source": "", "warnings": []},
        "earnings_guidance": earnings_guidance or {"enabled": False, "source": "", "warnings": []},
        "dividends": dividends or [],
        "capital_flow_context": capital_flow_context or {"enabled": False, "warnings": []},
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


def _fetch_cn_balance_sheet_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    """Fetch A-share balance sheet from Eastmoney via AkShare."""
    function = getattr(ak, "stock_balance_sheet_by_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, symbol.canonical_symbol)
    return records, [error] if error else []


def _fetch_cn_profit_sheet_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    """Fetch A-share income statement from Eastmoney via AkShare."""
    function = getattr(ak, "stock_profit_sheet_by_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, symbol.canonical_symbol)
    return records, [error] if error else []


def _previous_period_record(records: list[dict], latest: dict) -> dict:
    """Find the comparable prior-period record for YoY comparison.

    Returns the most recent record with a date before the latest record.
    """
    if not records or not latest:
        return {}
    latest_date = _record_date(latest)
    if not latest_date:
        return {}
    sorted_records = sorted(records, key=lambda r: _record_date(r), reverse=True)
    for record in sorted_records:
        if _record_date(record) < latest_date:
            return record
    return {}


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
    balance_records, balance_errors = _fetch_cn_balance_sheet_records(ak, symbol)
    profit_records, profit_errors = _fetch_cn_profit_sheet_records(ak, symbol)
    announcements_records, announcement_errors = _announcement_records(ak, symbol)
    errors.extend(cash_errors)
    errors.extend(balance_errors)
    errors.extend(profit_errors)
    errors.extend(announcement_errors)

    prev_record = _previous_period_record(records, latest)
    values = (
        _akshare_values_from_record(
            latest,
            _latest_record(cash_records),
            _latest_record(balance_records),
            _latest_record(profit_records),
        )
        if latest else {}
    )
    prev_values = _akshare_values_from_record(prev_record) if prev_record else {}

    # Optional: profit forecast, segment data, official guidance, capital flow
    mgmt_guidance = _fetch_cn_profit_forecast(ak, symbol)
    segment_data = _fetch_cn_segment_data(ak, symbol)
    earnings_guidance = _fetch_cn_official_guidance(ak, symbol)
    capital_flow = _fetch_capital_flow_context(ak)

    return _akshare_profile_from_values(
        symbol=symbol,
        source=source,
        currency="CNY",
        report_date=_record_date(latest),
        values=values,
        announcements=_announcements_from_records(announcements_records, source),
        errors=errors,
        prev_values=prev_values,
        management_guidance=mgmt_guidance,
        segment_data=segment_data,
        earnings_guidance=earnings_guidance,
        capital_flow_context=capital_flow,
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


def _fetch_hk_balance_sheet_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    """Fetch HK balance sheet from Eastmoney via AkShare.

    Returns row-oriented records with STD_ITEM_NAME / AMOUNT columns.
    """
    function = getattr(ak, "stock_financial_hk_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, stock=symbol.local_symbol, symbol="资产负债表", indicator="年度")
    return records, [error] if error else []


def _fetch_hk_profit_sheet_records(ak: object, symbol: MarketSymbol) -> tuple[list[dict], list[str]]:
    """Fetch HK income statement from Eastmoney via AkShare.

    Returns row-oriented records with STD_ITEM_NAME / AMOUNT columns.
    """
    function = getattr(ak, "stock_financial_hk_report_em", None)
    if function is None:
        return [], []
    records, error = _safe_akshare_records(function, stock=symbol.local_symbol, symbol="利润表", indicator="年度")
    return records, [error] if error else []


# Map HK Chinese line item names to internal field names for pivot.
_HK_ITEM_MAP = {
    "现金及现金等价物": "cash",
    "现金及約當現金": "cash",
    "货币资金": "cash",
    "短期借款": "short_term_debt",
    "长期借款": "long_term_debt",
    "資產總額": "total_assets",
    "资产总额": "total_assets",
    "总资产": "total_assets",
    "負債總額": "total_liabilities",
    "负债总额": "total_liabilities",
    "总负债": "total_liabilities",
    "本公司权益持有人应占权益": "shareholders_equity",
    "本公司權益持有人應佔權益": "shareholders_equity",
    "股东权益": "shareholders_equity",
    "權益總額": "shareholders_equity",
    "权益总额": "shareholders_equity",
    "營業利潤": "operating_income",
    "营业利润": "operating_income",
    "營業收入": "revenue",
    "营业收入": "revenue",
    "营业额": "revenue",
    "營業額": "revenue",
    "净利润": "net_income",
    "淨利潤": "net_income",
    "歸屬於母公司股東的淨利潤": "net_income",
    "归属于母公司股东的净利润": "net_income",
    "經營活動產生的現金流量淨額": "operating_cash_flow",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "基本每股收益": "eps_diluted",
    "稀釋每股收益": "eps_diluted",
    "稀释每股收益": "eps_diluted",
}


def _pivot_hk_row_records(records: list[dict]) -> list[dict]:
    """Pivot HK row-oriented financial records to column-oriented per report date.

    HK report functions return one row per line item (STD_ITEM_NAME + AMOUNT).
    This pivots them to one row per report period with line items as columns.
    """
    if not records:
        return []

    # Determine which column holds the item name
    item_col = _matching_column(records[0], ["STD_ITEM_NAME", "项目名称", "ITEM_NAME", "报表项目"])
    amount_col = _matching_column(records[0], ["AMOUNT", "金额", "VALUE"])

    pivoted: dict[str, dict] = {}
    for record in records:
        date = _record_date(record)
        if not date:
            continue
        if date not in pivoted:
            pivoted[date] = {"REPORT_DATE": date}

        item_name = str(record.get(item_col, "") or "").strip()
        amount = _coerce_number(record.get(amount_col))
        if not item_name or amount is None:
            continue

        # Match item name to internal field
        mapped_key = _HK_ITEM_MAP.get(item_name)
        if mapped_key is None:
            # Fuzzy match: check if any known name is contained in the item name
            for hk_name, key in _HK_ITEM_MAP.items():
                if hk_name in item_name or item_name in hk_name:
                    mapped_key = key
                    break
        if mapped_key:
            pivoted[date][mapped_key] = (pivoted[date].get(mapped_key, 0) or 0) + amount

    return list(pivoted.values())


def _fetch_cn_profit_forecast(ak: object, symbol: MarketSymbol) -> dict:
    """Fetch CN analyst profit forecast consensus from Eastmoney."""
    guidance: dict = {
        "enabled": False,
        "source": "",
        "analyst_consensus": {},
        "eps_forecast_range": {},
        "warnings": [],
    }
    fn = getattr(ak, "stock_profit_forecast_em", None)
    if fn is None:
        guidance["warnings"].append("stock_profit_forecast_em not available")
        return guidance
    try:
        df = fn(symbol=symbol.local_symbol)
        if hasattr(df, "empty") and df.empty:
            guidance["warnings"].append("No CN profit forecast data")
            return guidance
        row = df.iloc[0] if not getattr(df, "empty", True) else None
        if row is None:
            guidance["warnings"].append("No CN profit forecast rows")
            return guidance
        guidance["enabled"] = True
        guidance["source"] = "akshare_profit_forecast_em"
        guidance["analyst_consensus"] = {
            "eps_current_year": _coerce_number(row.get("2026预测每股收益")),
            "eps_next_year": _coerce_number(row.get("2027预测每股收益")),
            "buy_count": int(row.get("机构投资评级(近六个月)-买入", 0) or 0),
            "hold_count": (int(row.get("机构投资评级(近六个月)-增持", 0) or 0) + int(row.get("机构投资评级(近六个月)-中性", 0) or 0)),
            "sell_count": (int(row.get("机构投资评级(近六个月)-减持", 0) or 0) + int(row.get("机构投资评级(近六个月)-卖出", 0) or 0)),
            "total_analysts": int(row.get("研报数", 0) or 0),
        }
    except Exception as exc:
        guidance["warnings"].append(f"CN profit forecast failed: {type(exc).__name__}")
    return guidance


def _fetch_cn_segment_data(ak: object, symbol: MarketSymbol) -> dict:
    """Fetch CN segment revenue breakdown by product / industry / region from Eastmoney.
    从东方财富获取 A 股主营业务构成（按产品、行业、地区分类）。
    """
    segment: dict = {
        "enabled": False,
        "source": "",
        "report_date": "",
        "by_product": [],
        "by_industry": [],
        "by_region": [],
        "warnings": [],
    }
    fn = getattr(ak, "stock_zygc_em", None)
    if fn is None:
        segment["warnings"].append("stock_zygc_em not available")
        return segment
    try:
        df = fn(symbol=f"{symbol.local_symbol}.{symbol.exchange}")
        if hasattr(df, "empty") and df.empty:
            segment["warnings"].append("No segment data returned")
            return segment
        latest_date = str(df["报告日期"].max())
        latest_df = df[df["报告日期"].astype(str) == latest_date]
        segment["enabled"] = True
        segment["source"] = "akshare_stock_zygc_em"
        segment["report_date"] = latest_date
        category_map = {"按产品分类": "by_product", "按行业分类": "by_industry", "按地区分类": "by_region"}
        for _, row in latest_df.iterrows():
            cat = str(row.get("分类类型", ""))
            key = category_map.get(cat)
            if key is None:
                continue
            segment[key].append({
                "segment": str(row.get("主营构成", "")),
                "revenue": _coerce_number(row.get("主营收入")),
                "revenue_pct": round((_coerce_number(row.get("收入比例")) or 0) * 100, 2),
                "cost": _coerce_number(row.get("主营成本")),
                "cost_pct": round((_coerce_number(row.get("成本比例")) or 0) * 100, 2),
                "profit": _coerce_number(row.get("主营利润")),
                "profit_pct": round((_coerce_number(row.get("利润比例")) or 0) * 100, 2),
                "gross_margin": round((_coerce_number(row.get("毛利率")) or 0) * 100, 2),
            })
    except Exception as exc:
        segment["warnings"].append(f"Segment data failed: {type(exc).__name__}")
    return segment


def _fetch_cn_official_guidance(ak: object, symbol: MarketSymbol) -> dict:
    """Fetch official management earnings guidance from pre-announcements and express reports.
    从东方财富获取管理层正式业绩指引（业绩预告 + 业绩快报）。
    """
    import calendar
    from datetime import date

    guidance: dict = {
        "enabled": False,
        "source": "",
        "pre_announcements": [],
        "express_reports": [],
        "warnings": [],
    }

    # Build quarter-end lookback dates (AkShare yjyg/yjkb endpoints expect quarter-end)
    today = date.today()
    lookback_dates: list[str] = []
    # Start from current quarter, walk back up to 4 quarters
    quarter_end_month = ((today.month - 1) // 3 + 1) * 3
    year = today.year
    if quarter_end_month > 12:
        quarter_end_month = 3
        year += 1
    for _ in range(5):  # try up to 5 quarters back
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        qe = date(year, quarter_end_month, min(last_day, 31))
        if qe <= today:
            date_str = qe.strftime("%Y%m%d")
            if date_str not in lookback_dates:
                lookback_dates.append(date_str)
        # Move back one quarter
        quarter_end_month -= 3
        if quarter_end_month < 1:
            quarter_end_month = 12
            year -= 1

    # Part A: Earnings pre-announcements (业绩预告)
    fn_yjyg = getattr(ak, "stock_yjyg_em", None)
    if fn_yjyg is not None:
        for date_str in lookback_dates:
            try:
                df = fn_yjyg(date=date_str)
            except Exception:
                continue  # this date may not have data yet, try the next one
            if hasattr(df, "empty") and df.empty:
                continue
            stock_df = df[df["股票代码"].astype(str).str.strip() == symbol.local_symbol.strip()]
            if stock_df.empty:
                continue
            for _, row in stock_df.iterrows():
                guidance["pre_announcements"].append({
                    "report_date": str(row.get("公告日期", "")),
                    "indicator": str(row.get("预测指标", "")),
                    "change_description": str(row.get("业绩变动", "")),
                    "forecast_value": _coerce_number(row.get("预测数值")),
                    "change_range": _coerce_number(row.get("业绩变动幅度")),
                    "change_reason": str(row.get("业绩变动原因", "")),
                    "forecast_type": str(row.get("预告类型", "")),
                    "prior_year_value": _coerce_number(row.get("上年同期值")),
                })
            break  # Found data, stop trying older dates
    else:
        guidance["warnings"].append("stock_yjyg_em not available")

    # Part B: Express reports (业绩快报)
    fn_yjkb = getattr(ak, "stock_yjkb_em", None)
    if fn_yjkb is not None:
        for date_str in lookback_dates:
            try:
                df = fn_yjkb(date=date_str)
            except Exception:
                continue  # this date may not have data yet, try the next one
            if hasattr(df, "empty") and df.empty:
                continue
            stock_df = df[df["股票代码"].astype(str).str.strip() == symbol.local_symbol.strip()]
            if stock_df.empty:
                continue
            for _, row in stock_df.iterrows():
                guidance["express_reports"].append({
                    "report_date": str(row.get("公告日期", "")),
                    "indicator": str(row.get("预测指标", "")),
                    "change_description": str(row.get("业绩变动", "")),
                    "forecast_value": _coerce_number(row.get("预测数值")),
                    "change_range": _coerce_number(row.get("业绩变动幅度")),
                    "change_reason": str(row.get("业绩变动原因", "")),
                    "forecast_type": str(row.get("预告类型", "")),
                    "prior_year_value": _coerce_number(row.get("上年同期值")),
                })
            break
    else:
        guidance["warnings"].append("stock_yjkb_em not available")

    if guidance["pre_announcements"] or guidance["express_reports"]:
        guidance["enabled"] = True
        guidance["source"] = "akshare_stock_yjyg_em + akshare_stock_yjkb_em"

    return guidance


def _fetch_hk_profit_forecast(ak: object, symbol: MarketSymbol) -> dict:
    """Fetch HK profit forecast from ETNET."""
    fn = getattr(ak, "stock_hk_profit_forecast_et", None)
    if fn is None:
        return {"enabled": False, "source": "", "analyst_consensus": {}, "warnings": ["stock_hk_profit_forecast_et not available"]}
    try:
        df = fn(symbol=symbol.local_symbol, indicator="盈利预测概览")
        if hasattr(df, "empty") and df.empty:
            return {"enabled": False, "source": "akshare_hk_profit_forecast_et", "analyst_consensus": {}, "warnings": ["No HK profit forecast data"]}
        broker_estimates: list[dict] = []
        for _, row in df.iterrows():
            broker_estimates.append({
                "fiscal_year": str(row.get("财政年度", "")),
                "profit": _coerce_number(row.get("纯利/亏损")),
                "eps": _coerce_number(row.get("每股盈利")),
                "dps": _coerce_number(row.get("每股派息")),
                "broker": str(row.get("证券商", "")),
                "rating": str(row.get("评级", "")),
                "target_price": _coerce_number(row.get("目标价")),
                "updated": str(row.get("更新日期", "")),
            })
        return {
            "enabled": True,
            "source": "akshare_hk_profit_forecast_et",
            "analyst_consensus": {},
            "broker_estimates": broker_estimates,
            "warnings": [],
        }
    except Exception as exc:
        return {"enabled": False, "source": "akshare_hk_profit_forecast_et", "analyst_consensus": {}, "warnings": [type(exc).__name__]}


def _fetch_hk_dividends(ak: object, symbol: MarketSymbol) -> list[dict]:
    """Fetch HK dividend payout history."""
    fn = getattr(ak, "stock_hk_dividend_payout_em", None)
    if fn is None:
        return []
    try:
        df = fn(symbol=symbol.local_symbol)
        if hasattr(df, "empty") and df.empty:
            return []
        dividends: list[dict] = []
        for _, row in df.iterrows():
            dividends.append({
                "fiscal_year": str(row.get("财政年度", "")),
                "scheme": str(row.get("分红方案", "")),
                "type": str(row.get("分配类型", "")),
                "ex_date": str(row.get("除净日", "")),
                "payment_date": str(row.get("发放日", "")),
                "announcement_date": str(row.get("最新公告日期", "")),
            })
        return dividends
    except Exception:
        return []


def _fetch_capital_flow_context(ak: object) -> dict:
    """Fetch North/South-bound capital flow summary (market-level, shared across CN/HK)."""
    fn = getattr(ak, "stock_hsgt_fund_flow_summary_em", None)
    if fn is None:
        return {"enabled": False, "warnings": ["hsgt_fund_flow not available"]}
    try:
        df = fn()
        if hasattr(df, "empty") and df.empty:
            return {"enabled": False, "warnings": ["No capital flow data"]}
        north = df[df["资金方向"] == "北向"]
        south = df[df["资金方向"] == "南向"]
        north_net = north["成交净买额"].sum() if not north.empty else None
        south_net = south["成交净买额"].sum() if not south.empty else None
        return {
            "enabled": True,
            "north_bound_net": _round_number(north_net) if north_net is not None else None,
            "south_bound_net": _round_number(south_net) if south_net is not None else None,
            "date": datetime.now().date().isoformat(),
            "warnings": [],
        }
    except Exception as exc:
        return {"enabled": False, "warnings": [type(exc).__name__]}


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
    latest = _latest_record(records)

    # HK balance sheet / profit sheet are row-oriented; pivot to column-oriented
    raw_balance_records, balance_errors = _fetch_hk_balance_sheet_records(ak, symbol)
    balance_records = _pivot_hk_row_records(raw_balance_records)
    raw_profit_records, profit_errors = _fetch_hk_profit_sheet_records(ak, symbol)
    profit_records = _pivot_hk_row_records(raw_profit_records)

    errors.extend(cash_errors)
    errors.extend(balance_errors)
    errors.extend(profit_errors)
    errors.extend(announcement_errors)

    values = (
        _akshare_values_from_record(
            latest,
            _latest_record(cash_records),
            _latest_record(balance_records),
            _latest_record(profit_records),
        )
        if latest else {}
    )

    # Optional: profit forecast, dividends, capital flow
    mgmt_guidance = _fetch_hk_profit_forecast(ak, symbol)
    dividends = _fetch_hk_dividends(ak, symbol)
    capital_flow = _fetch_capital_flow_context(ak)

    return _akshare_profile_from_values(
        symbol=symbol,
        source=source,
        currency="HKD",
        report_date=_record_date(latest),
        values=values,
        announcements=_announcements_from_records(announcements_records, source),
        errors=errors,
        management_guidance=mgmt_guidance,
        dividends=dividends,
        capital_flow_context=capital_flow,
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
