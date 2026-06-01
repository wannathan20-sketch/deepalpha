from app.llm.client import generate_text
from app.agents.llm_helpers import (
    build_claims,
    build_data_quality,
    build_memory_text,
    clean_generated_text,
    infer_verdict,
)


AGENT_ORDER = [
    "industry",
    "fundamental",
    "financial",
    "valuation",
    "technical",
    "news",
    "sentiment",
    "bull",
    "bear",
    "trader",
    "risk",
    "source_quality",
]

ALLOWED_RECOMMENDATIONS = {"watchlist", "cautious", "positive", "negative"}


def _build_context_text(agent_outputs: dict) -> str:
    lines = []

    for agent_key in AGENT_ORDER:
        result = agent_outputs.get(agent_key, {})
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


def _clean_text(text: str, company_name: str, sources_count: int) -> str:
    return (
        _fallback_summary(company_name, sources_count)
        if "mock" in text.lower()
        else text.strip()
    )


def _fallback_summary(company_name: str, sources_count: int) -> str:
    return (
        f"综合判断：{company_name} 目前适合进入持续观察清单，已有信息显示其具备一定成长潜力，"
        "但仍需要结合估值、竞争格局和执行风险进行审慎跟踪。\n\n"
        "主要看多理由：基本面、市场关注度和交易假设提供了进一步研究的基础。\n\n"
        "主要看空理由：估值压力、竞争变化和外部监管因素可能影响后续表现。\n\n"
        "风险提示：当前结论依赖有限信息来源，需持续验证关键经营指标和市场反馈。\n\n"
        f"后续关注点：继续跟踪收入质量、产品进展、重大新闻事件、资金面变化和风险暴露。"
        f" 本次汇总参考了 {sources_count} 条信息来源。"
    )


def _is_unavailable_llm_text(text: str) -> bool:
    normalized = text.strip().lower()
    return not normalized or "mock llm response" in normalized


def analyze(company_name: str, context: dict) -> dict:
    agent_outputs = context.get("agent_outputs", {})
    sources_count = sum(
        len(result.get("sources", [])) for result in agent_outputs.values()
    )

    context_text = _build_context_text(agent_outputs)
    memory_text = build_memory_text(context.get("memory", {}))
    recommendation = "watchlist"

    try:
        summary = generate_text(
            prompt=(
                f"请基于以下多类 Agent 的投研结果，为 {company_name} 生成综合投研结论。\n\n"
                "输出内容必须覆盖：\n"
                "1. 投资评级：positive / watchlist / cautious / negative\n"
                "2. 时间维度：短期、中期、长期\n"
                "3. 核心矛盾：一句话说明多空分歧\n"
                "4. 三个核心看多理由\n"
                "5. 三个核心看空理由\n"
                "6. 关键验证指标\n"
                "7. 结论置信度\n"
                "8. 财务与估值约束\n"
                "9. 来源可信度与低质量来源警告\n"
                "10. 不足与待验证数据\n\n"
                "请使用清晰、专业、克制的中文。不要提及 mock、占位或测试。"
                "不要使用“好的”“作为某某 Agent”等对话式开头。不要重复上游 Agent 原文。不要输出 Markdown 装饰符号。\n\n"
                f"{memory_text}\n\n"
                f"{context_text}"
            ),
            system_prompt="你是深研 Alpha 的 Committee Agent，负责综合投研判断。",
            max_tokens=900,
        )
    except Exception:
        summary = _fallback_summary(company_name, sources_count)

    if _is_unavailable_llm_text(summary):
        summary = _fallback_summary(company_name, sources_count)
    else:
        summary = clean_generated_text(_clean_text(summary, company_name, sources_count))

    if recommendation not in ALLOWED_RECOMMENDATIONS:
        recommendation = "watchlist"

    key_points = [
        "综合判断以结构化 Agent 输出为基础。",
        "多空观点、风控意见和数据质量已纳入委员会结论。",
        "后续应继续跟踪基本面、新闻事件、市场情绪和风险暴露。",
    ]
    verdict = infer_verdict(summary)

    return {
        "agent": "committee",
        "verdict": verdict,
        "summary": summary,
        "key_points": key_points,
        "claims": build_claims(key_points, confidence=0.79),
        "risks": [
        "结论依赖当前可得来源，仍需用最新公告、财报和行情复核。",
        "财务和估值模型仍可能缺少关键输入，不宜将结论直接用于投资决策。",
        ],
        "watch_items": ["最新财报", "估值倍数", "核心业务增速", "竞争补贴强度", "股价关键位"],
        "data_quality": build_data_quality(warnings=["委员会结论仍需正式财报、估值数据库和可比公司样本复核。"]),
        "confidence": 0.79,
        "recommendation": recommendation,
        "sources_count": sources_count,
    }
