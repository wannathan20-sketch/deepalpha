from datetime import datetime, timezone
from typing import Annotated, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send


def _merge_dict(current: dict, update: dict) -> dict:
    """Reducer: shallow-merge two dicts so parallel branches can contribute."""
    if current is None:
        return update or {}
    if update is None:
        return current or {}
    return {**current, **update}


def _merge_trace(current: dict, update: dict) -> dict:
    """Reducer: concatenate trace step lists from parallel branches.

    Preserves metadata (trace_id, started_at, etc.) from *current* while
    letting *update* override single-value keys (finished_at, duration_seconds).
    """
    if current is None:
        return update or {"steps": []}
    if update is None:
        return current or {"steps": []}
    return {
        **current,
        **update,
        "steps": current.get("steps", []) + update.get("steps", []),
    }

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
from app.trace import add_trace_step, start_trace
from app.utils import safe_run_agent


class DeepAlphaState(TypedDict):
    """Shared LangGraph state passed between research nodes.

    Keys annotated with _merge_dict / _merge_trace use custom reducers so
    parallel Send-based branches can write to the same key without colliding.
    """

    thread_id: str
    company_name: str
    market_profile: dict
    financial_profile: dict
    research_plan: dict
    context: Annotated[dict, _merge_dict]
    rag_chunks: list[dict]
    rag_context: dict
    analysis_context: dict
    team_results: Annotated[dict, _merge_dict]
    final_report: dict
    markdown_report: str
    report_editor_result: dict
    citation_check: dict
    trace: Annotated[dict, _merge_trace]


# ── Parallel fan-out helpers ──────────────────────────────────────────


def _gate(state: DeepAlphaState) -> DeepAlphaState:
    """No-op synchronization gate. Returns empty dict — the framework
    merges upstream state automatically; we just need the barrier."""
    return {}


def _fanout_analysts(state: DeepAlphaState) -> list[Send]:
    """After RAG, run all independent analysts in parallel."""
    return [
        Send("industry", state),
        Send("fundamental", state),
        Send("financial", state),
        Send("valuation", state),
        Send("technical", state),
        Send("news", state),
        Send("sentiment", state),
    ]


def _fanout_debate(state: DeepAlphaState) -> list[Send]:
    """After all analysts complete, run Bull and Bear in parallel."""
    return [Send("bull", state), Send("bear", state)]


def _fanout_review(state: DeepAlphaState) -> list[Send]:
    """After debate completes, run Trader, Risk Manager, and Source Quality in parallel."""
    return [Send("trader", state), Send("risk", state), Send("source_quality", state)]


