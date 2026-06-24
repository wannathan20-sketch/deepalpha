import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.errors import LLMProviderError, SearchProviderError
from app.llm import client as llm_client
from app.schemas import ReportChatResponse, ReportChatSearchMode, ReportChatStrategy
from app.services.report_chat_routing import route_report_question
from app.services.report_sections import parse_report_sections, validate_report_citations
from app.tools.search import search_public_info


MAX_REPORT_CHARS = 30_000
MAX_PROFILE_CHARS = 8_000
MAX_SOURCE_QUALITY_CHARS = 10_000
URL_PATTERN = re.compile(r"https?://[^\s)\]}>\"']+")

STRATEGY_GUIDANCE: dict[ReportChatStrategy, str] = {
    "general": "Balance the main conclusion, supporting evidence, counterpoints, and uncertainty.",
    "risk": "Prioritize downside risks, triggers, missing evidence, and monitoring indicators.",
    "valuation": "Prioritize valuation assumptions, key variables, and scenario sensitivity. State clearly when valuation data is absent.",
    "technical": "Prioritize trend, moving averages, volatility, and price ranges. Never invent missing market indicators.",
    "news": "Prioritize events, timing, and impact. Distinguish saved-report evidence from newly retrieved web evidence.",
}

SYSTEM_PROMPT = (
    "You answer investment-research follow-up questions using only the supplied report context, "
    "conversation, and web evidence. Do not invent facts, sources, prices, or metrics. "
    "Do not give trade instructions or claim this is investment advice. "
    "Return exactly one JSON object with answer, key_points, risks, cited_sources, "
    "report_citations, web_citations, and data_quality_warning. "
    "Report citations must use supplied section_id values and continuous exact excerpts. "
    "Web citations must use supplied URLs."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]}\n[Context truncated]"


def _bounded_json(value: object, limit: int) -> str:
    return _truncate(json.dumps(value or {}, ensure_ascii=False, default=str, sort_keys=True), limit)


def _source_entries(source_quality: object) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            url = str(value.get("url") or value.get("source_url") or "").strip()
            if url.startswith(("http://", "https://")):
                entries.append(
                    {
                        "title": str(value.get("title") or value.get("name") or url).strip(),
                        "url": url,
                    }
                )
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(source_quality)
    return entries


def _allowed_sources(markdown_report: str, source_quality: object) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for entry in _source_entries(source_quality):
        allowed.setdefault(entry["url"], entry["title"])
    for url in URL_PATTERN.findall(markdown_report):
        clean = url.rstrip(".,;，。；")
        allowed.setdefault(clean, clean)
    return allowed


def _compact_history(history: list[dict]) -> list[dict]:
    return [
        {
            "question": turn.get("question", ""),
            "answer": turn.get("answer", ""),
            "key_points": turn.get("key_points", []),
            "risks": turn.get("risks", []),
            "report_citation_ids": [
                citation.get("section_id")
                for citation in turn.get("report_citations", [])
                if citation.get("section_id")
            ],
        }
        for turn in history[-6:]
    ]


def _filter_web_citations(citations: list[dict], results: list[dict]) -> list[dict]:
    by_url = {str(item.get("url") or ""): item for item in results if item.get("url")}
    filtered = []
    seen = set()
    for citation in citations or []:
        url = str(citation.get("url") or "")
        source = by_url.get(url)
        if source is None or url in seen:
            continue
        seen.add(url)
        filtered.append(
            {
                "title": source.get("title") or url,
                "url": url,
                "published_at": source.get("published_at") or "",
                "snippet": source.get("snippet") or "",
            }
        )
    return filtered


