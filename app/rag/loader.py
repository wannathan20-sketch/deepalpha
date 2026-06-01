from app.tools.search import search_public_info


def load_company_industry_docs(company_name: str) -> list[dict]:
    query = f"{company_name} industry market size competitors regulation"
    search_results = search_public_info(query)

    documents = []
    for index, result in enumerate(search_results):
        documents.append(
            {
                "id": f"{company_name}-industry-{index}",
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("snippet", ""),
                "source": result,
            }
        )

    return documents
