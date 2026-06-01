import re


CONVERSATIONAL_PREFIXES = (
    r"^好的[，,。.\s]*",
    r"^当然[，,。.\s]*",
    r"^以下是[，,。.\s]*",
    r"^作为[^，,。]{2,40}[，,。]\s*",
)

PROFESSIONAL_REPLACEMENTS = {
    "暂无 summary。": "暂无可用摘要。",
    "暂无 summary": "暂无可用摘要",
    "N/A": "待补充",
    "mock": "待验证",
    "placeholder": "待验证",
}


def _normalize_for_duplicate(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    normalized = normalized.strip("#-*•_`>：:，,。.；;（）()[]【】")
    return normalized.lower()


def _clean_heading(line: str) -> str:
    match = re.match(r"^(#{1,6})\s*(.+)$", line)
    if not match:
        return line

    hashes, title = match.groups()
    title = re.sub(r"^\*{1,2}(.+?)\*{1,2}$", r"\1", title.strip())
    title = title.replace("**", "").replace("__", "").replace("*", "").strip()
    return f"{hashes} {title}"


def _clean_body_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""

    for pattern in CONVERSATIONAL_PREFIXES:
        text = re.sub(pattern, "", text)

    for source, target in PROFESSIONAL_REPLACEMENTS.items():
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)

    text = re.sub(r"`{3,}", "", text)
    text = re.sub(r"^\s*>+\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = text.replace("•", "-")
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _is_divider_or_artifact(line: str) -> bool:
    stripped = line.strip()
    return stripped in {"---", "***", "___", "```"} or bool(
        re.fullmatch(r"[-_*#`\s]{4,}", stripped)
    )


def _append_line(lines: list[str], line: str) -> None:
    if line == "" and (not lines or lines[-1] == ""):
        return
    lines.append(line)


def edit_report(company_name: str, markdown_report: str) -> dict:
    edited_lines: list[str] = []
    seen_blocks: set[str] = set()
    removed_duplicates = 0
    removed_artifacts = 0
    cleaned_lines = 0

    for raw_line in markdown_report.splitlines():
        if _is_divider_or_artifact(raw_line):
            removed_artifacts += 1
            continue

        stripped = raw_line.strip()
        if not stripped:
            _append_line(edited_lines, "")
            continue

        if stripped.startswith("#"):
            cleaned = _clean_heading(stripped)
        else:
            cleaned = _clean_body_line(stripped)

        if not cleaned:
            removed_artifacts += 1
            continue

        duplicate_key = _normalize_for_duplicate(cleaned)
        is_structural = cleaned.startswith("#") or cleaned in {"核心判断：", "主要风险：", "后续跟踪指标：", "Sources:"}
        if duplicate_key and not is_structural:
            if duplicate_key in seen_blocks:
                removed_duplicates += 1
                continue
            seen_blocks.add(duplicate_key)

        if cleaned != stripped:
            cleaned_lines += 1

        _append_line(edited_lines, cleaned)

    edited_report = "\n".join(edited_lines).strip() + "\n"

    return {
        "agent": "Report Editor",
        "summary": f"{company_name} 报告已完成结构化编辑与 PDF 前清洗。",
        "edits": {
            "removed_duplicates": removed_duplicates,
            "removed_artifacts": removed_artifacts,
            "cleaned_lines": cleaned_lines,
        },
        "markdown_report": edited_report,
        "confidence": 0.86,
    }