def _run_agent_node(
    state: DeepAlphaState,
    output_key: str,
    agent_name: str,
    func,
) -> DeepAlphaState:
    """Run a single analyst and merge its result back into state.

    Copies context / team_results before mutation so that parallel
    branches (driven by Send fan-out) do not share mutable references.

    Returns only incremental trace steps — the _merge_trace reducer
    concatenates them across parallel branches.
    """
    context = dict(state["context"])
    team_results = dict(state["team_results"])

    context["agent_outputs"] = dict(team_results)
    result = safe_run_agent(agent_name, func, state["company_name"], context)
    team_results[output_key] = result
    context["agent_outputs"] = dict(team_results)

    # Start fresh — the reducer concatenates so we only emit the new step.
    trace = {"steps": []}
    trace_status = "failed" if result.get("error") else "success"
    add_trace_step(
        trace,
        f"{output_key}_completed",
        trace_status,
        result.get("error", f"{result.get('agent', agent_name)} completed."),
    )

    # Return only modified keys so parallel fan-out doesn't create merge
    # conflicts on immutable fields like thread_id / company_name.
    return {"context": context, "team_results": team_results, "trace": trace}


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
    trace = {"steps": []}
    add_trace_step(trace, "planner_completed", "success", "Research plan created.")

    return {
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
    analysis_context = build_analysis_context(
        state["company_name"],
        market_profile=state.get("market_profile", {}),
        financial_profile=state.get("financial_profile", {}),
        rag_context=rag_context,
    ).model_dump(mode="json")

    context["rag"] = rag_context
    context["analysis_context"] = analysis_context

    # Incremental trace step — reducer concatenates.
    trace_update = {"steps": []}
    add_trace_step(
        trace_update,
        "rag_retriever_completed",
        "success",
        f"Retrieved {len(rag_chunks)} RAG chunks.",
    )

    return {
        "context": context,
        "rag_chunks": rag_chunks,
        "rag_context": rag_context,
        "analysis_context": analysis_context,
        "trace": trace_update,
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
    trace = {"steps": []}
    trace_status = "failed" if result.get("error") else "success"
    add_trace_step(
        trace,
        "committee_completed",
        trace_status,
        result.get("error", "Final report created."),
    )

    return {"final_report": result, "trace": trace}


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
    trace = {"steps": []}
    add_trace_step(trace, "report_generated", "success", "Markdown report generated.")

    return {"markdown_report": markdown_report, "trace": trace}


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
    trace = {"steps": []}
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
    # Emit the final trace update: incremental step + finish metadata.
    # The _merge_trace reducer preserves started_at / trace_id from current
    # and overlays finished_at / duration_seconds from this update.
    now = datetime.now(timezone.utc)
    finished_at = now.isoformat()
    current_trace = state["trace"]
    started_at = datetime.fromisoformat(current_trace["started_at"])
    duration_seconds = round((now - started_at).total_seconds(), 4)

    trace = {
        "steps": [],
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
    }
    add_trace_step(trace, "citation_checked", "success", "Citation check completed.")

    return {"citation_check": citation_check, "trace": trace}


def _build_graph():
    """Compile the hybrid-parallel research workflow.

    Three parallel groups separated by sync gates:
    1. Industry / Fundamental / Financial / Valuation / Technical / News / Sentiment
    2. Bull / Bear (parallel debate)
    3. Trader / Risk / SourceQuality (parallel review)

    Planner → RAG (sequential head) and Committee → Report → Editor → Citation
    (sequential tail) remain serial because they depend on full accumulated context.
    """
    graph = StateGraph(DeepAlphaState)

    # ── All agent nodes ─────────────────────────────────────────────
    graph.add_node("planner", planner_node)
    graph.add_node("rag", rag_node)

    ANALYST_NODES = {
        "industry": industry_node,
        "fundamental": fundamental_node,
        "financial": financial_node,
        "valuation": valuation_node,
        "technical": technical_node,
        "news": news_node,
        "sentiment": sentiment_node,
    }
    for name, func in ANALYST_NODES.items():
        graph.add_node(name, func)

    graph.add_node("bull", bull_node)
    graph.add_node("bear", bear_node)
    graph.add_node("trader", trader_node)
    graph.add_node("risk", risk_node)
    graph.add_node("source_quality", source_quality_node)
    graph.add_node("committee", committee_node)
    graph.add_node("report", report_node)
    graph.add_node("report_editor", report_editor_node)
    graph.add_node("citation", citation_node)

    # ── Synchronization gates ───────────────────────────────────────
    graph.add_node("_debate_gate", _gate)
    graph.add_node("_review_gate", _gate)

    # ── Sequential head ─────────────────────────────────────────────
    graph.set_entry_point("planner")
    graph.add_edge("planner", "rag")

    # ── Group 1: RAG → 7 analysts (parallel) ────────────────────────
    graph.add_conditional_edges(
        "rag", _fanout_analysts, {n: n for n in ANALYST_NODES}
    )
    for name in ANALYST_NODES:
        graph.add_edge(name, "_debate_gate")

    # ── Group 2: Debate gate → Bull + Bear (parallel) ──────────────
    graph.add_conditional_edges(
        "_debate_gate", _fanout_debate, {"bull": "bull", "bear": "bear"}
    )
    graph.add_edge("bull", "_review_gate")
    graph.add_edge("bear", "_review_gate")

    # ── Group 3: Review gate → Trader + Risk + SourceQuality (parallel)
    REVIEW_NODES = {"trader": "trader", "risk": "risk", "source_quality": "source_quality"}
    graph.add_conditional_edges(
        "_review_gate", _fanout_review, REVIEW_NODES
    )
    for name in REVIEW_NODES:
        graph.add_edge(name, "committee")

    # ── Sequential tail ─────────────────────────────────────────────
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
                    # Apply custom reducers for annotated keys so parallel
                    # Send branches accumulate correctly (trace → concat,
                    # context/team_results → shallow merge).
                    for key, value in state_update.items():
                        if key == "trace":
                            final_state[key] = _merge_trace(final_state.get(key), value)
                        elif key in ("context", "team_results"):
                            final_state[key] = _merge_dict(final_state.get(key), value)
                        else:
                            final_state[key] = value
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
