from app.rag.loader import load_company_industry_docs
from app.rag.vector_store import ChromaVectorStore


def _collection_name(company_name: str) -> str:
    return f"industry_{company_name}"


def retrieve_industry_context(company_name: str, query: str) -> dict:
    documents = load_company_industry_docs(company_name)
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
            }
        )

    return {
        "query": query,
        "vector_store": vector_store.provider,
        "collection_name": vector_store.collection_name,
        "chunks": chunks,
        "sources": sources,
    }
