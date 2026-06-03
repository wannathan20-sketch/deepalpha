from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class RuntimeConfigResponse(BaseModel):
    llm_provider: str
    llm_model: str
    llm_enabled: bool
    search_provider: str
    search_enabled: bool
    debug_routes_enabled: bool


class AnalyzeRequest(BaseModel):
    company_name: str
    thread_id: str | None = None
    symbol: str | None = None
    yahoo_symbol: str | None = None
    exchange: str | None = None
    data_provider: str | None = None


class WatchlistRequest(BaseModel):
    company_name: str
    symbol: str | None = None
    yahoo_symbol: str | None = None
    data_provider: str | None = None


class AnalyzeResponse(BaseModel):
    thread_id: str
    company_name: str
    status: str
    planner_result: dict[str, Any]
    rag_chunks: list[dict[str, Any]]
    agent_outputs: dict[str, Any]
    final_decision: dict[str, Any]
    research_plan: dict[str, Any]
    team_results: dict[str, Any]
    final_report: dict[str, Any]
    markdown_report: str
    report_editor: dict[str, Any]
    market_profile: dict[str, Any]
    financial_profile: dict[str, Any]
    citation_check: dict[str, Any]
    trace: dict[str, Any]


class ReportResponse(BaseModel):
    thread_id: str
    company_name: str
    status: str
    final_report: dict[str, Any]
    markdown_report: str
    report_editor: dict[str, Any]
    source_quality: dict[str, Any]
    citation_check: dict[str, Any]
    trace_summary: dict[str, Any]


class ReportTaskCreateResponse(BaseModel):
    task_id: str
    status: str


class ReportTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
