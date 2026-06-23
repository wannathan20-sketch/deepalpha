from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ContextStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    NOT_SUPPORTED = "not_supported"
    FALLBACK = "fallback"
    STALE = "stale"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    FETCH_FAILED = "fetch_failed"


class ContextItem(BaseModel):
    status: ContextStatus
    value: Any = None
    source: str | None = None
    timestamp: str | None = None
    fallback_from: str | None = None
    missing_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataQuality(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    level: Literal["good", "usable", "limited", "poor"]
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisContextPack(BaseModel):
    version: Literal["1.0"] = "1.0"
    company: str
    market: ContextItem
    financials: ContextItem
    rag: ContextItem
    data_quality: DataQuality
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    """Client request for a full research run.
    客户端发起完整投研分析时提交的请求体。
    """
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


class SymbolResolveBatchRequest(BaseModel):
    items: list[str] = Field(default_factory=list)
    text: str | None = None


class AnalyzeResponse(BaseModel):
    """Full graph response used by the interactive analysis endpoint.
    交互式分析接口返回的完整图执行结果。
    """
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
    analysis_context: AnalysisContextPack
    citation_check: dict[str, Any]
    trace: dict[str, Any]


class ReportResponse(BaseModel):
    """Compact report response for report-focused clients.
    面向报告页面/下载场景的精简响应结构。
    """
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
    steps: list[dict[str, Any]] = Field(default_factory=list)


class ReportTaskStatusResponse(BaseModel):
    """Polling response for background report tasks.
    后台报告任务轮询接口返回的任务状态。
    """
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
