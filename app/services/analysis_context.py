from app.schemas import AnalysisContextPack, ContextItem, ContextStatus, DataQuality


STATUS_SCORES = {
    ContextStatus.AVAILABLE: 100,
    ContextStatus.PARTIAL: 70,
    ContextStatus.ESTIMATED: 65,
    ContextStatus.STALE: 55,
    ContextStatus.FALLBACK: 40,
    ContextStatus.NOT_SUPPORTED: 30,
    ContextStatus.MISSING: 20,
    ContextStatus.FETCH_FAILED: 0,
}


def _status_from_hint(value: object) -> ContextStatus | None:
    try:
        return ContextStatus(str(value))
    except ValueError:
        return None


def _profile_item(profile: object, *, source_key: str) -> ContextItem:
    if not isinstance(profile, dict) or not profile:
        return ContextItem(status=ContextStatus.MISSING, missing_reason="No profile data available.")

    status = _status_from_hint(profile.get("context_status"))
    if status is None:
        if profile.get("fetch_failed") or profile.get("error"):
            status = ContextStatus.FETCH_FAILED
        elif profile.get("fallback"):
            status = ContextStatus.FALLBACK
        elif profile.get("enabled") is True:
            status = ContextStatus.AVAILABLE
        else:
            status = ContextStatus.MISSING

    reason = str(profile.get("reason") or profile.get("error") or "").strip() or None
    return ContextItem(
        status=status,
        value=profile,
        source=str(profile.get(source_key) or "").strip() or None,
        timestamp=str(profile.get("report_date") or profile.get("filing_date") or "").strip() or None,
        fallback_from=str(profile.get("fallback_from") or "").strip() or None,
        missing_reason=reason if status != ContextStatus.AVAILABLE else None,
        warnings=[str(item) for item in profile.get("warnings", []) if str(item).strip()],
    )


def _rag_item(rag_context: object) -> ContextItem:
    if not isinstance(rag_context, dict):
        return ContextItem(status=ContextStatus.MISSING, missing_reason="No RAG context available.")

    chunks = rag_context.get("chunks", [])
    if not isinstance(chunks, list) or not chunks:
        status = ContextStatus.FETCH_FAILED if rag_context.get("error") else ContextStatus.MISSING
        return ContextItem(
            status=status,
            value=rag_context,
            source=str(rag_context.get("vector_store") or "").strip() or None,
            missing_reason=str(rag_context.get("error") or "No RAG chunks available."),
        )

    mock_flags = [
        str(chunk.get("source_type", "")).lower() == "mock"
        or str(chunk.get("source_provider", "")).lower() == "mock"
        for chunk in chunks
        if isinstance(chunk, dict)
    ]
    if mock_flags and all(mock_flags):
        status = ContextStatus.FALLBACK
    elif any(mock_flags):
        status = ContextStatus.PARTIAL
    else:
        status = ContextStatus.AVAILABLE

    first_timestamp = next(
        (
            str(chunk.get("retrieved_at"))
            for chunk in chunks
            if isinstance(chunk, dict) and chunk.get("retrieved_at")
        ),
        None,
    )
    return ContextItem(
        status=status,
        value=rag_context,
        source=str(rag_context.get("vector_store") or "").strip() or None,
        timestamp=first_timestamp,
        fallback_from="real_search" if status == ContextStatus.FALLBACK else None,
        warnings=(
            ["RAG context contains fallback data."]
            if status in {ContextStatus.FALLBACK, ContextStatus.PARTIAL}
            else []
        ),
    )


def _build_quality(items: dict[str, ContextItem]) -> DataQuality:
    score = round(sum(STATUS_SCORES[item.status] for item in items.values()) / len(items))
    if score >= 85:
        level = "good"
    elif score >= 60:
        level = "usable"
    elif score >= 35:
        level = "limited"
    else:
        level = "poor"

    limitations = [
        f"{name}: {item.status.value}"
        for name, item in items.items()
        if item.status != ContextStatus.AVAILABLE
    ]
    warnings = [warning for item in items.values() for warning in item.warnings]
    return DataQuality(
        overall_score=score,
        level=level,
        limitations=limitations,
        warnings=warnings,
    )


def build_analysis_context(
    company: str,
    *,
    market_profile: object,
    financial_profile: object,
    rag_context: object,
) -> AnalysisContextPack:
    items = {
        "market": _profile_item(market_profile, source_key="provider"),
        "financials": _profile_item(financial_profile, source_key="source"),
        "rag": _rag_item(rag_context),
    }
    return AnalysisContextPack(
        company=company,
        market=items["market"],
        financials=items["financials"],
        rag=items["rag"],
        data_quality=_build_quality(items),
    )
