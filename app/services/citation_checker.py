import hashlib
import re
from urllib.parse import urlparse


_HASH_DIM = 128


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9一-鿿]+", text.lower())


def _hash_embedding(text: str) -> list[float]:
    """Deterministic hash-based embedding used for lightweight semantic scoring.
    确定性哈希向量，用于轻量级语义评分，不依赖外部 embedding API。
    """
    vector = [0.0] * _HASH_DIM
    tokens = _tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % _HASH_DIM
        vector[index] += 1.0
    magnitude = sum(value * value for value in vector) ** 0.5
    if not magnitude:
        return vector
    return [value / magnitude for value in vector]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return round(max(0.0, min(1.0, dot)), 4)


def _chunk_text(chunk: dict) -> str:
    return " ".join(
        [
            chunk.get("title", ""),
            chunk.get("content", ""),
        ]
    )


def _claim_semantic_score(claim_text: str, chunks: list[dict]) -> float:
    """Max cosine similarity between a claim and any RAG chunk.
    计算声明文本与所有 RAG 分块的最大余弦相似度。
    """
    if not claim_text.strip() or not chunks:
        return 0.0
    claim_vec = _hash_embedding(claim_text)
    best = 0.0
    for chunk in chunks:
        chunk_vec = _hash_embedding(_chunk_text(chunk))
        sim = _cosine_similarity(claim_vec, chunk_vec)
        if sim > best:
            best = sim
    return best


# Threshold below which a claim is considered semantically unverifiable
# from the available RAG evidence.
# 语义匹配阈值：低于此值的声明视为无法从现有 RAG 证据中验证。
SEMANTIC_MATCH_THRESHOLD = 0.25


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


def _collect_claim_metrics(agent_outputs: dict, rag_chunks: list) -> dict:
    total_claims = 0
    cited_claims = 0
    semantically_matched_claims = 0
    agents_with_claims = []
    agents_with_cited_claims = []
    unverified_claims: list[dict] = []

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
            # Semantic check: does claim text match any RAG chunk?
            claim_text = str(claim.get("claim", ""))
            sim = _claim_semantic_score(claim_text, rag_chunks)
            if sim >= SEMANTIC_MATCH_THRESHOLD:
                semantically_matched_claims += 1
            else:
                unverified_claims.append(
                    {
                        "agent": agent_name,
                        "claim": claim_text[:200],
                        "semantic_score": sim,
                        "has_source_url": _valid_url(claim.get("source_url")),
                    }
                )
        if agent_cited_claims:
            agents_with_cited_claims.append(agent_name)

    url_coverage = round(cited_claims / total_claims, 2) if total_claims else 0.0
    semantic_coverage = (
        round(semantically_matched_claims / total_claims, 2) if total_claims else 0.0
    )
    return {
        "total_claims": total_claims,
        "cited_claims": cited_claims,
        "claim_citation_coverage": url_coverage,
        "semantic_match_count": semantically_matched_claims,
        "semantic_coverage": semantic_coverage,
        "agents_with_claims": agents_with_claims,
        "agents_with_cited_claims": agents_with_cited_claims,
        "unverified_claims": unverified_claims,
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

    claim_metrics = _collect_claim_metrics(agent_outputs, rag_chunks)
    source_metrics = _source_metrics(rag_chunks)

    if claim_metrics["total_claims"] and not claim_metrics["cited_claims"]:
        warnings.append("Agent claims are present but none include source_url evidence.")
    elif claim_metrics["total_claims"] and claim_metrics["claim_citation_coverage"] < 0.3:
        warnings.append("Claim-level citation coverage is below 30%; key conclusions need stronger source binding.")

    # Semantic warnings: flag claims that can't be verified against RAG evidence.
    # 语义警告：标记无法通过 RAG 证据验证的声明。
    unverified = claim_metrics["unverified_claims"]
    if unverified:
        unverified_with_urls = [c for c in unverified if c["has_source_url"]]
        unverified_without_urls = [c for c in unverified if not c["has_source_url"]]
        if unverified_without_urls:
            warnings.append(
                f"{len(unverified_without_urls)} claim(s) have no source URL "
                "and no semantic match in RAG evidence — possible hallucination."
            )
        if unverified_with_urls:
            warnings.append(
                f"{len(unverified_with_urls)} claim(s) have source URLs "
                "but their text does not semantically match any RAG chunk — "
                "cited sources may not support the claim."
            )

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
