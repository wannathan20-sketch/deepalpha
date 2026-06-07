import os

from dotenv import load_dotenv


load_dotenv()


def _mock_generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
    """Return a safe fallback when no real model is configured.
    当未配置真实模型或外部调用失败时，返回安全的兜底文本。
    """
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

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )

    message = response.choices[0].message
    return message.content or ""


def generate_text(prompt: str, system_prompt: str = "", max_tokens: int = 800) -> str:
    """Route generation to the configured provider and degrade gracefully.
    根据环境变量选择模型供应商，并在异常时平滑降级到 mock 输出。
    """
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    if llm_provider == "openai" and openai_api_key:
        try:
            return _generate_with_openai_compatible(
                prompt=prompt,
                api_key=openai_api_key,
                model=os.getenv("OPENAI_MODEL", "gpt-5"),
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
        except Exception:
            return _mock_generate_text(prompt, system_prompt, max_tokens)

    if llm_provider == "deepseek" and deepseek_api_key:
        try:
            return _generate_with_openai_compatible(
                prompt=prompt,
                api_key=deepseek_api_key,
                model="deepseek-chat",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
        except Exception:
            return _mock_generate_text(prompt, system_prompt, max_tokens)

    return _mock_generate_text(prompt, system_prompt, max_tokens)
