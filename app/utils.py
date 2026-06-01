def safe_run_agent(agent_name: str, func, company_name: str, context: dict) -> dict:
    try:
        return func(company_name, context)
    except Exception as exc:
        return {
            "agent": agent_name,
            "summary": f"{agent_name} failed, fallback result generated.",
            "key_points": ["Agent execution failed", "Fallback result used"],
            "confidence": 0.3,
            "sources": [],
            "error": str(exc),
        }
