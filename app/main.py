import hmac
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import debug_routes_enabled, get_access_code, get_cors_allow_origin_regex, get_int_env, get_runtime_config
from app.graph import run_deepalpha_graph
from app.memory.store import (
    add_to_watchlist,
    get_research_history,
    get_watchlist,
    save_research_history,
)
from app.rag.retriever import retrieve_industry_context
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    ReportTaskCreateResponse,
    ReportTaskStatusResponse,
    ReportResponse,
    RuntimeConfigResponse,
    WatchlistRequest,
)
from app.services.cache import cache
from app.services.financials import build_financial_profile
from app.services.logging import log_event
from app.services.market_summary import build_market_profile
from app.services.rate_limit import rate_limit, rate_limiter
from app.tools.market_data import get_market_chart
from app.tools.symbol_lookup import lookup_symbol


app = FastAPI(title="DeepAlpha", description="Multi-agent virtual investment research team")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=get_cors_allow_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-memory task state is intentionally lightweight for the MVP; use Redis/DB for multi-worker deployments.
# 当前异步任务状态仅保存在进程内，适合 MVP；多进程或生产部署应迁移到 Redis/数据库。
REPORT_TASKS: dict[str, dict] = {}
REPORT_TASKS_LOCK = Lock()


def _check_limit(key: str, *, limit: int, window_seconds: int) -> None:
    if limit > 0:
        rate_limiter.check(key, limit=limit, window_seconds=window_seconds)


def _require_report_access(request: Request) -> str:
    """Validate optional access code and return a stable per-user limit key.
    校验可选访问码，并返回用于用户级限流的稳定标识。
    """
    expected_access_code = get_access_code()
    provided_access_code = request.headers.get("x-deepalpha-access-code", "")
    user_id = request.headers.get("x-deepalpha-user-id", "").strip() or "anonymous"

    if expected_access_code and not hmac.compare_digest(provided_access_code, expected_access_code):
        raise HTTPException(status_code=401, detail="Invalid access code")

    return user_id[:80]


