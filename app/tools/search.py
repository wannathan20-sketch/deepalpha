import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv

from app.config import is_production
from app.errors import SearchProviderError


load_dotenv()


DEFAULT_TIMEOUT_SECONDS = 10


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _strip_html(text: str) -> str:
    parser = _TextHTMLParser()
    try:
        parser.feed(text or "")
    except Exception:
        return _normalize_text(re.sub(r"<[^>]+>", " ", text or ""))
    return _normalize_text(parser.text())


def _with_provider(result: dict, provider: str) -> dict:
    return {**result, "provider": provider}


def _dedupe_results(results: list[dict], limit: int) -> list[dict]:
    deduped = []
    seen = set()
    for result in results:
        key = (result.get("url") or result.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def _mock_search(query: str, limit: int = 5) -> list[dict]:
    results = [
        {
            "title": f"Mock public information for {query}",
            "url": "https://example.com/mock-public-info",
            "snippet": f"Mock snippet about {query}.",
        },
        {
            "title": f"Mock market context for {query}",
            "url": "https://example.com/mock-market-context",
            "snippet": f"Additional mock context related to {query}.",
        },
    ]

    return [_with_provider(result, "mock") for result in results[:limit]]


def _search_with_tavily(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": limit,
            "search_depth": "basic",
        },
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    results = []

    for item in data.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "published_at": item.get("published_date", "") or item.get("publishedDate", ""),
                "provider": "tavily",
            }
        )

    return results[:limit]


def _search_with_brave(query: str, api_key: str, limit: int = 5) -> list[dict]:
    params = {
        "q": query,
        "count": min(limit, 20),
        "extra_snippets": "true",
        "freshness": os.getenv("BRAVE_SEARCH_FRESHNESS", ""),
        "country": os.getenv("BRAVE_SEARCH_COUNTRY", "US"),
        "search_lang": os.getenv("BRAVE_SEARCH_LANG", "en"),
    }
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        params={key: value for key, value in params.items() if value != ""},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        snippets = [item.get("description", "")]
        snippets.extend(item.get("extra_snippets", []) or [])
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": _normalize_text(" ".join(snippets)),
                "published_at": item.get("age", ""),
                "provider": "brave",
            }
        )

    return results[:limit]


