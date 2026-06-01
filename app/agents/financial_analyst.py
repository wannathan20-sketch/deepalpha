from app.agents.llm_helpers import build_memory_text, structure_agent_result
from app.llm.client import generate_text
from app.tools.search import search_public_info


def _build_context_text(sources: list[dict]) -> str:
    return "\n".join(
        f"- {source.get('title', '')}: {source.get('snippet', '')} ({source.get('url', '')})"
        for source in sources
    )


def analyze(company_name: str, context: dict) -> dict:
    sources = search_public_info(
        f"{company_name} revenue gross margin operating margin net income cash flow financial results"
    )
    context_text = _build_context_text(sources)
    memory_text = build_memory_text(context.get("memory", {}))
    summary = generate_text(
        prompt=(
            f"请基于以下公开信息，为 {company_name} 生成财务分析。\n"
            "必须覆盖：收入趋势、毛利率、经营利润率、净利润、经营现金流、分业务收入或地区结构、资产负债表风险。\n"
            "如果公开信息不足，请明确写出“待补充数据”，不要编造数字。\n"
            "要求：不要使用对话式开头，不要重复来源原文，不要输出 Markdown 装饰符号。\n\n"
            f"{memory_text}\n\n"
            f"{context_text}"
        ),
        system_prompt="你是深研 Alpha 的 Financial Analyst，负责财务报表分析。",
        max_tokens=700,
    )

    return structure_agent_result(
        agent="Financial Analyst",
        summary=summary,
        confidence=0.72,
        sources=sources,
        risks=[
            "公开搜索结果不能替代正式财报，收入、利润率和现金流需以公司披露文件复核。",
            "缺少分业务数据时，无法判断增长质量与利润贡献结构。",
        ],
        watch_items=[
            "收入增速",
            "毛利率",
            "经营利润率",
            "净利润率",
            "经营现金流",
            "分业务收入占比",
        ],
    )
