import os
import json

from dotenv import load_dotenv

from app.config import is_production
from app.errors import LLMProviderError


load_dotenv()


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
        "Set LLM_PROVIDER=openai or LLM_PROVIDER=deepseek with an API key to enable real generation."
    )


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
    openai_api_key = os.getenv("OPENAI_API_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    if llm_provider == "openai" and openai_api_key:
        try:
            response_text = _generate_with_openai_compatible(
                prompt=prompt,
                api_key=openai_api_key,
                model=os.getenv("OPENAI_MODEL", "gpt-5"),
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as exc:
            if is_production():
                raise LLMProviderError(f"openai LLM request failed: {exc}") from exc
            return _mock_generate_text(prompt, system_prompt, max_tokens)
        if is_production() and not response_text.strip():
            raise LLMProviderError("openai LLM returned an empty response.")
        return response_text

    if llm_provider == "deepseek" and deepseek_api_key:
        try:
            response_text = _generate_with_openai_compatible(
                prompt=prompt,
                api_key=deepseek_api_key,
                model="deepseek-chat",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as exc:
            if is_production():
                raise LLMProviderError(f"deepseek LLM request failed: {exc}") from exc
            return _mock_generate_text(prompt, system_prompt, max_tokens)
        if is_production() and not response_text.strip():
            raise LLMProviderError("deepseek LLM returned an empty response.")
        return response_text

    if is_production():
        raise LLMProviderError(
            f"Production LLM provider '{llm_provider}' is unavailable or missing credentials."
        )
    return _mock_generate_text(prompt, system_prompt, max_tokens)
