def analyze(company_name: str, context: dict) -> dict:
    from app.agents.llm_helpers import (
        build_agent_outputs_text,
        clean_generated_text,
        structure_agent_result,
    )
    from app.llm.client import generate_text

    context_text = build_agent_outputs_text(context.get("agent_outputs", {}))
    market_profile = context.get("market_profile", {})
    market_text = ""
    if market_profile.get("enabled"):
        market_text = (
            "\n\n真实行情摘要："
            f"\n- Symbol: {market_profile.get('symbol') or market_profile.get('yahoo_symbol')}"
            f"\n- Provider: {market_profile.get('provider')}"
            f"\n- Latest Close: {market_profile.get('latest_close')}"
            f"\n- 6M Return: {market_profile.get('period_return_percent')}%"
            f"\n- 6M High/Low: {market_profile.get('high_6m')} / {market_profile.get('low_6m')}"
            f"\n- MA20/MA60: {market_profile.get('ma20')} / {market_profile.get('ma60')}"
            f"\n- Trend: {market_profile.get('trend')}"
            f"\n- Annualized Volatility: {market_profile.get('annualized_volatility_percent')}%"
        )
    else:
        market_text = f"\n\n行情摘要不可用：{market_profile.get('reason', '未提供 symbol。')}"

    summary = generate_text(
        prompt=(
            f"请基于已有 Agent 结果，为 {company_name} 生成技术面分析。"
            "请优先使用真实行情摘要中的数值，关注趋势、波动、关键观察区间和技术风险，不要使用投资指令。\n"
            "要求：不要使用对话式开头，不要重复上游 Agent 原文，不要输出 Markdown 装饰符号。\n\n"
            f"{context_text}"
            f"{market_text}"
        ),
        system_prompt="你是深研 Alpha 的 Technical Analyst，负责技术面分析。",
        max_tokens=500,
    )
    summary = clean_generated_text(summary)

    sources = []
    if market_profile.get("enabled"):
        sources = [
            {
                "title": f"{market_profile.get('provider', 'market')} market data for {market_profile.get('yahoo_symbol')}",
                "url": market_profile.get("source_url", "#"),
            }
        ]

    return structure_agent_result(
        agent="Technical Analyst",
        summary=summary,
        confidence=0.75,
        sources=sources,
        risks=["技术指标只能反映价格行为，不能单独构成投资结论。"],
        watch_items=["MA20/MA60", "6 个月高低点", "成交量变化", "关键支撑与压力位"],
        market_profile=market_profile if market_profile.get("enabled") else {},
    )
