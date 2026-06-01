def analyze(company_name: str, context: dict) -> dict:
    from app.agents.llm_helpers import (
        build_agent_outputs_text,
        clean_generated_text,
        extract_key_points,
    )
    from app.llm.client import generate_text

    context_text = build_agent_outputs_text(context.get("agent_outputs", {}))
    summary = generate_text(
        prompt=(
            f"请基于已有 Agent 结果，为 {company_name} 生成看多观点。"
            "请聚焦业务、产品、增长、市场情绪等支持性因素，并保持审慎表达。\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Bull Analyst，负责提出看多理由。",
        max_tokens=500,
    )
    summary = clean_generated_text(summary)

    return {
        "agent": "Bull Analyst",
        "summary": summary,
        "key_points": extract_key_points(summary),
        "confidence": 0.75,
    }