def _enforce_report_generation_limits(request: Request) -> None:
    """Apply layered limits before expensive multi-agent analysis starts.
    在启动高成本多 Agent 分析前，同时应用用户、IP 与全局限流。
    """
    user_id = _require_report_access(request)
    client_host = request.client.host if request.client else "unknown"
    _check_limit(
        f"report_create_user_daily:{user_id}",
        limit=get_int_env("REPORT_USER_DAILY_LIMIT", 3),
        window_seconds=86400,
    )
    _check_limit(
        f"report_create_hourly:{client_host}",
        limit=get_int_env("REPORT_CREATE_RATE_LIMIT_PER_HOUR", 5),
        window_seconds=3600,
    )
    _check_limit(
        f"report_create_daily:{client_host}",
        limit=get_int_env("REPORT_CREATE_RATE_LIMIT_PER_DAY", 10),
        window_seconds=86400,
    )
    _check_limit(
        "report_create_global_daily",
        limit=get_int_env("REPORT_GLOBAL_DAILY_LIMIT", 50),
        window_seconds=86400,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/config", response_model=RuntimeConfigResponse)
def config() -> dict:
    return get_runtime_config()


@app.get("/debug/architecture")
def debug_architecture() -> dict:
    if not debug_routes_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    runtime = get_runtime_config()

    return {
        "project": "DeepAlpha",
        "capabilities": {
            "planner": True,
            "llm": runtime["llm_enabled"],
            "tool_calling": True,
            "langgraph": True,
            "rag": True,
            "memory": True,
            "multi_agent": True,
            "trace": True,
            "citation_checker": True,
        },
        "agents": [
            "Planner",
            "Industry Analyst",
            "Fundamental Analyst",
            "Financial Analyst",
            "Valuation Analyst",
            "Technical Analyst",
            "News Analyst",
            "Sentiment Analyst",
            "Bull Analyst",
            "Bear Analyst",
            "Trader Agent",
            "Risk Manager",
            "Source Quality Agent",
            "Committee",
            "Report Editor",
        ],
        "tools": [
            "Tavily Search",
            f"{runtime['llm_provider']} LLM ({runtime['llm_model']})",
            "Memory Store",
            "RAG Retriever",
            "Chroma Vector Store",
            "SEC EDGAR Companyfacts",
        ],
        "architecture": (
            "Planner -> Industry/Fundamental/Financial/Valuation/News/Technical -> Bull/Bear -> "
            "Trader/Risk -> Source Quality -> Committee -> Report -> Report Editor"
        ),
    }


@app.get("/debug/rag")
def debug_rag(company_name: str) -> dict:
    if not debug_routes_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    query = f"{company_name} industry market size competitors regulation"
    rag_context = retrieve_industry_context(company_name, query)

    return {
        "company_name": company_name,
        "query": rag_context["query"],
        "vector_store": rag_context.get("vector_store", "unknown"),
        "embedding_provider": rag_context.get("embedding_provider", "unknown"),
        "collection_name": rag_context.get("collection_name", ""),
        "documents_count": rag_context.get("documents_count", 0),
        "chunks_count": len(rag_context.get("chunks", [])),
        "chunks": rag_context.get("chunks", []),
        "sources": rag_context.get("sources", []),
    }


@app.get("/symbol/lookup")
def symbol_lookup(query: str, request: Request) -> dict:
    rate_limit(
        request,
        "symbol_lookup",
        limit=get_int_env("SYMBOL_LOOKUP_RATE_LIMIT", 60),
        window_seconds=60,
    )
    # Symbol search is called while users type; cache normalized queries to keep the UI responsive.
    # 符号搜索会在用户输入时频繁触发，按标准化查询缓存以提升响应速度。
    cache_key = f"symbol:{query.strip().lower()}"
    try:
        data, cache_hit = cache.get_or_set(
            cache_key,
            get_int_env("SYMBOL_CACHE_TTL_SECONDS", 86400),
            lambda: lookup_symbol(query),
        )
        result = {**data, "cache_hit": cache_hit}
        log_event("symbol_lookup", query=query, matched=result.get("matched"), cache_hit=cache_hit)
        return result
    except Exception as exc:
        log_event("symbol_lookup_failed", query=query, error=str(exc))
        return {
            "query": query,
            "matched": False,
            "matches": [],
            "candidates": [],
            "needs_confirmation": True,
            "error": str(exc),
            "source": "external_provider",
        }


@app.get("/market/chart")
def market_chart(symbol: str, request: Request, range: str = "6mo", interval: str = "1d", provider: str = "auto") -> dict:
    rate_limit(
        request,
        "market_chart",
        limit=get_int_env("MARKET_CHART_RATE_LIMIT", 120),
        window_seconds=60,
    )
    # Market data has a short TTL so dashboards feel fresh without hammering the provider.
    # 行情数据使用较短 TTL，在保持新鲜度的同时避免过度请求外部数据源。
    cache_key = f"market:{provider.lower()}:{symbol.strip().lower()}:{range}:{interval}"
    try:
        data, cache_hit = cache.get_or_set(
            cache_key,
            get_int_env("MARKET_CACHE_TTL_SECONDS", 300),
            lambda: get_market_chart(symbol, provider, range, interval),
        )
        result = {**data, "cache_hit": cache_hit}
        log_event(
            "market_chart",
            symbol=symbol,
            provider=provider,
            cache_hit=cache_hit,
            points_count=len(result.get("points", [])),
        )
        return result
    except Exception as exc:
        log_event("market_chart_failed", symbol=symbol, provider=provider, error=str(exc))
        return {
            "provider": provider,
            "symbol": symbol,
            "range": range,
            "interval": interval,
            "points": [],
            "error": str(exc),
            "source": "market_chart",
        }


@app.get("/financials/latest")
def financials_latest(symbol: str, request: Request, exchange: str = "") -> dict:
    rate_limit(
        request,
        "financials_latest",
        limit=get_int_env("FINANCIALS_RATE_LIMIT", 60),
        window_seconds=60,
    )
    cache_key = f"financials:sec:{symbol.strip().lower()}:{exchange.strip().lower()}"
    try:
        data, cache_hit = cache.get_or_set(
            cache_key,
            get_int_env("FINANCIALS_CACHE_TTL_SECONDS", 21600),
            lambda: build_financial_profile(symbol, exchange),
        )
        result = {**data, "cache_hit": cache_hit}
        log_event(
            "financials_latest",
            symbol=symbol,
            source=result.get("source"),
            enabled=result.get("enabled"),
            cache_hit=cache_hit,
        )
        return result
    except Exception as exc:
        log_event("financials_latest_failed", symbol=symbol, error=str(exc))
        return {
            "enabled": False,
            "symbol": symbol,
            "source": "sec_companyfacts",
            "reason": str(exc),
            "summary": [f"SEC financial data unavailable: {exc}"],
            "cache_hit": False,
        }


def _build_market_profile_from_request(request: AnalyzeRequest) -> dict:
    try:
        return build_market_profile(
            symbol=request.symbol,
            yahoo_symbol=request.yahoo_symbol,
            exchange=request.exchange,
            provider=request.data_provider,
        )
    except Exception as exc:
        return {
            "enabled": False,
            "context_status": "fetch_failed",
            "fetch_failed": True,
            "reason": str(exc),
            "symbol": request.symbol,
            "yahoo_symbol": request.yahoo_symbol,
            "provider": request.data_provider,
        }


def _build_financial_profile_from_request(request: AnalyzeRequest) -> dict:
    symbol = request.yahoo_symbol or request.symbol
    try:
        return build_financial_profile(symbol, request.exchange)
    except Exception as exc:
        return {
            "enabled": False,
            "context_status": "fetch_failed",
            "fetch_failed": True,
            "reason": str(exc),
            "symbol": symbol,
            "source": "sec_companyfacts",
            "summary": [f"SEC financial data unavailable: {exc}"],
        }


def _run_analysis(request: AnalyzeRequest) -> dict:
    """Assemble external data profiles, then hand off to the research graph.
    先构建外部行情/财报画像，再交给投研图执行完整分析。
    """
    market_profile = _build_market_profile_from_request(request)
    financial_profile = _build_financial_profile_from_request(request)
    return run_deepalpha_graph(request.company_name, request.thread_id, market_profile, financial_profile)


def _build_report_response(result: dict) -> dict:
    """Trim the full graph output into the report endpoint contract.
    将完整图执行结果裁剪为报告接口所需的响应结构。
    """
    trace = result["trace"]
    return {
        "thread_id": result["thread_id"],
        "company_name": result["company_name"],
        "status": result["status"],
        "final_report": result["final_report"],
        "markdown_report": result["markdown_report"],
        "report_editor": result["report_editor"],
        "source_quality": result["team_results"].get("source_quality", {}),
        "citation_check": result["citation_check"],
        "trace_summary": {
            "trace_id": trace["trace_id"],
            "duration_seconds": trace["duration_seconds"],
            "steps_count": len(trace["steps"]),
        },
    }


def _run_report_task(task_id: str, request: AnalyzeRequest) -> None:
    """Background entrypoint for long-running report generation.
    长耗时报告生成的后台任务入口，负责状态流转和历史记录落库。
    """
    log_event("report_task_started", task_id=task_id, company_name=request.company_name)
    with REPORT_TASKS_LOCK:
        REPORT_TASKS[task_id]["status"] = "running"

    try:
        result = _run_analysis(request)
        save_research_history(
            result["company_name"],
            result["thread_id"],
            result["final_report"],
            result["citation_check"],
            symbol=request.symbol,
            yahoo_symbol=request.yahoo_symbol,
            data_provider=request.data_provider,
        )
        payload = _build_report_response(result)
        with REPORT_TASKS_LOCK:
            REPORT_TASKS[task_id].update({"status": "success", "result": payload, "error": None})
        log_event("report_task_completed", task_id=task_id, company_name=result["company_name"])
    except Exception as exc:
        with REPORT_TASKS_LOCK:
            REPORT_TASKS[task_id].update({"status": "failed", "result": None, "error": str(exc)})
        log_event("report_task_failed", task_id=task_id, company_name=request.company_name, error=str(exc))


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, http_request: Request) -> dict:
    _enforce_report_generation_limits(http_request)
    result = _run_analysis(request)
    save_research_history(
        result["company_name"],
        result["thread_id"],
        result["final_report"],
        result["citation_check"],
        symbol=request.symbol,
        yahoo_symbol=request.yahoo_symbol,
        data_provider=request.data_provider,
    )
    return result


