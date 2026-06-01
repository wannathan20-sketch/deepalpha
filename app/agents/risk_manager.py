def analyze(company_name: str, context: dict) -> dict:
    from app.agents.llm_helpers import (
        build_memory_text,
        build_agent_outputs_text,
        clean_generated_text,
        extract_key_points,
        structure_agent_result,
    )
    from app.llm.client import generate_text

    agent_outputs = context.get("agent_outputs", {})
    bull_view = agent_outputs.get("bull", {})
    bear_view = agent_outputs.get("bear", {})
    context_text = build_agent_outputs_text(agent_outputs)
    memory_text = build_memory_text(context.get("memory", {}))
    summary = generate_text(
        prompt=(
            f"请基于已有 Agent 结果，为 {company_name} 生成风控审查。"
            "必须明确参考看多观点和看空观点，输出主要风险、风险缓释思路、后续监控指标。"
            "请保留免责声明：不构成投资建议。\n"
            "要求：不要使用对话式开头，不要重复上游 Agent 原文，不要输出 Markdown 装饰符号。\n\n"
            f"{memory_text}\n\n"
            f"Bull Summary: {bull_view.get('summary', '')}\n"
            f"Bear Summary: {bear_view.get('summary', '')}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Risk Manager，负责风险审查。",
        max_tokens=600,
    )
    summary = clean_generated_text(summary)

    key_points = extract_key_points(summary)
    return structure_agent_result(
        agent="Risk Manager",
        summary=summary,
        confidence=0.75,
        risks=key_points,
        watch_items=["关键财务指标是否恶化", "竞争补贴强度", "监管变化", "股价波动率"],
        verdict="negative" if key_points else "neutral",
    )
