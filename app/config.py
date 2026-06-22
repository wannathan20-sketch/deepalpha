import os

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    """Parse feature flags from env vars.
    解析环境变量中的布尔开关，用于控制调试路由、能力开关等运行时行为。
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def debug_routes_enabled() -> bool:
    return _env_bool("ENABLE_DEBUG_ROUTES", True)


def get_cors_allow_origin_regex() -> str:
    return os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"http://(127\.0\.0\.1|localhost):\d+",
    )


def get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_access_code() -> str:
    return os.getenv("DEEPALPHA_ACCESS_CODE", "").strip()


def get_runtime_config() -> dict:
    """Return non-secret runtime capabilities for API/frontend display.
    返回不含密钥的运行时能力信息，供 API 与前端判断当前可用功能。
    """
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    search_provider = os.getenv("SEARCH_PROVIDER", "mock").lower()
    search_providers = os.getenv("SEARCH_PROVIDERS", "")
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    brave_search_api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    blockbeats_api_key = os.getenv("BLOCKBEATS_API_KEY", "")
    rag_embedding_provider = os.getenv("RAG_EMBEDDING_PROVIDER", "hash").lower()
    llm_model = "deepseek-chat" if llm_provider == "deepseek" else openai_model
    llm_enabled = (
        (llm_provider == "openai" and bool(openai_api_key))
        or (llm_provider == "deepseek" and bool(deepseek_api_key))
    )

    return {
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_enabled": llm_enabled,
        "search_provider": search_provider,
        "search_providers": search_providers,
        "search_enabled": (
            (search_provider == "tavily" and bool(tavily_api_key))
            or (search_provider == "brave" and bool(brave_search_api_key))
            or (search_provider == "blockbeats" and bool(blockbeats_api_key))
            or search_provider == "multi"
        ),
        "tavily_enabled": bool(tavily_api_key),
        "brave_search_enabled": bool(brave_search_api_key),
        "blockbeats_enabled": bool(blockbeats_api_key),
        "rag_embedding_provider": rag_embedding_provider,
        "rag_full_text_fetch_enabled": _env_bool("RAG_FETCH_FULL_TEXT", False),
        "rag_chunk_size": get_int_env("RAG_CHUNK_SIZE", 900),
        "rag_chunk_overlap": get_int_env("RAG_CHUNK_OVERLAP", 120),
        "debug_routes_enabled": debug_routes_enabled(),
        "symbol_cache_ttl_seconds": get_int_env("SYMBOL_CACHE_TTL_SECONDS", 86400),
        "market_cache_ttl_seconds": get_int_env("MARKET_CACHE_TTL_SECONDS", 300),
        "financials_cache_ttl_seconds": get_int_env("FINANCIALS_CACHE_TTL_SECONDS", 21600),
        "access_code_required": bool(get_access_code()),
        "financials_rate_limit": get_int_env("FINANCIALS_RATE_LIMIT", 60),
        "report_user_daily_limit": get_int_env("REPORT_USER_DAILY_LIMIT", 3),
        "report_create_rate_limit_per_hour": get_int_env("REPORT_CREATE_RATE_LIMIT_PER_HOUR", 5),
        "report_create_rate_limit_per_day": get_int_env("REPORT_CREATE_RATE_LIMIT_PER_DAY", 10),
        "report_global_daily_limit": get_int_env("REPORT_GLOBAL_DAILY_LIMIT", 50),
    }
