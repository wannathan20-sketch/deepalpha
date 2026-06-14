from urllib.parse import urlparse


def _has_text_content(output: dict) -> bool:
    summary = str(output.get("summary", "")).strip()
    key_points = output.get("key_points", [])

    if summary:
        return True

    if isinstance(key_points, list):
        return any(str(point).strip() for point in key_points)

    return bool(str(key_points).strip())


def _valid_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _collect_claim_metrics(agent_outputs: dict) -> dict:
    total_claims = 0
    cited_claims = 0
    agents_with_claims = []
    agents_with_cited_claims = []

    for agent_name, output in agent_outputs.items():
        if not isinstance(output, dict):
            continue
        claims = output.get("claims", [])
        if not isinstance(claims, list) or not claims:
            continue

        agents_with_claims.append(agent_name)
        agent_cited_claims = 0
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            total_claims += 1
            if _valid_url(claim.get("source_url")):
                cited_claims += 1
                agent_cited_claims += 1
        if agent_cited_claims:
            agents_with_cited_claims.append(agent_name)

    coverage = round(cited_claims / total_claims, 2) if total_claims else 0.0
    return {
        "total_claims": total_claims,
        "cited_claims": cited_claims,
        "claim_citation_coverage": coverage,
        "agents_with_claims": agents_with_claims,
        "agents_with_cited_claims": agents_with_cited_claims,
    }


def _source_metrics(rag_chunks: list) -> dict:
    linked_chunks = [chunk for chunk in rag_chunks if _valid_url(chunk.get("url"))]
    official_chunks = [
        chunk
        for chunk in linked_chunks
        if str(chunk.get("source_grade", "")).upper() == "A"
        or str(chunk.get("source_type", "")) in {"regulatory_filing", "exchange_disclosure"}
    ]
    return {
        "sources_count": len(rag_chunks),
        "linked_sources_count": len(linked_chunks),
        "official_sources_count": len(official_chunks),
        "retrieval_scores": [
            chunk.get("retrieval_score")
            for chunk in rag_chunks
            if chunk.get("retrieval_score") is not None
        ],
    }


def check_citations(agent_outputs: dict, rag_chunks: list) -> dict:
    checked_agents = []
    issues = []
    warnings = []

    if not rag_chunks:
        issues.append("No RAG chunks available for citation support.")

    if not agent_outputs:
        issues.append("No agent outputs available for citation checking.")

    for agent_name, output in agent_outputs.items():
        checked_agents.append(agent_name)

        if not isinstance(output, dict) or not _has_text_content(output):
            issues.append(f"{agent_name} has no text content.")

    claim_metrics = _collect_claim_metrics(agent_outputs)
    source_metrics = _source_metrics(rag_chunks)

    if claim_metrics["total_claims"] and not claim_metrics["cited_claims"]:
        warnings.append("Agent claims are present but none include source_url evidence.")
    elif claim_metrics["total_claims"] and claim_metrics["claim_citation_coverage"] < 0.3:
        warnings.append("Claim-level citation coverage is below 30%; key conclusions need stronger source binding.")

    if rag_chunks and not source_metrics["linked_sources_count"]:
        warnings.append("RAG chunks are present but do not include accessible source URLs.")
    if rag_chunks and not source_metrics["official_sources_count"]:
        warnings.append("No official/regulatory source chunks found; customer-facing use should add primary sources.")

    return {
        "passed": not issues,
        "checked_agents": checked_agents,
        "issues": issues,
        "warnings": warnings,
        "sources_count": source_metrics["sources_count"],
        "total_sources": source_metrics["sources_count"],
        "linked_sources_count": source_metrics["linked_sources_count"],
        "official_sources_count": source_metrics["official_sources_count"],
        "retrieval_scores": source_metrics["retrieval_scores"],
        **claim_metrics,
    }
