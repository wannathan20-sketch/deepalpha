import hashlib
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


EMBEDDING_DIMENSION = 128
CHROMA_PATH = Path(os.getenv("CHROMA_DB_PATH", "data/chroma"))
OFFICIAL_SOURCE_DOMAINS = ("sec.gov", "hkexnews.hk", "hkex.com.hk", "annualreports.com")
MARKET_SOURCE_DOMAINS = ("reuters.com", "bloomberg.com", "wsj.com", "ft.com", "marketwatch.com", "finance.yahoo.com")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text.lower())


def _score(query: str, document: dict) -> float:
    query_terms = Counter(_tokenize(query))
    document_text = " ".join(
        [
            document.get("title", ""),
            document.get("content", ""),
        ]
    )
    document_terms = Counter(_tokenize(document_text))

    if not query_terms or not document_terms:
        return 0.0

    overlap = sum(min(count, document_terms.get(term, 0)) for term, count in query_terms.items())
    return overlap / sum(query_terms.values())


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _source_quality_score(document: dict) -> float:
    domain = document.get("source_domain") or _domain(document.get("url", ""))
    if any(domain.endswith(rule) for rule in OFFICIAL_SOURCE_DOMAINS):
        return 1.0
    if any(domain.endswith(rule) for rule in MARKET_SOURCE_DOMAINS):
        return 0.82
    if domain and domain != "example.com":
        return 0.58
    if domain == "example.com":
        return 0.25
    return 0.1


def _freshness_score(document: dict) -> float:
    value = document.get("published_at") or document.get("retrieved_at")
    if not value:
        return 0.35

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.35

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - parsed).days, 0)
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.75
    if age_days <= 730:
        return 0.45
    return 0.2


def _with_retrieval_metadata(document: dict, query: str, vector_score: float) -> dict:
    keyword_score = _score(query, document)
    source_score = _source_quality_score(document)
    freshness_score = _freshness_score(document)
    retrieval_score = (
        0.58 * max(vector_score, 0.0)
        + 0.24 * keyword_score
        + 0.12 * source_score
        + 0.06 * freshness_score
    )
    source_grade = "A" if source_score >= 0.95 else "B" if source_score >= 0.8 else "C" if source_score >= 0.5 else "D"

    return {
        **document,
        "retrieval_score": round(retrieval_score, 4),
        "keyword_score": round(keyword_score, 4),
        "vector_score": round(max(vector_score, 0.0), 4),
        "source_score": round(source_score, 4),
        "freshness_score": round(freshness_score, 4),
        "source_grade": source_grade,
    }


class InMemoryVectorStore:
    def __init__(self, documents: list[dict]):
        self.documents = documents

    def similarity_search(self, query: str, limit: int = 5) -> list[dict]:
        ranked_documents = sorted(
            (
                _with_retrieval_metadata(document, query, _score(query, document))
                for document in self.documents
            ),
            key=lambda document: document["retrieval_score"],
            reverse=True,
        )
        return ranked_documents[:limit]


def _document_text(document: dict) -> str:
    return " ".join(
        [
            document.get("title", ""),
            document.get("content", ""),
        ]
    )


def _hash_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    tokens = _tokenize(text)

    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % EMBEDDING_DIMENSION
        vector[index] += 1.0

    magnitude = sum(value * value for value in vector) ** 0.5
    if not magnitude:
        return vector

    return [value / magnitude for value in vector]


class HashEmbeddingProvider:
    name = "hash"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _hash_embedding(text)


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _build_embedding_provider():
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", "hash").strip().lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIEmbeddingProvider()
        except Exception:
            return HashEmbeddingProvider()
    return HashEmbeddingProvider()


class ChromaVectorStore:
    def __init__(self, documents: list[dict], collection_name: str = "deepalpha_rag"):
        self.documents = documents
        self.collection_name = _sanitize_collection_name(collection_name)
        self.collection = None
        self.provider = "in_memory"
        self.embedding_provider = _build_embedding_provider()
        self._fallback_store = InMemoryVectorStore(documents)
        self._build_collection()

    def _build_collection(self) -> None:
        try:
            import chromadb
        except ImportError:
            return

        if not self.documents:
            return

        try:
            CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_PATH))
            self.collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self.provider = "chroma"

            ids = [document.get("id") or str(index) for index, document in enumerate(self.documents)]
            documents = [_document_text(document) for document in self.documents]
            try:
                embeddings = self.embedding_provider.embed_documents(documents)
            except Exception:
                self.embedding_provider = HashEmbeddingProvider()
                embeddings = self.embedding_provider.embed_documents(documents)
            metadatas = [
                {
                    "title": document.get("title", ""),
                    "url": document.get("url", ""),
                    "source_domain": document.get("source_domain", ""),
                    "source_type": document.get("source_type", ""),
                    "retrieved_at": document.get("retrieved_at", ""),
                    "published_at": document.get("published_at", ""),
                    "chunk_index": document.get("chunk_index", 0),
                }
                for document in self.documents
            ]

            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception:
            self.collection = None
            self.provider = "in_memory"

    def similarity_search(self, query: str, limit: int = 5) -> list[dict]:
        if self.collection is None:
            return self._fallback_store.similarity_search(query, limit)

        try:
            query_embedding = self.embedding_provider.embed_query(query)
        except Exception:
            return self._fallback_store.similarity_search(query, limit)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(max(limit * 3, limit), len(self.documents)),
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        document_by_id = {
            document.get("id") or str(index): document
            for index, document in enumerate(self.documents)
        }

        candidates = []
        for index, result_id in enumerate(ids):
            if result_id not in document_by_id:
                continue
            distance = distances[index] if index < len(distances) else 1.0
            vector_score = 1.0 - float(distance)
            candidates.append(_with_retrieval_metadata(document_by_id[result_id], query, vector_score))

        return sorted(candidates, key=lambda document: document["retrieval_score"], reverse=True)[:limit]


def _sanitize_collection_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_").lower()
    sanitized = sanitized[:50].strip("_-")

    if not sanitized:
        sanitized = "rag"

    collection_name = f"deepalpha_{sanitized}"
    return collection_name[:63].strip("_-")