def _parse_response(
    raw_response: str,
    *,
    allowed_sources: dict[str, str],
    sections: list[dict],
    web_results: list[dict],
    default_quality_warning: str,
) -> dict[str, Any]:
    if not raw_response.strip():
        raise LLMProviderError("Report chat LLM returned an empty response.")
    try:
        payload = json.loads(raw_response)
        parsed = ReportChatResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise LLMProviderError(f"Report chat LLM returned invalid JSON: {exc}") from exc

    result = parsed.model_dump(mode="json")
    result["cited_sources"] = [
        {"title": source.title.strip() or allowed_sources[source.url], "url": source.url}
        for source in parsed.cited_sources
        if source.url in allowed_sources
    ]
    result["report_citations"] = validate_report_citations(
        result.get("report_citations", []),
        sections,
        allowed_urls=set(allowed_sources),
    )
    result["web_citations"] = _filter_web_citations(
        result.get("web_citations", []),
        web_results,
    )
    if not result["data_quality_warning"].strip():
        result["data_quality_warning"] = default_quality_warning
    return result


def answer_report_question(
    *,
    company_name: str,
    question: str,
    strategy: ReportChatStrategy,
    search_mode: ReportChatSearchMode = "auto",
    markdown_report: str,
    market_profile: dict | None = None,
    financial_profile: dict | None = None,
    source_quality: dict | None = None,
    history: list[dict] | None = None,
    task_context: bool = False,
    report_generated_at: str | None = None,
) -> dict[str, Any]:
    market_profile = market_profile or {}
    financial_profile = financial_profile or {}
    source_quality = source_quality or {}
    history = history or []
    route = route_report_question(question, strategy, search_mode)
    web_results: list[dict] = []
    web_retrieved_at = None
    search_warning = ""
    if route["mode"] == "report_web_qa":
        try:
            web_results = search_public_info(
                f"{company_name} {question} {strategy} latest",
                limit=5,
            )
            route["web_status"] = "success" if web_results else "no_results"
            web_retrieved_at = _utc_now()
            if not web_results:
                search_warning = "Web search returned no usable results; latest information could not be confirmed."
        except SearchProviderError as exc:
            route["web_status"] = "failed"
            search_warning = f"Web search failed; latest information could not be confirmed: {exc}"

    sections = parse_report_sections(markdown_report)
    context = {
        "company_name": company_name,
        "report_sections": [
            {
                "section_id": section["section_id"],
                "title": section["title"],
                "content": section["content"],
                "urls": section["urls"],
            }
            for section in sections
        ],
        "market_profile": market_profile,
        "financial_profile": financial_profile,
        "source_quality": source_quality,
        "recent_conversation": _compact_history(history),
        "web_evidence": web_results,
    }
    prompt = (
        f"Strategy: {strategy}\n"
        f"Strategy focus: {STRATEGY_GUIDANCE[strategy]}\n"
        f"Route: {json.dumps(route, ensure_ascii=False)}\n"
        f"Question: {question}\n\n"
        f"Evidence context:\n{_bounded_json(context, MAX_REPORT_CHARS + MAX_PROFILE_CHARS * 2 + MAX_SOURCE_QUALITY_CHARS)}\n\n"
        "Answer in the same language as the question. Clearly separate saved-report conclusions "
        "from new web evidence and state conflicts or missing evidence."
    )
    raw_response = llm_client.generate_text(prompt=prompt, system_prompt=SYSTEM_PROMPT, max_tokens=1400)
    default_warning = (
        "The answer is limited to the saved report and captured profiles."
        if task_context
        else "Only the submitted Markdown report was available; this conversation is not persisted."
    )
    if search_warning:
        default_warning = f"{default_warning} {search_warning}"
    result = _parse_response(
        raw_response,
        allowed_sources=_allowed_sources(markdown_report, source_quality),
        sections=sections,
        web_results=web_results,
        default_quality_warning=default_warning,
    )
    if search_warning and search_warning not in result["data_quality_warning"]:
        result["data_quality_warning"] = (
            f"{result['data_quality_warning'].strip()} {search_warning}"
        ).strip()
    result["route"] = route
    result["freshness"] = {
        "report_generated_at": report_generated_at,
        "web_retrieved_at": web_retrieved_at,
        "answer_cutoff": web_retrieved_at or report_generated_at,
    }
    return result
