import re
from urllib.parse import urlparse


FALLBACK_ANALYSIS = "该模块当前为占位分析，后续可接入真实数据源。"
BLOCKED_TERMS = ("mock", "placeholder", "assumed", "modeled")
VERDICT_KEYWORDS = {
    "positive": ("积极", "正面", "改善", "增长", "超预期", "护城河", "修复"),
    "negative": ("负面", "承压", "下行", "恶化", "不及预期", "亏损", "风险"),
}


def contains_blocked_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BLOCKED_TERMS)


def clean_generated_text(text: str) -> str:
    stripped = text.strip()
    if not stripped or contains_blocked_terms(stripped):
        return FALLBACK_ANALYSIS

    return clean_markdown_artifacts(stripped)


def clean_markdown_artifacts(text: str) -> str:
    lines = []

    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue

        stripped = re.sub(r"^好的[，,]?\s*", "", stripped)
        stripped = re.sub(r"^作为[^，,。]{2,40}[，,]\s*", "", stripped)
        stripped = re.sub(r"^#{1,6}\s*", "", stripped)
        stripped = re.sub(r"^\*{1,2}(.+?)\*{1,2}$", r"\1", stripped)
        stripped = re.sub(r"__([^_]+)__", r"\1", stripped)
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)
        stripped = stripped.replace("**", "").replace("*", "").strip()
        if stripped:
            lines.append(stripped)

    return "\n".join(lines) if lines else FALLBACK_ANALYSIS


def extract_key_points(text: str, max_points: int = 3) -> list[str]:
    points = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith(("-", "*")):
            point = stripped.lstrip("-* ").strip()
        elif re.match(r"^\d+[\.\)、)]\s*", stripped):
            point = re.sub(r"^\d+[\.\)、)]\s*", "", stripped).strip()
        else:
            continue

        point = clean_markdown_artifacts(point)
        if point and not contains_blocked_terms(point):
            points.append(point)

        if len(points) >= max_points:
            return points

    sentences = re.split(r"[。！？.!?]\s*", text)
    for sentence in sentences:
        point = sentence.strip()
        if point and not contains_blocked_terms(point):
            points.append(clean_markdown_artifacts(point)[:120])

        if len(points) >= max_points:
            return points

    return [FALLBACK_ANALYSIS]


def build_agent_outputs_text(agent_outputs: dict) -> str:
    lines = []

    for agent_key, result in agent_outputs.items():
        lines.extend(
            [
                f"Agent: {agent_key}",
                f"Summary: {result.get('summary', '')}",
                "Key Points:",
            ]
        )
        lines.extend(f"- {point}" for point in result.get("key_points", []))

        claims = result.get("claims", [])
        if claims:
            lines.append("Structured Claims:")
            for claim in claims[:5]:
                lines.append(
                    f"- Claim: {claim.get('claim', '')}; Evidence: {claim.get('evidence', '')}; Confidence: {claim.get('confidence', '')}"
                )

        sources = result.get("sources", [])
        if sources:
            lines.append("Sources:")
            for source in sources:
                lines.append(
                    f"- {source.get('title', '')}: {source.get('snippet', '')} ({source.get('url', '')})"
                )

        lines.append("")

    return "\n".join(lines)


def infer_verdict(text: str) -> str:
    positive_score = sum(1 for word in VERDICT_KEYWORDS["positive"] if word in text)
    negative_score = sum(1 for word in VERDICT_KEYWORDS["negative"] if word in text)

    if positive_score and negative_score:
        return "mixed"
    if positive_score:
        return "positive"
    if negative_score:
        return "negative"
    return "neutral"


def _source_url(source: dict) -> str:
    url = str(source.get("url", "")).strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} else ""


def build_claims(key_points: list[str], sources: list[dict] | None = None, confidence: float = 0.7) -> list[dict]:
    claims = []
    sources = sources or []

    for index, point in enumerate(key_points):
        source = sources[index % len(sources)] if sources else {}
        source_url = _source_url(source)
        claims.append(
            {
                "claim": clean_markdown_artifacts(point),
                "evidence": clean_markdown_artifacts(source.get("snippet") or source.get("title") or "需进一步验证。"),
                "source_url": source_url,
                "confidence": confidence if source_url else min(confidence, 0.55),
            }
        )

    return claims


def build_data_quality(sources: list[dict] | None = None, warnings: list[str] | None = None) -> dict:
    sources = sources or []
    valid_source_count = sum(1 for source in sources if _source_url(source))
    quality_warnings = list(warnings or [])

    if not sources:
        quality_warnings.append("缺少外部来源，结论仅可作为初步观察。")
    elif valid_source_count < len(sources):
        quality_warnings.append("部分来源缺少可访问链接。")

    freshness = "unknown"
    if valid_source_count:
        freshness = "needs_review"

    return {
        "source_count": len(sources),
        "linked_source_count": valid_source_count,
        "freshness": freshness,
        "warnings": quality_warnings,
    }


def structure_agent_result(
    agent: str,
    summary: str,
    confidence: float,
    sources: list[dict] | None = None,
    risks: list[str] | None = None,
    watch_items: list[str] | None = None,
    verdict: str | None = None,
    max_points: int = 3,
    **extra,
) -> dict:
    cleaned_summary = clean_generated_text(summary)
    key_points = extract_key_points(cleaned_summary, max_points=max_points)
    source_list = sources or []

    result = {
        "agent": agent,
        "verdict": verdict or infer_verdict(cleaned_summary),
        "summary": cleaned_summary,
        "key_points": key_points,
        "claims": build_claims(key_points, source_list, confidence),
        "risks": [clean_markdown_artifacts(item) for item in (risks or []) if item],
        "watch_items": [clean_markdown_artifacts(item) for item in (watch_items or []) if item],
        "confidence": confidence,
        "data_quality": build_data_quality(source_list),
    }

    if source_list:
        result["sources"] = source_list

    result.update(extra)
    return result


def build_memory_text(memory: dict) -> str:
    recent_history = memory.get("recent_history", [])

    if not recent_history:
        return "暂无历史投研记录。"

    lines = ["历史投研记忆："]
    for record in recent_history:
        lines.extend(
            [
                f"- 时间: {record.get('created_at', '')}",
                f"  Recommendation: {record.get('recommendation', '')}",
                f"  Confidence: {record.get('confidence', '')}",
                f"  Summary: {record.get('summary', '')}",
            ]
        )

    return "\n".join(lines)
