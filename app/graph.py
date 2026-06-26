from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from app.agents import (
    bear_analyst,
    bull_analyst,
    committee,
    financial_analyst,
    fundamental_analyst,
    industry_analyst,
    news_analyst,
    planner,
    report_editor,
    risk_manager,
    sentiment_analyst,
    source_quality,
    technical_analyst,
    trader,
    valuation_analyst,
)
from app.memory.store import get_research_history
from app.rag.retriever import retrieve_industry_context
from app.report_generator import generate_markdown_report
from app.services.analysis_context import build_analysis_context
from app.services.citation_checker import check_citations
from app.trace import add_trace_step, finish_trace, start_trace
from app.utils import safe_run_agent


class DeepAlphaState(TypedDict):
    """Shared LangGraph state passed between research nodes.
    LangGraph 各节点之间传递的共享状态，集中保存输入画像、Agent 输出、报告与追踪信息。
    """
    thread_id: str
    company_name: str
    market_profile: dict
    financial_profile: dict
    research_plan: dict
    context: dict
    rag_chunks: list[dict]
    rag_context: dict
    analysis_context: dict
    team_results: dict
    final_report: dict
    markdown_report: str
    report_editor_result: dict
    citation_check: dict
    trace: dict


def _run_agent_node(
    state: DeepAlphaState,
    output_key: str,
    agent_name: str,
    func,
) -> DeepAlphaState:
    """Run a single analyst and merge its structured result back into state.
    执行单个分析 Agent，并把结构化结果合并回全局状态。
    """
    context = state["context"]
    team_results = dict(state["team_results"])
    trace = state["trace"]

    # Downstream agents see previous outputs, which lets bull/bear/risk roles debate accumulated evidence.
    # 下游 Agent 可以读取前序结果，从而基于已积累证据继续辩论与审查。
    context["agent_outputs"] = team_results
    result = safe_run_agent(agent_name, func, state["company_name"], context)
    team_results[output_key] = result
    context["agent_outputs"] = team_results

    trace_status = "failed" if result.get("error") else "success"
    add_trace_step(
        trace,
        f"{output_key}_completed",
        trace_status,
        result.get("error", f"{result.get('agent', agent_name)} completed."),
    )

    return {
        **state,
        "context": context,
        "team_results": team_results,
        "trace": trace,
    }


def planner_node(state: DeepAlphaState) -> DeepAlphaState:
    """Create the research plan and seed context with recent memory.
    生成研究计划，并把近期历史投研记忆注入上下文。
    """
    research_plan = planner.create_plan(
        state["company_name"],
        market_profile=state.get("market_profile"),
        financial_profile=state.get("financial_profile"),
    )
    recent_history = [
        {
            "created_at": record.get("created_at", ""),
            "recommendation": record.get("recommendation", ""),
            "confidence": record.get("confidence", 0),
            "summary": record.get("summary", ""),
        }
        for record in get_research_history(state["company_name"])[:3]
    ]
    context = {
        "company_name": state["company_name"],
        "market_profile": state.get("market_profile", {}),
        "financial_profile": state.get("financial_profile", {}),
        "research_plan": research_plan,
        "agent_outputs": {},
        "memory": {"recent_history": recent_history},
    }
    trace = state["trace"]
    add_trace_step(trace, "planner_completed", "success", "Research plan created.")

    return {
        **state,
        "research_plan": research_plan,
        "context": context,
        "team_results": {},
        "trace": trace,
    }


def fundamental_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "fundamental",
        "fundamental",
        fundamental_analyst.analyze,
    )


def financial_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "financial",
        "financial",
        financial_analyst.analyze,
    )


def valuation_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "valuation",
        "valuation",
        valuation_analyst.analyze,
    )


def industry_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "industry", "industry", industry_analyst.analyze)


