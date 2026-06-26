def _resolve_market(market_profile: dict, financial_profile: dict) -> str:
    """Detect the target market from profile metadata.
    从行情和财报画像中推断标的所属市场（CN / HK / US），无法判断时返回 "unknown"。
    """
    market = (market_profile.get("market") or "").upper()
    if market in ("CN", "A", "A_SHARE"):
        return "CN"
    if market in ("HK", "HKG"):
        return "HK"
    if market in ("US", "USA", "NASDAQ", "NYSE", "AMEX"):
        return "US"
    exchange = (market_profile.get("exchange") or "").upper()
    if exchange in ("SSE", "SZSE"):
        return "CN"
    if exchange in ("HKEX",):
        return "HK"
    if exchange in ("NASDAQ", "NYSE", "AMEX", "OTC"):
        return "US"
    fin_source = str(financial_profile.get("source") or "").lower()
    if "akshare" in fin_source:
        return "CN"
    if "sec" in fin_source or "edgar" in fin_source or "companyfacts" in fin_source:
        return "US"
    return "unknown"


_MARKET_TASK_VARIANTS: dict[str, dict[str, str]] = {
    "CN": {
        "fundamental": "基本面分析（A 股，关注国内竞争格局与产业政策）",
        "financial": "财务报表分析（A 股，基于 Akshare / 东方财富数据源）",
        "valuation": "估值与情景分析（A 股，适用 PE/PB/PS 估值，对比行业均值）",
        "technical": "技术面分析（A 股，关注北向资金与龙虎榜动向）",
        "news": "新闻事件分析（A 股，关注监管政策、行业利好与财报披露窗口）",
        "sentiment": "市场情绪分析（A 股，融资融券、涨停/跌停情绪）",
        "risk": "风控审查（A 股，退市风险、股权质押、大股东减持）",
    },
    "HK": {
        "fundamental": "基本面分析（港股，关注 AH 溢价与中资/外资定价分歧）",
        "financial": "财务报表分析（港股，基于 Akshare 港股财务数据）",
        "valuation": "估值与情景分析（港股，对比恒指与行业 PE 中枢）",
        "technical": "技术面分析（港股，关注南向资金流向与成交量变化）",
        "news": "新闻事件分析（港股，关注港交所公告、内地政策联动）",
        "sentiment": "市场情绪分析（港股，关注沽空比率与港股通资金动向）",
        "risk": "风控审查（港股，汇率敞口、做空报告与流动性风险）",
    },
    "US": {
        "fundamental": "基本面分析（美股，关注竞争壁垒与全球市场份额）",
        "financial": "财务报表分析（美股，基于 SEC EDGAR 10-K/10-Q 数据）",
        "valuation": "估值与情景分析（美股，DCF 与可比公司分析）",
        "technical": "技术面分析（美股，关注期权 Gamma 集中度与 VIX）",
        "news": "新闻事件分析（美股，关注美联储政策与财报季预期）",
        "sentiment": "市场情绪分析（美股，关注做空比率与机构持仓变化）",
        "risk": "风控审查（美股，利率敏感性、监管与地缘政治风险）",
    },
}


def create_plan(
    company_name: str,
    market_profile: dict | None = None,
    financial_profile: dict | None = None,
) -> dict:
    """Generate a market-aware research plan.
    根据标的所属市场动态生成研究计划，不同市场的 Agent 关注点不同。
    """
    market_profile = market_profile or {}
    financial_profile = financial_profile or {}
    market = _resolve_market(market_profile, financial_profile)
    variants = _MARKET_TASK_VARIANTS.get(market, {})
    market_label = {"CN": "A 股", "HK": "港股", "US": "美股"}.get(market, market)

    default_tasks = [
        ("industry", "行业研究分析", "Industry Analyst"),
        ("fundamental", "基本面分析", "Fundamental Analyst"),
        ("financial", "财务报表分析", "Financial Analyst"),
        ("valuation", "估值与情景分析", "Valuation Analyst"),
        ("technical", "技术面分析", "Technical Analyst"),
        ("news", "新闻事件分析", "News Analyst"),
        ("sentiment", "市场情绪分析", "Sentiment Analyst"),
        ("bull", "看多观点", "Bull Analyst"),
        ("bear", "看空观点", "Bear Analyst"),
        ("trader", "交易假设", "Trader"),
        ("risk", "风控审查", "Risk Manager"),
        ("source_quality", "来源质量审查", "Source Quality Agent"),
        ("committee", "综合决策汇总", "Committee Agent"),
    ]

    tasks = []
    for task_id, title, assigned_to in default_tasks:
        tasks.append(
            {
                "id": task_id,
                "title": variants.get(task_id, title),
                "assigned_to": assigned_to,
            }
        )

    objective = (
        f"为 {company_name}（{market_label}）生成结构化投研计划，"
        f"各 Agent 按市场特征调整分析重点。"
    )

    return {
        "agent": "Planner Agent",
        "objective": objective,
        "market": market,
        "market_label": market_label,
        "tasks": tasks,
    }
