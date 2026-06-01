import os
import re
from collections import Counter
from pathlib import Path


EMBEDDING_DIMENSION = 128
CHROMA_PATH = Path(os.getenv("CHROMA_DB_PATH", "data/chroma"))


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


class InMemoryVectorStore:
    def __init__(self, documents: list[dict]):
        self.documents = documents

    def similarity_search(self, query: str, limit: int = 5) -> list[dict]:
        ranked_documents = sorted(
            self.documents,
            key=lambda document: _score(query, document),
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
        index = hash(token) % EMBEDDING_DIMENSION
        vector[index] += 1.0

    magnitude = sum(value * value for value in vector) ** 0.5
    if not magnitude:
        return vector

    return [value / magnitude for value in vector]


class ChromaVectorStore:
    def __init__(self, documents: list[dict], collection_name: str = "deepalpha_rag"):
        self.documents = documents
        self.collection_name = _sanitize_collection_name(collection_name)
        self.collection = None
        self.provider = "in_memory"
        self._fallback_store = InMemoryVectorStore(documents)
        self._build_collection()

    def _build_collection(self) -> None:
        try:
            import chromadb
        except ImportError:
            return

        if not self.documents:
            return

        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.provider = "chroma"

        ids = [document.get("id") or str(index) for index, document in enumerate(self.documents)]
        documents = [_document_text(document) for document in self.documents]
        embeddings = [_hash_embedding(text) for text in documents]
        metadatas = [
            {
                "title": document.get("title", ""),
                "url": document.get("url", ""),
            }
            for document in self.documents
        ]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def similarity_search(self, query: str, limit: int = 5) -> list[dict]:
        if self.collection is None:
            return self._fallback_store.similarity_search(query, limit)

        results = self.collection.query(
            query_embeddings=[_hash_embedding(query)],
            n_results=min(limit, len(self.documents)),
        )
        ids = results.get("ids", [[]])[0]
        document_by_id = {
            document.get("id") or str(index): document
            for index, document in enumerate(self.documents)
        }

        return [document_by_id[result_id] for result_id in ids if result_id in document_by_id]


def _sanitize_collection_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_").lower()
    sanitized = sanitized[:50].strip("_-")

    if not sanitized:
        sanitized = "rag"

    collection_name = f"deepalpha_{sanitized}"
    return collection_name[:63].strip("_-")