@app.post("/report", response_model=ReportResponse)
def report(request: AnalyzeRequest, http_request: Request) -> dict:
    _enforce_report_generation_limits(http_request)
    result = _run_analysis(request)
    save_research_history(
        result["company_name"],
        result["thread_id"],
        result["final_report"],
        result["citation_check"],
        symbol=request.symbol,
        yahoo_symbol=request.yahoo_symbol,
        data_provider=request.data_provider,
    )

    return _build_report_response(result)


@app.post("/report/tasks", response_model=ReportTaskCreateResponse)
def create_report_task(request: AnalyzeRequest, background_tasks: BackgroundTasks, http_request: Request) -> dict:
    _enforce_report_generation_limits(http_request)
    task_id = str(uuid4())
    with REPORT_TASKS_LOCK:
        REPORT_TASKS[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "result": None,
            "error": None,
        }

    background_tasks.add_task(_run_report_task, task_id, request)
    return {"task_id": task_id, "status": "queued"}


@app.get("/report/tasks/{task_id}", response_model=ReportTaskStatusResponse)
def get_report_task(task_id: str) -> dict:
    with REPORT_TASKS_LOCK:
        task = REPORT_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return dict(task)


@app.get("/memory/history")
def memory_history() -> list[dict]:
    return get_research_history()


@app.get("/memory/history/{company_name}")
def memory_history_by_company(company_name: str) -> list[dict]:
    return get_research_history(company_name)


@app.post("/memory/watchlist")
def memory_add_to_watchlist(request: WatchlistRequest) -> dict:
    return add_to_watchlist(
        request.company_name,
        symbol=request.symbol,
        yahoo_symbol=request.yahoo_symbol,
        data_provider=request.data_provider,
    )


@app.get("/memory/watchlist")
def memory_watchlist() -> list[dict]:
    return get_watchlist()
