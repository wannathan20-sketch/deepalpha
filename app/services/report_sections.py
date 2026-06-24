import re


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
URL_PATTERN = re.compile(r"https?://[^\s)\]}>\"']+")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.casefold(), flags=re.UNICODE)
    return normalized.strip("-") or "section"


def section_id(index: int, title: str) -> str:
    return f"report-section-{index}-{_slug(title)}"


def parse_report_sections(markdown_report: str) -> list[dict]:
    sections = []
    current = None
    for line in markdown_report.splitlines():
        match = HEADING_PATTERN.match(line.strip())
        if match:
            if current is not None:
                current["content"] = "\n".join(current.pop("lines")).strip()
                current["urls"] = sorted(
                    {url.rstrip(".,;，。；") for url in URL_PATTERN.findall(current["content"])}
                )
                sections.append(current)
            title = match.group(2).strip()
            current = {
                "section_id": section_id(len(sections) + 1, title),
                "title": title,
                "level": len(match.group(1)),
                "lines": [],
            }
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        current["content"] = "\n".join(current.pop("lines")).strip()
        current["urls"] = sorted(
            {url.rstrip(".,;，。；") for url in URL_PATTERN.findall(current["content"])}
        )
        sections.append(current)
    return sections


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def validate_report_citations(
    citations: list[dict],
    sections: list[dict],
    *,
    allowed_urls: set[str],
) -> list[dict]:
    by_id = {section["section_id"]: section for section in sections}
    valid = []
    for citation in citations or []:
        section = by_id.get(str(citation.get("section_id") or ""))
        excerpt = _normalize(str(citation.get("excerpt") or ""))
        url = str(citation.get("url") or "").strip()
        if section is None or not excerpt:
            continue
        if excerpt not in _normalize(section["content"]):
            continue
        if url and url not in allowed_urls and url not in section["urls"]:
            continue
        valid.append(
            {
                "section_id": section["section_id"],
                "section_title": section["title"],
                "excerpt": excerpt,
                "url": url,
            }
        )
    return valid
