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
            f"请基于已有 Agent 结果，为 {company_name} 生成看空观点。"
            "请聚焦估值、竞争、执行、监管、信息不足等潜在压力，并保持审慎表达。\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Bear Analyst，负责提出看空风险。",
        max_tokens=500,
    )
    summary = clean_generated_text(summary)

    return {
        "agent": "Bear Analyst",
        "summary": summary,
        "key_points": extract_key_points(summary),
        "confidence": 0.75,
    }
