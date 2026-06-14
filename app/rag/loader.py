import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from app.config import get_int_env
from app.tools.search import search_public_info


DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _source_type(url: str) -> str:
    domain = _domain(url)
    if domain.endswith("sec.gov"):
        return "regulatory_filing"
    if domain.endswith(("hkexnews.hk", "hkex.com.hk")):
        return "exchange_disclosure"
    if domain.endswith(("finance.yahoo.com", "marketwatch.com")):
        return "market_data"
    if domain.endswith(("reuters.com", "bloomberg.com", "wsj.com", "ft.com")):
        return "news"
    if domain.endswith("example.com"):
        return "mock"
    return "web"


def _fetch_url_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""

    try:
        response = requests.get(
            url,
            timeout=get_int_env("RAG_FETCH_TIMEOUT_SECONDS", 6),
            headers={"User-Agent": os.getenv("SEC_USER_AGENT", "DeepAlpha research prototype")},
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    content_type = response.headers.get("content-type", "")
    text = response.text
    if "html" not in content_type.lower():
        return _normalize_text(text)

    parser = _TextHTMLParser()
    try:
        parser.feed(text)
    except Exception:
        return ""
    return _normalize_text(parser.text())


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(cleaned):
            break
        start = max(end - overlap, start + 1)

    return chunks


def load_company_industry_docs(company_name: str) -> list[dict]:
    query = f"{company_name} industry market size competitors regulation"
    search_results = search_public_info(query)

    documents = []
    for index, result in enumerate(search_results):
        url = result.get("url", "")
        snippet = result.get("snippet", "")
        full_text = ""
        if os.getenv("RAG_FETCH_FULL_TEXT", "false").strip().lower() in {"1", "true", "yes", "on"}:
            full_text = _fetch_url_text(url)

        content = full_text or snippet
        chunks = _chunk_text(
            content,
            chunk_size=get_int_env("RAG_CHUNK_SIZE", DEFAULT_CHUNK_SIZE),
            overlap=get_int_env("RAG_CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP),
        )
        retrieved_at = _utc_now()

        for chunk_index, chunk in enumerate(chunks):
            documents.append(
                {
                    "id": f"{company_name}-industry-{index}-{chunk_index}",
                    "chunk_id": f"{company_name}-industry-{index}-{chunk_index}",
                    "company_name": company_name,
                    "title": result.get("title", ""),
                    "url": url,
                    "content": chunk,
                    "snippet": chunk[:280],
                    "source": result,
                    "source_domain": _domain(url),
                    "source_type": _source_type(url),
                    "retrieved_at": retrieved_at,
                    "published_at": result.get("published_at", ""),
                    "chunk_index": chunk_index,
                    "content_length": len(chunk),
                    "is_full_text": bool(full_text),
                }
            )

    return documents
