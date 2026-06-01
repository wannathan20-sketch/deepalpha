def _has_text_content(output: dict) -> bool:
    summary = str(output.get("summary", "")).strip()
    key_points = output.get("key_points", [])

    if summary:
        return True

    if isinstance(key_points, list):
        return any(str(point).strip() for point in key_points)

    return bool(str(key_points).strip())


def check_citations(agent_outputs: dict, rag_chunks: list) -> dict:
    checked_agents = []
    issues = []

    if not rag_chunks:
        issues.append("No RAG chunks available for citation support.")

    if not agent_outputs:
        issues.append("No agent outputs available for citation checking.")

    for agent_name, output in agent_outputs.items():
        checked_agents.append(agent_name)

        if not isinstance(output, dict) or not _has_text_content(output):
            issues.append(f"{agent_name} has no text content.")

    return {
        "passed": not issues,
        "checked_agents": checked_agents,
        "issues": issues,
        "sources_count": len(rag_chunks),
    }
