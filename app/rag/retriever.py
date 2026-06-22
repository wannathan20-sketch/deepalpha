from app.rag.loader import load_company_industry_docs
from app.rag.vector_store import ChromaVectorStore
from app.errors import SearchProviderError


def _collection_name(company_name: str) -> str:
    return f"industry_{company_name}"


def retrieve_industry_context(company_name: str, query: str) -> dict:
    try:
        documents = load_company_industry_docs(company_name)
    except SearchProviderError as exc:
        return {
            "query": query,
            "context_status": "fetch_failed",
            "vector_store": "unavailable",
            "embedding_provider": "unavailable",
            "collection_name": _collection_name(company_name),
            "documents_count": 0,
            "chunks": [],
            "sources": [],
            "error": str(exc),
        }
    vector_store = ChromaVectorStore(
        documents,
        collection_name=_collection_name(company_name),
    )
    chunks = vector_store.similarity_search(query)

    sources = []
    for chunk in chunks:
        sources.append(
            {
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "snippet": chunk.get("content", ""),
                "chunk_id": chunk.get("chunk_id") or chunk.get("id", ""),
                "source_provider": chunk.get("source_provider", ""),
                "source_domain": chunk.get("source_domain", ""),
                "source_type": chunk.get("source_type", ""),
                "source_grade": chunk.get("source_grade", ""),
                "retrieval_score": chunk.get("retrieval_score"),
                "published_at": chunk.get("published_at", ""),
                "retrieved_at": chunk.get("retrieved_at", ""),
            }
        )

    return {
        "query": query,
        "vector_store": vector_store.provider,
        "embedding_provider": vector_store.embedding_provider.name,
        "collection_name": vector_store.collection_name,
        "documents_count": len(documents),
        "chunks": chunks,
        "sources": sources,
    }
