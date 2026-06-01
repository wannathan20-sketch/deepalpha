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
from app.services.citation_checker import check_citations
from app.trace import add_trace_step, finish_trace, start_trace
from app.utils import safe_run_agent


class DeepAlphaState(TypedDict):
    thread_id: str
    company_name: str
    market_profile: dict
    research_plan: dict
    context: dict
    rag_chunks: list[dict]
    rag_context: dict
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
    context = state["context"]
    team_results = dict(state["team_results"])
    trace = state["trace"]

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
    research_plan = planner.create_plan(state["company_name"])
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
    query = f"{state['company_name']} industry market size competitors regulation"
    rag_context = retrieve_industry_context(state["company_name"], query)
    rag_chunks = rag_context.get("chunks", [])
    context = state["context"]
    trace = state["trace"]

    context["rag"] = rag_context
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
    markdown_report = generate_markdown_report(
        state["company_name"],
        state["research_plan"],
        state["team_results"],
        state["final_report"],
        state["context"].get("memory", {}),
        state["context"].get("market_profile", {}),
    )
    trace = state["trace"]
    add_trace_step(trace, "report_generated", "success", "Markdown report generated.")

    return {**state, "markdown_report": markdown_report, "trace": trace}


def report_editor_node(state: DeepAlphaState) -> DeepAlphaState:
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
    citation_check = check_citations(
        state["team_results"],
        state["rag_chunks"],
    )
    trace = state["trace"]
    add_trace_step(trace, "citation_checked", "success", "Citation check completed.")

    return {**state, "citation_check": citation_check, "trace": finish_trace(trace)}


def _build_graph():
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
) -> dict:
    if thread_id is None:
        thread_id = str(uuid4())

    trace = start_trace(company_name)
    add_trace_step(trace, "request_received", "success", "Analysis request received.")

    initial_state: DeepAlphaState = {
        "thread_id": thread_id,
        "company_name": company_name,
        "market_profile": market_profile or {},
        "research_plan": {},
        "context": {},
        "rag_chunks": [],
        "rag_context": {},
        "team_results": {},
        "final_report": {},
        "markdown_report": "",
        "report_editor_result": {},
        "citation_check": {},
        "trace": trace,
    }
    final_state = deepalpha_graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
    )

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
        "citation_check": final_state["citation_check"],
        "trace": final_state["trace"],
    }
