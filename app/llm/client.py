import os
import json

from dotenv import load_dotenv

from app.config import is_production
from app.errors import LLMProviderError


load_dotenv()


# ═══════════════════════════════════════════════════════════════════════
# Mock fallback (development / no provider configured)
# ═══════════════════════════════════════════════════════════════════════

def _mock_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
    """Return a safe fallback when no real model is configured.
    当未配置真实模型或外部调用失败时，返回安全的兜底文本。
    """
    if "Return exactly one JSON object" in system_prompt and "report_citations" in system_prompt:
        return json.dumps(
            {
                "answer": (
                    "开发环境的模型服务当前不可用，无法生成真实追问分析。"
                    "请检查 LLM_PROVIDER 和对应 API Key；生产环境不会使用该 mock 回答。"
                ),
                "key_points": [
                    "已保留报告追问流程，但当前回答不是由真实模型生成。",
                    "配置可用模型服务后，追问会基于报告上下文、最近对话和可选联网证据生成。",
                ],
                "risks": ["当前 mock 回答不能作为投研依据。"],
                "cited_sources": [],
                "report_citations": [],
                "web_citations": [],
                "data_quality_warning": "Development mock LLM response; no real model output was available.",
            },
            ensure_ascii=False,
        )
    return (
        "Mock LLM response. "
        "Set LLM_PROVIDER (openai, deepseek, anthropic, gemini, ollama, dashscope, zhipuai, aihubmix) "
        "with the corresponding API key to enable real generation."
    )


# ═══════════════════════════════════════════════════════════════════════
# OpenAI-compatible generator
# ═══════════════════════════════════════════════════════════════════════

def _generate_with_openai_compatible(
    prompt: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
    system_prompt: str = "",
    max_tokens: int = 800,
    json_mode: bool = False,
) -> str:
    """Call providers that expose an OpenAI-compatible chat completions API.
    调用兼容 OpenAI Chat Completions 协议的模型服务。
    """
    from openai import OpenAI

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    request_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if json_mode:
        request_kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**request_kwargs)
    except Exception as exc:
        if json_mode:
            # Some providers (e.g. older DeepSeek models) may not support
            # response_format; retry without it and rely on prompt instructions.
            # 部分模型（如旧版 DeepSeek）可能不支持 response_format，
            # 此时去掉该参数重试，改由 prompt 约束输出格式。
            request_kwargs.pop("response_format", None)
            try:
                response = client.chat.completions.create(**request_kwargs)
            except Exception:
                raise exc
        else:
            raise

    message = response.choices[0].message
    return message.content or ""


# ═══════════════════════════════════════════════════════════════════════
# Anthropic generator (Messages API, not OpenAI-compatible)
# ═══════════════════════════════════════════════════════════════════════

def _generate_with_anthropic(
    prompt: str,
    api_key: str,
    model: str,
    system_prompt: str = "",
    max_tokens: int = 800,
    json_mode: bool = False,  # noqa: ARG001 — Anthropic handles JSON via prompt instructions
) -> str:
    """Call Anthropic Claude via the Messages API.
    通过 Anthropic Messages API 调用 Claude 模型。
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    messages: list[dict] = []
    messages.append({"role": "user", "content": prompt})

    request_kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system_prompt:
        request_kwargs["system"] = system_prompt

    response = client.messages.create(**request_kwargs)

    # Anthropic returns ContentBlock objects; extract the first text block.
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# ═══════════════════════════════════════════════════════════════════════
# Provider registry
# ═══════════════════════════════════════════════════════════════════════

def _get_provider_config(provider: str) -> dict | None:
    """Look up the API key, model name, base URL, and generator type for a provider.
    根据 provider 名查找对应的配置：API key、模型名、base URL 和生成器类型。
    Returns None if the provider is unknown.
    """
    configs = {
        "openai": {
            "key": os.getenv("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-5"),
            "base_url": None,
            "generator": "openai_compatible",
        },
        "deepseek": {
            "key": os.getenv("DEEPSEEK_API_KEY"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "generator": "openai_compatible",
        },
        "anthropic": {
            "key": os.getenv("ANTHROPIC_API_KEY"),
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "base_url": None,
            "generator": "anthropic",
        },
        "gemini": {
            "key": os.getenv("GEMINI_API_KEY"),
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "generator": "openai_compatible",
        },
        "ollama": {
            "key": "ollama",  # Ollama does not require an API key
            "model": os.getenv("OLLAMA_MODEL", "llama3"),
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "generator": "openai_compatible",
        },
        "dashscope": {
            "key": os.getenv("DASHSCOPE_API_KEY"),
            "model": os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "generator": "openai_compatible",
        },
        "zhipuai": {
            "key": os.getenv("ZHIPUAI_API_KEY"),
            "model": os.getenv("ZHIPUAI_MODEL", "glm-4-flash"),
            "base_url": "https://open.bigmodel.cn/api/paas/v4/",
            "generator": "openai_compatible",
        },
        "aihubmix": {
            "key": os.getenv("AIHUBMIX_API_KEY"),
            "model": os.getenv("AIHUBMIX_MODEL", "deepseek-chat"),
            "base_url": "https://aihubmix.com/v1",
            "generator": "openai_compatible",
        },
    }
    return configs.get(provider)


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def generate_text(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 800,
    json_mode: bool = False,
) -> str:
    """Route generation to the configured provider and degrade gracefully.
    根据环境变量选择模型供应商，并在异常时平滑降级到 mock 输出。
    """
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()

    if llm_provider == "mock":
        if is_production():
            raise LLMProviderError(
                "Production LLM_PROVIDER must be a real provider, not 'mock'."
            )
        return _mock_generate_text(prompt, system_prompt, max_tokens)

    cfg = _get_provider_config(llm_provider)
    if cfg is None:
        if is_production():
            raise LLMProviderError(
                f"Unknown LLM_PROVIDER '{llm_provider}'."
            )
        return _mock_generate_text(prompt, system_prompt, max_tokens)

    if not cfg["key"]:
        if is_production():
            raise LLMProviderError(
                f"Production LLM provider '{llm_provider}' is missing credentials."
            )
        return _mock_generate_text(prompt, system_prompt, max_tokens)

    try:
        if cfg["generator"] == "anthropic":
            response_text = _generate_with_anthropic(
                prompt=prompt,
                api_key=cfg["key"],
                model=cfg["model"],
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        else:
            response_text = _generate_with_openai_compatible(
                prompt=prompt,
                api_key=cfg["key"],
                model=cfg["model"],
                base_url=cfg["base_url"],
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
    except Exception as exc:
        if is_production():
            raise LLMProviderError(f"{llm_provider} LLM request failed: {exc}") from exc
        return _mock_generate_text(prompt, system_prompt, max_tokens)

    if is_production() and not response_text.strip():
        raise LLMProviderError(f"{llm_provider} LLM returned an empty response.")
    return response_text
