from app.agents.llm_helpers import build_memory_text, structure_agent_result
from app.llm.client import generate_text
from app.tools.search import search_public_info


def _build_context_text(sources: list[dict]) -> str:
    return "\n".join(
        f"- {source.get('title', '')}: {source.get('snippet', '')} ({source.get('url', '')})"
        for source in sources
    )


def _build_financial_profile_text(financial_profile: dict) -> str:
    if not financial_profile.get("enabled"):
        return f"SEC 财报摘要不可用：{financial_profile.get('reason', '未提供美股 symbol。')}"

    fields = [
        ("Symbol", financial_profile.get("symbol")),
        ("Source", financial_profile.get("source")),
        ("Filing", f"{financial_profile.get('filing_type', '')} {financial_profile.get('fiscal_period', '')}".strip()),
        ("Report Date", financial_profile.get("report_date")),
        ("Revenue", financial_profile.get("revenue")),
        ("Revenue Change %", financial_profile.get("revenue_change_percent")),
        ("Gross Profit", financial_profile.get("gross_profit")),
        ("Gross Margin %", financial_profile.get("gross_margin_percent")),
        ("Operating Income", financial_profile.get("operating_income")),
        ("Operating Margin %", financial_profile.get("operating_margin_percent")),
        ("Net Income", financial_profile.get("net_income")),
        ("Net Income Change %", financial_profile.get("net_income_change_percent")),
        ("EPS Diluted", financial_profile.get("eps_diluted")),
        ("Operating Cash Flow", financial_profile.get("operating_cash_flow")),
        ("Free Cash Flow", financial_profile.get("free_cash_flow")),
        ("Cash", financial_profile.get("cash")),
        ("Debt", financial_profile.get("debt")),
        ("Total Assets", financial_profile.get("total_assets")),
        ("Total Liabilities", financial_profile.get("total_liabilities")),
        ("Shareholders Equity", financial_profile.get("shareholders_equity")),
        ("Filing URL", financial_profile.get("filing_url")),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if value not in {None, ""})


def analyze(company_name: str, context: dict) -> dict:
    sources = search_public_info(
        f"{company_name} revenue gross margin operating margin net income cash flow financial results"
    )
    context_text = _build_context_text(sources)
    memory_text = build_memory_text(context.get("memory", {}))
    financial_profile = context.get("financial_profile", {})
    financial_profile_text = _build_financial_profile_text(financial_profile)
    summary = generate_text(
        prompt=(
            f"请基于 SEC 结构化财报摘要和公开信息，为 {company_name} 生成财务分析。\n"
            "SEC companyfacts 是财务数字的优先事实来源；新闻和网页搜索只用于补充解释。\n"
            "必须覆盖：收入趋势、毛利率、经营利润率、净利润、经营现金流、分业务收入或地区结构、资产负债表风险。\n"
            "如果公开信息不足，请明确写出“待补充数据”，不要编造数字。\n"
            "要求：不要使用对话式开头，不要重复来源原文，不要输出 Markdown 装饰符号。\n\n"
            f"{memory_text}\n\n"
            f"SEC 结构化财报摘要：\n{financial_profile_text}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Financial Analyst，负责财务报表分析。",
        max_tokens=700,
    )

    sec_sources = []
    if financial_profile.get("filing_url"):
        sec_sources.append(
            {
                "title": f"SEC {financial_profile.get('filing_type', 'filing')} for {financial_profile.get('symbol', company_name)}",
                "snippet": "SEC companyfacts and latest filing metadata used for structured financial metrics.",
                "url": financial_profile.get("filing_url"),
            }
        )

    return structure_agent_result(
        agent="Financial Analyst",
        summary=summary,
        confidence=0.78 if financial_profile.get("enabled") else 0.72,
        sources=sec_sources + sources,
        risks=[
            "公开搜索结果不能替代正式财报，收入、利润率和现金流需以公司披露文件复核。",
            "缺少分业务数据时，无法判断增长质量与利润贡献结构。",
        ],
        watch_items=[
            "收入增速",
            "毛利率",
            "经营利润率",
            "净利润率",
            "经营现金流",
            "分业务收入占比",
        ],
        financial_profile=financial_profile,
    )