def rag_node(state: DeepAlphaState) -> DeepAlphaState:
    """Retrieve industry context before specialist analysts run.
    在专业分析 Agent 执行前检索行业上下文，补足市场规模、竞争和监管背景。
    """
    query = f"{state['company_name']} industry market size competitors regulation"
    rag_context = retrieve_industry_context(state["company_name"], query)
    rag_chunks = rag_context.get("chunks", [])
    context = state["context"]
    trace = state["trace"]
    analysis_context = build_analysis_context(
        state["company_name"],
        market_profile=state.get("market_profile", {}),
        financial_profile=state.get("financial_profile", {}),
        rag_context=rag_context,
    ).model_dump(mode="json")

    context["rag"] = rag_context
    context["analysis_context"] = analysis_context
    add_trace_step(
        trace,
        "rag_retriever_completed",
        "success",
        f"Retrieved {len(rag_chunks)} RAG chunks.",
    )

    return {
        **state,
        "context": context,
        "rag_chunks": rag_chunks,
        "rag_context": rag_context,
        "analysis_context": analysis_context,
        "trace": trace,
    }


def technical_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "technical",
        "technical",
        technical_analyst.analyze,
    )


def news_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "news", "news", news_analyst.analyze)


def sentiment_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "sentiment",
        "sentiment",
        sentiment_analyst.analyze,
    )


def bull_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "bull", "bull", bull_analyst.analyze)


def bear_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "bear", "bear", bear_analyst.analyze)


def trader_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "trader", "trader", trader.analyze)


def risk_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(state, "risk", "risk", risk_manager.analyze)


def source_quality_node(state: DeepAlphaState) -> DeepAlphaState:
    return _run_agent_node(
        state,
        "source_quality",
        "source_quality",
        source_quality.analyze,
    )


def committee_node(state: DeepAlphaState) -> DeepAlphaState:
    """Synthesize analyst outputs into one investment committee decision.
    将各分析 Agent 的结果汇总为投研委员会的综合判断。
    """
    result = safe_run_agent(
        "committee",
        committee.analyze,
        state["company_name"],
        state["context"],
    )
    trace = state["trace"]
    trace_status = "failed" if result.get("error") else "success"
    add_trace_step(
        trace,
        "committee_completed",
        trace_status,
        result.get("error", "Final report created."),
    )

    return {**state, "final_report": result, "trace": trace}


def report_node(state: DeepAlphaState) -> DeepAlphaState:
    """Render structured state into a user-facing markdown report.
    将结构化状态渲染为面向用户的 Markdown 投研报告。
    """
    markdown_report = generate_markdown_report(
        state["company_name"],
        state["research_plan"],
        state["team_results"],
        state["final_report"],
        state["context"].get("memory", {}),
        state["context"].get("market_profile", {}),
        state["context"].get("financial_profile", {}),
    )
    trace = state["trace"]
    add_trace_step(trace, "report_generated", "success", "Markdown report generated.")

    return {**state, "markdown_report": markdown_report, "trace": trace}


def report_editor_node(state: DeepAlphaState) -> DeepAlphaState:
    """Clean and polish the generated report without changing graph evidence.
    清理并润色生成的报告文本，但不改变图中已形成的证据结构。
    """
    result = safe_run_agent(
        "report_editor",
        report_editor.edit_report,
        state["company_name"],
        state["markdown_report"],
    )
    edited_report = result.get("markdown_report", state["markdown_report"])
    trace = state["trace"]
    trace_status = "failed" if result.get("error") else "success"
    edits = result.get("edits", {})
    add_trace_step(
        trace,
        "report_editor_completed",
        trace_status,
        result.get(
            "error",
            (
                "Report edited. "
                f"Removed duplicates: {edits.get('removed_duplicates', 0)}, "
                f"artifacts: {edits.get('removed_artifacts', 0)}."
            ),
        ),
    )

    return {
        **state,
        "markdown_report": edited_report,
        "report_editor_result": result,
        "trace": trace,
    }


def citation_node(state: DeepAlphaState) -> DeepAlphaState:
    """Validate claim/source coverage as the last graph step.
    作为最后一步检查论点与来源覆盖情况，并结束 trace。
    """
    citation_check = check_citations(
        state["team_results"],
        state["rag_chunks"],
    )
    trace = state["trace"]
    add_trace_step(trace, "citation_checked", "success", "Citation check completed.")

    return {**state, "citation_check": citation_check, "trace": finish_trace(trace)}


