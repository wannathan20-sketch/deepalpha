TRADER_BLOCKED_TERMS = (
    "mock",
    "placeholder",
    "占位",
    "该模块当前为占位分析",
    "买入",
    "卖出",
    "强烈推荐",
    "目标价",
    "自动交易指令",
)


def _build_trader_context(agent_outputs: dict) -> str:
    lines = []
    for agent_key in (
        "fundamental",
        "technical",
        "news",
        "sentiment",
        "bull",
        "bear",
        "risk",
    ):
        result = agent_outputs.get(agent_key)
        if not result:
            continue

        lines.extend(
            [
                f"Agent: {agent_key}",
                f"Summary: {result.get('summary', '')}",
                "Key Points:",
            ]
        )
        lines.extend(f"- {point}" for point in result.get("key_points", []))
        lines.append("")

    return "\n".join(lines)


def _fallback_trader_summary(company_name: str) -> str:
    return (
        f"观察策略：围绕 {company_name} 的基本面变化、新闻事件、市场情绪和多空分歧进行持续记录，"
        "仅用于研究跟踪，不构成投资建议。\n"
        "- 分批跟踪思路：按时间窗口和事件节点拆分观察，避免依赖单一时点信息。\n"
        "- 关键触发条件：重点关注收入质量、产品进展、重大新闻、情绪变化和风险暴露是否发生实质变化。\n"
        "- 风险控制假设：在信息不充分或波动放大时降低结论确定性，优先保留风险缓冲。"
    )


def _clean_trader_text(text: str, company_name: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()

    if not stripped:
        return _fallback_trader_summary(company_name)

    if any(term in lowered for term in TRADER_BLOCKED_TERMS[:4]):
        return _fallback_trader_summary(company_name)

    if any(term in stripped for term in TRADER_BLOCKED_TERMS[4:]):
        return _fallback_trader_summary(company_name)

    return stripped


def analyze(company_name: str, context: dict) -> dict:
    from app.agents.llm_helpers import extract_key_points
    from app.llm.client import generate_text

    context_text = _build_trader_context(context.get("agent_outputs", {}))
    summary = generate_text(
        prompt=(
            f"请基于已有 Agent 结果，为 {company_name} 生成 Trader Agent 的研究输出。\n"
            "输出必须包含以下四部分：\n"
            "1. 观察策略\n"
            "2. 分批跟踪思路\n"
            "3. 关键触发条件\n"
            "4. 风险控制假设\n\n"
            "不得给出具体交易动作、强烈倾向性推荐、价格预测或自动化执行建议。\n"
            "必须明确说明：不构成投资建议。\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Trader Agent，负责交易观察和风险假设。",
        max_tokens=650,
    )
    summary = _clean_trader_text(summary, company_name)

    return {
        "agent": "Trader Agent",
        "summary": summary,
        "key_points": extract_key_points(summary),
        "confidence": 0.75,
    }
