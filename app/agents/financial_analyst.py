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
        return f"财报摘要不可用：{financial_profile.get('reason', '未提供结构化财报数据。')}"

    lines: list[str] = []

    fields = [
        ("Symbol", financial_profile.get("symbol")),
        ("Source", financial_profile.get("source")),
        ("Currency", financial_profile.get("currency")),
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
        ("Operating Cash Flow Change %", financial_profile.get("operating_cash_flow_change_percent")),
        ("Free Cash Flow", financial_profile.get("free_cash_flow")),
        ("Cash", financial_profile.get("cash")),
        ("Debt", financial_profile.get("debt")),
        ("Short-term Debt", financial_profile.get("short_term_debt")),
        ("Long-term Debt", financial_profile.get("long_term_debt")),
        ("Total Assets", financial_profile.get("total_assets")),
        ("Total Liabilities", financial_profile.get("total_liabilities")),
        ("Shareholders Equity", financial_profile.get("shareholders_equity")),
        ("Filing URL", financial_profile.get("filing_url")),
    ]
    lines.append("\n".join(f"{label}: {value}" for label, value in fields if value not in {None, ""}))

    # Management guidance / analyst consensus
    mgmt = financial_profile.get("management_guidance", {})
    if mgmt.get("enabled"):
        consensus = mgmt.get("analyst_consensus", {})
        if consensus:
            lines.append("\n分析师盈利预测共识：")
            for k, v in consensus.items():
                if v is not None and v != 0:
                    lines.append(f"  {k}: {v}")
        broker_estimates = mgmt.get("broker_estimates", [])
        if broker_estimates:
            lines.append(f"券商预测（共 {len(broker_estimates)} 条）：")
            for est in broker_estimates[:5]:
                lines.append(f"  {est.get('broker', '')} FY{est.get('fiscal_year', '')}: EPS={est.get('eps')}, 目标价={est.get('target_price')}, 评级={est.get('rating')}")

    # Announcement type breakdown
    ann_summary = financial_profile.get("announcement_summary", {})
    if ann_summary:
        lines.append("\n公告类型分布：")
        for ct, anns in sorted(ann_summary.items()):
            lines.append(f"  {ct}: {len(anns)} 条")

    # Dividends
    dividends = financial_profile.get("dividends", [])
    if dividends:
        lines.append(f"\n分红记录（共 {len(dividends)} 条）：")
        for d in dividends[:5]:
            lines.append(f"  FY{d.get('fiscal_year', '')}: {d.get('scheme', '')} (除净日 {d.get('ex_date', '')})")

    # Segment data
    seg = financial_profile.get("segment_data", {})
    if seg.get("enabled"):
        if seg.get("quantitative") is not False:
            # CN: structured quantitative segment data
            lines.append(f"\n分业务收入结构（报告期 {seg.get('report_date', '')}）：")
            for key, label in [("by_product", "按产品"), ("by_industry", "按行业"), ("by_region", "按地区")]:
                items = seg.get(key, [])
                if items:
                    lines.append(f"\n  {label}分类：")
                    for item in items:
                        parts = [item.get("segment", "")]
                        rev = item.get("revenue")
                        rev_pct = item.get("revenue_pct")
                        gm = item.get("gross_margin")
                        if rev is not None:
                            parts.append(f"收入 {rev:,.0f}")
                        if rev_pct is not None:
                            parts.append(f"占比 {rev_pct}%")
                        if gm is not None:
                            parts.append(f"毛利率 {gm}%")
                        lines.append(f"    {'，'.join(parts)}")
        else:
            # HK: qualitative segment context from yfinance
            qual_segs = seg.get("qualitative_segments", [])
            if qual_segs:
                lines.append(f"\n分业务板块（定性来源 — {seg.get('source', '')}）：")
                lines.append(f"  识别板块：{' / '.join(qual_segs)}")
                lines.append("  注意：上述为业务描述中提取的定性分类，非结构化财务数据。")
            sector = seg.get("sector", "")
            industry = seg.get("industry", "")
            if sector or industry:
                lines.append(f"  GICS 分类：{sector} / {industry}" if (sector and industry) else "")

    # Official management earnings guidance
    eg = financial_profile.get("earnings_guidance", {})
    if eg.get("enabled"):
        pas = eg.get("pre_announcements", [])
        ers = eg.get("express_reports", [])
        if pas:
            lines.append(f"\n管理层正式业绩预告（共 {len(pas)} 条）：")
            for pa in pas[:3]:
                lines.append(
                    f"  {pa.get('report_date', '')} {pa.get('forecast_type', '')}"
                    f" | {pa.get('indicator', '')}"
                    f" | {pa.get('change_description', '')}"
                    f" | 变动幅度 {pa.get('change_range', '')}%"
                )
                reason = pa.get("change_reason", "")
                if reason:
                    lines.append(f"    原因：{reason}")
        if ers:
            lines.append(f"\n管理层正式业绩快报（共 {len(ers)} 条）：")
            for er in ers[:3]:
                lines.append(
                    f"  {er.get('report_date', '')} {er.get('forecast_type', '')}"
                    f" | {er.get('indicator', '')}"
                    f" | {er.get('change_description', '')}"
                    f" | 变动幅度 {er.get('change_range', '')}%"
                )

    return "\n".join(lines)


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
            f"请基于结构化财报摘要和公开信息，为 {company_name} 生成财务分析。\n"
            "结构化财报来源是财务数字的优先事实锚点；新闻和网页搜索只用于补充解释。\n"
            "必须覆盖：收入趋势、毛利率、经营利润率、净利润、经营现金流、分业务收入或地区结构、资产负债表风险。\n"
            "如果公开信息不足，请明确写出“待补充数据”，不要编造数字。\n"
            "要求：不要使用对话式开头，不要重复来源原文，不要输出 Markdown 装饰符号。\n\n"
            f"{memory_text}\n\n"
            f"结构化财报摘要：\n{financial_profile_text}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Financial Analyst，负责财务报表分析。",
        max_tokens=700,
    )

    financial_sources = []
    if financial_profile.get("filing_url"):
        financial_sources.append(
            {
                "title": f"{financial_profile.get('source', 'financial filing')} {financial_profile.get('filing_type', 'filing')} for {financial_profile.get('symbol', company_name)}",
                "snippet": "Structured financial profile and latest filing metadata used for financial metrics.",
                "url": financial_profile.get("filing_url"),
            }
        )

    risks = [
        "公开搜索结果不能替代正式财报，收入、利润率和现金流需以公司披露文件复核。",
    ]
    seg = financial_profile.get("segment_data", {})
    if not seg.get("enabled"):
        risks.append("缺少分业务数据时，无法判断增长质量与利润贡献结构。")
    elif seg.get("quantitative") is False:
        risks.append("分业务数据仅为定性分类（非结构化营收数字），增长质量判断需额外核实。")
    if not financial_profile.get("earnings_guidance", {}).get("enabled"):
        risks.append("缺少管理层正式业绩指引，盈利预测仅依赖分析师共识。")

    return structure_agent_result(
        agent="Financial Analyst",
        summary=summary,
        confidence=0.78 if financial_profile.get("enabled") else 0.72,
        sources=financial_sources + sources,
        risks=risks,
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
