from app.agents.llm_helpers import (
    build_agent_outputs_text,
    clean_markdown_artifacts,
    structure_agent_result,
)
from app.llm.client import generate_text


def _build_market_text(market_profile: dict) -> str:
    if not market_profile.get("enabled"):
        return f"行情摘要不可用：{market_profile.get('reason', '未提供 symbol。')}"

    return "\n".join(
        [
            f"Symbol: {market_profile.get('symbol') or market_profile.get('yahoo_symbol')}",
            f"Provider: {market_profile.get('provider')}",
            f"Latest Close: {market_profile.get('latest_close')}",
            f"6M Return: {market_profile.get('period_return_percent')}%",
            f"6M High/Low: {market_profile.get('high_6m')} / {market_profile.get('low_6m')}",
            f"Trend: {market_profile.get('trend')}",
            f"Annualized Volatility: {market_profile.get('annualized_volatility_percent')}%",
        ]
    )


def _build_financial_text(financial_profile: dict) -> str:
    if not financial_profile.get("enabled"):
        return f"财报摘要不可用：{financial_profile.get('reason', '未提供结构化财报数据。')}"

    fields = [
        ("Source", financial_profile.get("source")),
        ("Currency", financial_profile.get("currency")),
        ("Filing", f"{financial_profile.get('filing_type', '')} {financial_profile.get('fiscal_period', '')}".strip()),
        ("Revenue", financial_profile.get("revenue")),
        ("Gross Margin %", financial_profile.get("gross_margin_percent")),
        ("Operating Income", financial_profile.get("operating_income")),
        ("Operating Margin %", financial_profile.get("operating_margin_percent")),
        ("Net Income", financial_profile.get("net_income")),
        ("EPS Diluted", financial_profile.get("eps_diluted")),
        ("Operating Cash Flow", financial_profile.get("operating_cash_flow")),
        ("Free Cash Flow", financial_profile.get("free_cash_flow")),
        ("Cash", financial_profile.get("cash")),
        ("Debt", financial_profile.get("debt")),
        ("Total Assets", financial_profile.get("total_assets")),
        ("Total Liabilities", financial_profile.get("total_liabilities")),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if value not in {None, ""})


def analyze(company_name: str, context: dict) -> dict:
    agent_outputs = context.get("agent_outputs", {})
    market_profile = context.get("market_profile", {})
    financial_profile = context.get("financial_profile", {})
    context_text = build_agent_outputs_text(agent_outputs)
    market_text = _build_market_text(market_profile)
    financial_text = _build_financial_text(financial_profile)

    summary = generate_text(
        prompt=(
            f"请基于已有 Agent 结果、行情摘要和结构化财务事实，为 {company_name} 生成估值分析。\n"
            "必须覆盖：PE、PS、EV/EBITDA、可比公司估值、Bull/Base/Bear 情景、估值约束和安全边际。\n"
            "如果缺少市值、净利润、收入、EBITDA 或可比公司数据，请明确标注“待补充数据”，不要编造倍数或目标价。\n"
            "结构化财务事实用于约束收入、利润、现金流、现金和债务，不得与其冲突。\n"
            "输出应是研究判断，不得给出交易指令。\n"
            "要求：不要使用对话式开头，不要重复上游 Agent 原文，不要输出 Markdown 装饰符号。\n\n"
            f"行情摘要：\n{market_text}\n\n"
            f"结构化财务事实：\n{financial_text}\n\n"
            f"结构化 Agent 上下文：\n{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Valuation Analyst，负责估值与情景分析。",
        max_tokens=750,
    )

    sources = []
    if market_profile.get("enabled"):
        sources.append(
            {
                "title": clean_markdown_artifacts(
                    f"{market_profile.get('provider', 'market')} market data for {market_profile.get('yahoo_symbol')}"
                ),
                "url": market_profile.get("source_url", "#"),
            }
        )
    if financial_profile.get("filing_url"):
        sources.append(
            {
                "title": clean_markdown_artifacts(
                    f"{financial_profile.get('source', 'financial filing')} {financial_profile.get('filing_type', 'filing')} for {financial_profile.get('symbol', company_name)}"
                ),
                "url": financial_profile.get("filing_url", "#"),
            }
        )

    return structure_agent_result(
        agent="Valuation Analyst",
        summary=summary,
        confidence=0.72 if financial_profile.get("enabled") else 0.68,
        sources=sources,
        risks=[
            "估值分析缺少完整财务预测时，只能作为框架判断。",
            "未接入可比公司数据库前，PE、PS、EV/EBITDA 需要人工复核。",
        ],
        watch_items=[
            "PE",
            "PS",
            "EV/EBITDA",
            "可比公司估值区间",
            "Bull/Base/Bear 情景假设",
            "市值与净现金",
        ],
        financial_profile=financial_profile,
    )
