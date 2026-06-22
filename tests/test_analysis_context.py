from datetime import timezone
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import AnalysisContextPack, ContextItem, ContextStatus, DataQuality


def test_analysis_context_pack_defaults_to_version_one() -> None:
    pack = AnalysisContextPack(
        company="NVIDIA",
        market=ContextItem(status=ContextStatus.AVAILABLE, value={"latest_close": 120.0}),
        financials=ContextItem(status=ContextStatus.MISSING),
        rag=ContextItem(status=ContextStatus.FALLBACK),
        data_quality=DataQuality(overall_score=53, level="limited"),
    )

    assert pack.version == "1.0"
    assert pack.created_at.tzinfo == timezone.utc
    assert pack.model_dump(mode="json")["market"]["status"] == "available"


def test_analysis_context_pack_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        AnalysisContextPack(
            version="2.0",
            company="NVIDIA",
            market=ContextItem(status=ContextStatus.MISSING),
            financials=ContextItem(status=ContextStatus.MISSING),
            rag=ContextItem(status=ContextStatus.MISSING),
            data_quality=DataQuality(overall_score=20, level="poor"),
        )
