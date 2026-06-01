import os

import requests
from dotenv import load_dotenv


load_dotenv()


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

    return results[:limit]


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
            }
        )

    return results[:limit]


def search_public_info(query: str, limit: int = 5) -> list[dict]:
    search_provider = os.getenv("SEARCH_PROVIDER", "mock").lower()
    tavily_api_key = os.getenv("TAVILY_API_KEY")

    if search_provider == "tavily" and tavily_api_key:
        try:
            return _search_with_tavily(query, tavily_api_key, limit)
        except requests.RequestException as exc:
            print(f"Tavily search failed: {exc}")
            return _mock_search(query, limit)
        except ValueError as exc:
            print(f"Tavily search response parsing failed: {exc}")
            return _mock_search(query, limit)

    return _mock_search(query, limit)
