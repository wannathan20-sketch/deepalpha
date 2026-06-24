import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPORT = """# Tesla Report
Overview text.

## 2. 基本面分析
Revenue improved while margins remain under pressure.
Source: https://example.com/filing

## 12. 风控审查
Margin contraction is the primary downside trigger.
"""


def test_parse_report_sections_creates_stable_ids() -> None:
    from app.services.report_sections import parse_report_sections

    sections = parse_report_sections(REPORT)

    assert [section["section_id"] for section in sections] == [
        "report-section-1-tesla-report",
        "report-section-2-2-基本面分析",
        "report-section-3-12-风控审查",
    ]
    assert sections[1]["urls"] == ["https://example.com/filing"]


def test_validate_report_citations_filters_fabricated_evidence() -> None:
    from app.services.report_sections import parse_report_sections, validate_report_citations

    sections = parse_report_sections(REPORT)
    citations = validate_report_citations(
        [
            {
                "section_id": "report-section-2-2-基本面分析",
                "section_title": "ignored",
                "excerpt": "Revenue improved while margins remain under pressure.",
                "url": "https://example.com/filing",
            },
            {
                "section_id": "report-section-3-12-风控审查",
                "section_title": "ignored",
                "excerpt": "Fabricated excerpt.",
                "url": "",
            },
            {
                "section_id": "missing-section",
                "section_title": "ignored",
                "excerpt": "Overview text.",
                "url": "",
            },
        ],
        sections,
        allowed_urls={"https://example.com/filing"},
    )

    assert citations == [
        {
            "section_id": "report-section-2-2-基本面分析",
            "section_title": "2. 基本面分析",
            "excerpt": "Revenue improved while margins remain under pressure.",
            "url": "https://example.com/filing",
        }
    ]
