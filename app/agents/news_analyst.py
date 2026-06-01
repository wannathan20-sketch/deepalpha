import re

from app.agents.llm_helpers import build_memory_text, structure_agent_result
from app.llm.client import generate_text
from app.tools.search import search_public_info


PLACEHOLDER_ANALYSIS = "该模块当前为占位分析，后续可接入真实数据源。"


def _build_context_text(sources: list[dict]) -> str:
    return "\n".join(
        f"- {source.get('title', '')}: {source.get('snippet', '')} ({source.get('url', '')})"
        for source in sources
    )


def _clean_text(text: str) -> str:
    return PLACEHOLDER_ANALYSIS if "mock" in text.lower() else text.strip()


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

        if point and "mock" not in point.lower():
            points.append(point)

        if len(points) >= max_points:
            return points

    sentences = re.split(r"[。！？.!?]\s*", text)
    for sentence in sentences:
        point = sentence.strip()
        if point and "mock" not in point.lower():
            points.append(point[:120])

        if len(points) >= max_points:
            return points

    return [PLACEHOLDER_ANALYSIS]


def analyze(company_name: str, context: dict) -> dict:
    sources = search_public_info(f"{company_name} recent news funding earnings")
    context_text = _build_context_text(sources)
    memory_text = build_memory_text(context.get("memory", {}))
    summary = generate_text(
        prompt=(
            f"请基于以下公开信息，生成 {company_name} 的新闻事件分析摘要，并用要点列出关键事件。\n"
            "要求：\n"
            "- 不要使用“好的”“作为某某分析师”等对话式开头。\n"
            "- 区分已发生事件、市场预期和需要复核的信息。\n"
            "- 不要输出 Markdown 装饰符号。\n"
            "- 每个事件应说明潜在影响方向和仍需验证的数据。\n\n"
            f"{memory_text}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 News Analyst，负责新闻事件分析。",
        max_tokens=500,
    )
    summary = _clean_text(summary)

    return structure_agent_result(
        agent="News Analyst",
        summary=summary,
        confidence=0.8,
        sources=sources,
        risks=["新闻事件可能存在时效滞后，需以公司公告和交易所披露复核。"],
        watch_items=["最新财报发布日期", "业绩会指引", "重大监管或竞争事件", "股价对新闻的反应"],
    )
