def check_citations(team_results: dict, markdown_report: str) -> dict:
    total_agents = len(team_results)
    total_sources = 0
    agents_with_sources = []
    agents_without_sources = []

    for agent_key, result in team_results.items():
        sources = result.get("sources", [])
        total_sources += len(sources)

        if sources:
            agents_with_sources.append(agent_key)
        else:
            agents_without_sources.append(agent_key)

    lower_report = markdown_report.lower()
    has_citation_section = "来源" in markdown_report or "sources" in lower_report
    source_coverage = len(agents_with_sources) / total_agents if total_agents else 0.0
    section_score = 1.0 if has_citation_section else 0.0
    citation_score = round((source_coverage + section_score) / 2, 2)

    return {
        "total_sources": total_sources,
        "agents_with_sources": agents_with_sources,
        "agents_without_sources": agents_without_sources,
        "has_citation_section": has_citation_section,
        "citation_score": citation_score,
    }