def _search_with_blockbeats(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.get(
        "https://api-pro.theblockbeats.info/v1/search",
        headers={"api-key": api_key},
        params={
            "name": query,
            "page": 1,
            "size": min(limit, 100),
            "lang": os.getenv("BLOCKBEATS_LANG", "cn"),
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("data", {}).get("data", [])
    results = []
    for item in items:
        snippet = item.get("content") or item.get("abstract") or ""
        url = item.get("link") or item.get("url") or ""
        results.append(
            {
                "title": item.get("title", ""),
                "url": url,
                "snippet": _strip_html(snippet),
                "published_at": item.get("create_time", ""),
                "provider": "blockbeats",
            }
        )

    return results[:limit]


def _search_with_serpapi(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": os.getenv("SERPAPI_ENGINE", "google"),
            "q": query,
            "api_key": api_key,
            "num": limit,
            "hl": os.getenv("SERPAPI_HL", "zh-cn"),
            "gl": os.getenv("SERPAPI_GL", "cn"),
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    results = []
    for item in data.get("organic_results", []):
        snippet_parts = [
            item.get("snippet", ""),
            " ".join(item.get("snippet_highlighted_words", []) or []),
        ]
        rich_snippet = item.get("rich_snippet") or {}
        if isinstance(rich_snippet, dict):
            for section in rich_snippet.values():
                if not isinstance(section, dict):
                    continue
                extensions = section.get("extensions")
                if isinstance(extensions, list):
                    snippet_parts.extend(str(value) for value in extensions)
                detected = section.get("detected_extensions")
                if isinstance(detected, dict):
                    snippet_parts.extend(f"{key}: {value}" for key, value in detected.items())
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link") or item.get("url") or "",
                "snippet": _normalize_text(" ".join(snippet_parts)),
                "published_at": item.get("date", ""),
                "provider": "serpapi",
            }
        )

    return results[:limit]


def _search_with_bocha(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.post(
        "https://api.bocha.cn/v1/web-search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "freshness": os.getenv("BOCHA_FRESHNESS", "oneWeek"),
            "summary": True,
            "count": min(limit, 50),
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("code") not in {None, 200}:
        raise ValueError(str(data.get("msg") or f"Bocha API returned code {data.get('code')}"))

    value_list = data.get("data", {}).get("webPages", {}).get("value", [])
    results = []
    for item in value_list:
        results.append(
            {
                "title": item.get("name") or item.get("title") or "",
                "url": item.get("url", ""),
                "snippet": _normalize_text(item.get("summary") or item.get("snippet") or ""),
                "published_at": item.get("datePublished", ""),
                "provider": "bocha",
            }
        )

    return results[:limit]


def _search_with_searxng(query: str, base_url: str, limit: int = 5) -> list[dict]:
    search_url = f"{base_url.rstrip('/')}/search"
    response = requests.get(
        search_url,
        params={
            "q": query,
            "format": "json",
            "language": os.getenv("SEARXNG_LANGUAGE", "auto"),
            "time_range": os.getenv("SEARXNG_TIME_RANGE", ""),
            "safesearch": os.getenv("SEARXNG_SAFESEARCH", "0"),
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    results = []
    for item in data.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": _normalize_text(item.get("content") or item.get("description") or ""),
                "published_at": item.get("publishedDate") or item.get("published_at") or "",
                "provider": "searxng",
            }
        )

    return results[:limit]


def _search_with_x_mcp(query: str, search_url: str, limit: int = 5) -> list[dict]:
    headers = {"Accept": "application/json"}
    api_key = os.getenv("X_MCP_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        search_url,
        headers=headers,
        json={"query": query, "limit": limit},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("results") or data.get("tweets") or data.get("data") or []
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("content") or item.get("snippet") or ""
        author = item.get("author") or item.get("username") or item.get("user") or ""
        title = item.get("title") or f"X: {author or query}"
        results.append(
            {
                "title": title,
                "url": item.get("url") or item.get("link") or "",
                "snippet": _normalize_text(text),
                "published_at": item.get("created_at") or item.get("published_at") or item.get("date") or "",
                "provider": "x",
                "source_type": "social",
            }
        )

    return results[:limit]


def _configured_providers() -> list[str]:
    provider_value = os.getenv("SEARCH_PROVIDER", "mock").lower()
    if provider_value == "multi":
        provider_value = os.getenv("SEARCH_PROVIDERS", "brave,blockbeats,tavily")
    providers = [provider.strip().lower() for provider in provider_value.split(",") if provider.strip()]
    return providers or ["mock"]


def _search_provider(search_provider: str, query: str, limit: int) -> list[dict]:
    if search_provider == "mock":
        return _mock_search(query, limit)
    if search_provider == "tavily" and os.getenv("TAVILY_API_KEY"):
        return _search_with_tavily(query, os.getenv("TAVILY_API_KEY", ""), limit)
    if search_provider == "brave" and os.getenv("BRAVE_SEARCH_API_KEY"):
        return _search_with_brave(query, os.getenv("BRAVE_SEARCH_API_KEY", ""), limit)
    if search_provider == "blockbeats" and os.getenv("BLOCKBEATS_API_KEY"):
        return _search_with_blockbeats(query, os.getenv("BLOCKBEATS_API_KEY", ""), limit)
    if search_provider == "serpapi" and os.getenv("SERPAPI_API_KEY"):
        return _search_with_serpapi(query, os.getenv("SERPAPI_API_KEY", ""), limit)
    if search_provider == "bocha" and os.getenv("BOCHA_API_KEY"):
        return _search_with_bocha(query, os.getenv("BOCHA_API_KEY", ""), limit)
    if search_provider == "searxng" and os.getenv("SEARXNG_BASE_URL"):
        return _search_with_searxng(query, os.getenv("SEARXNG_BASE_URL", ""), limit)
    if search_provider == "x" and os.getenv("X_MCP_SEARCH_URL"):
        return _search_with_x_mcp(query, os.getenv("X_MCP_SEARCH_URL", ""), limit)
    return []


def _rank_by_provider_order(results_by_provider: dict[str, list[dict]], providers: list[str], limit: int) -> list[dict]:
    ranked = []
    max_items = max((len(results) for results in results_by_provider.values()), default=0)
    for item_index in range(max_items):
        for provider in providers:
            provider_results = results_by_provider.get(provider, [])
            if item_index < len(provider_results):
                ranked.append(provider_results[item_index])
    return _dedupe_results(ranked, limit)


def search_public_info(query: str, limit: int = 5) -> list[dict]:
    providers = _configured_providers()
    if is_production() and "mock" in providers:
        raise SearchProviderError("Production search cannot use the mock provider.")

    if len(providers) == 1:
        failure_reason = f"{providers[0]} search returned no results."
        try:
            results = _dedupe_results(_search_provider(providers[0], query, limit), limit)
            if results:
                return results
        except requests.RequestException as exc:
            print(f"{providers[0]} search failed: {exc}")
            failure_reason = f"{providers[0]} search failed: {exc}"
        except ValueError as exc:
            print(f"{providers[0]} search response parsing failed: {exc}")
            failure_reason = f"{providers[0]} search response parsing failed: {exc}"
        if is_production():
            raise SearchProviderError(failure_reason)
        return _mock_search(query, limit)

    results_by_provider: dict[str, list[dict]] = {}
    max_workers = min(len(providers), int(os.getenv("SEARCH_MAX_WORKERS", "4")))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_provider = {
            executor.submit(_search_provider, provider, query, limit): provider
            for provider in providers
        }
        for future in as_completed(future_to_provider):
            provider = future_to_provider[future]
            try:
                provider_results = future.result()
            except requests.RequestException as exc:
                print(f"{provider} search failed: {exc}")
                continue
            except ValueError as exc:
                print(f"{provider} search response parsing failed: {exc}")
                continue
            if provider_results:
                results_by_provider[provider] = provider_results

    ranked_results = _rank_by_provider_order(results_by_provider, providers, limit)
    if ranked_results:
        return ranked_results
    if is_production():
        raise SearchProviderError(
            f"All configured search providers failed or returned no results: {', '.join(providers)}."
        )
    return _mock_search(query, limit)
