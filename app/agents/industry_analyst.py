from app.agents.llm_helpers import (
    build_memory_text,
    clean_generated_text,
    extract_key_points,
)
from app.llm.client import generate_text
from app.rag.retriever import retrieve_industry_context


def _build_context_text(chunks: list[dict]) -> str:
    lines = []

    for chunk in chunks:
        lines.append(
            f"- {chunk.get('title', '')}: {chunk.get('content', '')} ({chunk.get('url', '')})"
        )

    return "\n".join(lines)


def analyze(company_name: str, context: dict) -> dict:
    industry_query = f"{company_name} industry market size competitors regulation"
    rag_context = context.get("rag") or retrieve_industry_context(company_name, industry_query)
    context_text = _build_context_text(rag_context.get("chunks", []))
    memory_text = build_memory_text(context.get("memory", {}))
    summary = generate_text(
        prompt=(
            f"请参考以下资料，为 {company_name} 生成行业研究分析。\n"
            "请覆盖行业空间、竞争格局、监管环境、结构性机会和主要风险。\n"
            "不要提及「RAG」「检索」「上下文」「本地」等内部术语，直接给出分析结论。\n\n"
            f"{memory_text}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Industry Analyst，负责行业研究分析。",
        max_tokens=650,
    )
    summary = clean_generated_text(summary)

    return {
        "agent": "Industry Analyst",
        "summary": summary,
        "key_points": extract_key_points(summary),
        "confidence": 0.75,
        "sources": rag_context.get("sources", []),
    }