def _build_graph():
    """Compile the deterministic research workflow.
    编译固定顺序的投研工作流，保证每次报告都经过同一套审查链路。
    """
    graph = StateGraph(DeepAlphaState)

    graph.add_node("planner", planner_node)
    graph.add_node("rag", rag_node)
    graph.add_node("industry", industry_node)
    graph.add_node("fundamental", fundamental_node)
    graph.add_node("financial", financial_node)
    graph.add_node("valuation", valuation_node)
    graph.add_node("technical", technical_node)
    graph.add_node("news", news_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("bull", bull_node)
    graph.add_node("bear", bear_node)
    graph.add_node("trader", trader_node)
    graph.add_node("risk", risk_node)
    graph.add_node("source_quality", source_quality_node)
    graph.add_node("committee", committee_node)
    graph.add_node("report", report_node)
    graph.add_node("report_editor", report_editor_node)
    graph.add_node("citation", citation_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "rag")
    graph.add_edge("rag", "industry")
    graph.add_edge("industry", "fundamental")
    graph.add_edge("fundamental", "financial")
    graph.add_edge("financial", "valuation")
    graph.add_edge("valuation", "technical")
    graph.add_edge("technical", "news")
    graph.add_edge("news", "sentiment")
    graph.add_edge("sentiment", "bull")
    graph.add_edge("bull", "bear")
    graph.add_edge("bear", "trader")
    graph.add_edge("trader", "risk")
    graph.add_edge("risk", "source_quality")
    graph.add_edge("source_quality", "committee")
    graph.add_edge("committee", "report")
    graph.add_edge("report", "report_editor")
    graph.add_edge("report_editor", "citation")
    graph.add_edge("citation", END)

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)


deepalpha_graph = _build_graph()


def run_deepalpha_graph(
    company_name: str,
    thread_id: str | None = None,
    market_profile: dict | None = None,
    financial_profile: dict | None = None,
    progress_callback=None,
) -> dict:
    """Public graph runner used by API endpoints.
    API 入口调用的图执行函数，负责初始化状态、运行工作流并整理响应。
    """
    if thread_id is None:
        thread_id = str(uuid4())

    trace = start_trace(company_name)
    add_trace_step(trace, "request_received", "success", "Analysis request received.")

    initial_state: DeepAlphaState = {
        "thread_id": thread_id,
        "company_name": company_name,
        "market_profile": market_profile or {},
        "financial_profile": financial_profile or {},
        "research_plan": {},
        "context": {},
        "rag_chunks": [],
        "rag_context": {},
        "analysis_context": {},
        "team_results": {},
        "final_report": {},
        "markdown_report": "",
        "report_editor_result": {},
        "citation_check": {},
        "trace": trace,
    }
    graph_config = {"configurable": {"thread_id": thread_id}}
    if progress_callback is None:
        final_state = deepalpha_graph.invoke(initial_state, config=graph_config)
    else:
        final_state = initial_state
        progress_callback("rag_search", "start", "Searching RAG context.")
        agent_analysis_started = False
        report_render_started = False
        for chunk in deepalpha_graph.stream(initial_state, config=graph_config):
            if not isinstance(chunk, dict):
                continue
            for node_name, state_update in chunk.items():
                if isinstance(state_update, dict):
                    final_state = state_update
                if node_name == "rag":
                    progress_callback("rag_search", "finish", "RAG context ready.")
                    progress_callback("agent_analysis", "start", "Running analyst agents.")
                    agent_analysis_started = True
                elif node_name == "committee":
                    if agent_analysis_started:
                        progress_callback("agent_analysis", "finish", "Analyst synthesis complete.")
                    progress_callback("report_render", "start", "Rendering report.")
                    report_render_started = True
                elif node_name == "citation" and report_render_started:
                    progress_callback("report_render", "finish", "Report rendered and checked.")

    return {
        "thread_id": thread_id,
        "company_name": company_name,
        "status": "success",
        "planner_result": final_state["research_plan"],
        "rag_chunks": final_state["rag_chunks"],
        "agent_outputs": final_state["team_results"],
        "final_decision": final_state["final_report"],
        "research_plan": final_state["research_plan"],
        "team_results": final_state["team_results"],
        "final_report": final_state["final_report"],
        "markdown_report": final_state["markdown_report"],
        "report_editor": final_state["report_editor_result"],
        "market_profile": final_state.get("market_profile", {}),
        "financial_profile": final_state.get("financial_profile", {}),
        "analysis_context": final_state.get("analysis_context", {}),
        "citation_check": final_state["citation_check"],
        "trace": final_state["trace"],
    }
