import json
import re
from typing import Any

from pydantic import ValidationError

from app.errors import LLMProviderError
from app.llm import client as llm_client
from app.schemas import ReportChatResponse, ReportChatStrategy


MAX_REPORT_CHARS = 30_000
MAX_PROFILE_CHARS = 8_000
MAX_SOURCE_QUALITY_CHARS = 10_000
URL_PATTERN = re.compile(r"https?://[^\s)\]}>\"']+")

STRATEGY_GUIDANCE: dict[ReportChatStrategy, str] = {
    "general": "Balance the main conclusion, supporting evidence, counterpoints, and uncertainty.",
    "risk": "Prioritize downside risks, triggers, missing evidence, and monitoring indicators.",
    "valuation": "Prioritize valuation assumptions, key variables, and scenario sensitivity. State clearly when valuation data is absent.",
    "technical": "Prioritize trend, moving averages, volatility, and price ranges. Never invent missing market indicators.",
    "news": "Prioritize events already present in the report, their timing, and possible impact. Do not claim knowledge of later news.",
}

SYSTEM_PROMPT = (
    "You answer investment-research follow-up questions using only the supplied report context. "
    "Do not invent facts, sources, current events, prices, or financial metrics. "
    "Do not give trade instructions or claim this is investment advice. "
    "Return exactly one valid JSON object with these fields: answer (string), "
    "key_points (array of strings), risks (array of strings), "
    "cited_sources (array of objects with title and url), and data_quality_warning (string)."
)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n[Context truncated]"


def _bounded_json(value: object, limit: int) -> str:
    return _truncate(
        json.dumps(value or {}, ensure_ascii=False, default=str, sort_keys=True),
        limit,
    )


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
        allowed.setdefault(url.rstrip(".,;，。；"), url.rstrip(".,;，。；"))
    return allowed


def _parse_response(
    raw_response: str,
    *,
    allowed_sources: dict[str, str],
    default_quality_warning: str,
) -> dict[str, Any]:
    if not raw_response.strip():
        raise LLMProviderError("Report chat LLM returned an empty response.")

    try:
        payload = json.loads(raw_response)
        parsed = ReportChatResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise LLMProviderError(f"Report chat LLM returned invalid JSON: {exc}") from exc

    filtered_sources = []
    seen_urls = set()
    for source in parsed.cited_sources:
        if source.url not in allowed_sources or source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        filtered_sources.append(
            {
                "title": source.title.strip() or allowed_sources[source.url],
                "url": source.url,
            }
        )

    result = parsed.model_dump(mode="json")
    result["cited_sources"] = filtered_sources
    if not result["data_quality_warning"].strip():
        result["data_quality_warning"] = default_quality_warning
    return result


def answer_report_question(
    *,
    company_name: str,
    question: str,
    strategy: ReportChatStrategy,
    markdown_report: str,
    market_profile: dict | None = None,
    financial_profile: dict | None = None,
    source_quality: dict | None = None,
    task_context: bool = False,
) -> dict[str, Any]:
    market_profile = market_profile or {}
    financial_profile = financial_profile or {}
    source_quality = source_quality or {}
    context = (
        "{\n"
        f'  "company_name": {json.dumps(company_name, ensure_ascii=False)},\n'
        f'  "markdown_report": {json.dumps(_truncate(markdown_report, MAX_REPORT_CHARS), ensure_ascii=False)},\n'
        f'  "market_profile": {_bounded_json(market_profile, MAX_PROFILE_CHARS)},\n'
        f'  "financial_profile": {_bounded_json(financial_profile, MAX_PROFILE_CHARS)},\n'
        f'  "source_quality": {_bounded_json(source_quality, MAX_SOURCE_QUALITY_CHARS)}\n'
        "}"
    )
    prompt = (
        f"Strategy: {strategy}\n"
        f"Strategy focus: {STRATEGY_GUIDANCE[strategy]}\n"
        f"Question: {question}\n\n"
        f"Report context:\n{context}\n\n"
        "Answer in the same language as the question. Use only evidence in the context. "
        "When evidence is absent, say so explicitly."
    )
    raw_response = llm_client.generate_text(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=1200,
    )
    default_quality_warning = (
        "The answer is limited to the saved report and its captured profiles; later events are not included."
        if task_context
        else "Only the submitted Markdown report was available; structured market and financial profiles were not provided."
    )
    return _parse_response(
        raw_response,
        allowed_sources=_allowed_sources(markdown_report, source_quality),
        default_quality_warning=default_quality_warning,
    )
