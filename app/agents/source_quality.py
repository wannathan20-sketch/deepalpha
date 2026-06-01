from urllib.parse import urlparse

from app.agents.llm_helpers import build_claims, build_data_quality


GRADE_RULES = {
    "A": ("sec.gov", "hkexnews.hk", "hkex.com.hk", "annualreports.com"),
    "B": ("reuters.com", "bloomberg.com", "wsj.com", "ft.com", "marketwatch.com", "finance.yahoo.com"),
    "C": ("wikipedia.org", "google.com", "bing.com"),
}


def _source_key(source: dict) -> str:
    return str(source.get("url") or source.get("title") or "").strip()


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _grade_source(source: dict) -> tuple[str, str]:
    url = str(source.get("url", "")).strip()
    domain = _domain(url)

    if not urlparse(url).scheme in {"http", "https"}:
        return "D", "缺少可访问链接，不能作为客户级引用。"

    for grade, domains in GRADE_RULES.items():
        if any(domain.endswith(rule) for rule in domains):
            if grade == "A":
                return grade, "官方披露、交易所或监管来源，可信度较高。"
            if grade == "B":
                return grade, "主流财经或市场数据来源，可用于辅助验证。"
            return grade, "开放网络来源，仅适合作为背景信息。"

    return "C", "一般公开网页来源，需要用公告、财报或权威媒体复核。"


def _collect_sources(agent_outputs: dict) -> list[dict]:
    sources = []
    seen = set()

    for agent_name, output in agent_outputs.items():
        for source in output.get("sources", []):
            key = _source_key(source)
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append({**source, "agent": agent_name})

    return sources


def analyze(company_name: str, context: dict) -> dict:
    sources = _collect_sources(context.get("agent_outputs", {}))
    ratings = []
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}

    for source in sources:
        grade, reason = _grade_source(source)
        grade_counts[grade] += 1
        ratings.append(
            {
                "title": source.get("title", "Untitled"),
                "url": source.get("url", ""),
                "agent": source.get("agent", ""),
                "grade": grade,
                "reason": reason,
            }
        )

    if sources:
        summary = (
            f"{company_name} 本次报告共识别 {len(sources)} 条去重来源。"
            f"A/B/C/D 分布为 {grade_counts['A']}/{grade_counts['B']}/{grade_counts['C']}/{grade_counts['D']}。"
            "客户级交付应优先补充公司公告、交易所披露、正式财报和权威财经媒体。"
        )
    else:
        summary = f"{company_name} 本次报告缺少可评级来源，当前结论只能作为内部研究草稿。"

    warnings = []
    if grade_counts["A"] == 0:
        warnings.append("缺少 A 级官方或监管披露来源。")
    if grade_counts["D"]:
        warnings.append("存在 D 级来源，需要移除或补充可访问链接。")

    key_points = [
        f"来源总数：{len(sources)}",
        f"A/B/C/D 来源分布：{grade_counts['A']}/{grade_counts['B']}/{grade_counts['C']}/{grade_counts['D']}",
        "客户级报告需优先使用公告、财报、交易所披露和权威财经媒体。",
    ]

    return {
        "agent": "Source Quality Agent",
        "verdict": "positive" if grade_counts["A"] else "mixed",
        "summary": summary,
        "key_points": key_points,
        "claims": build_claims(key_points, confidence=0.74),
        "risks": warnings or ["来源质量仍需在正式交付前复核。"],
        "watch_items": ["A 级来源占比", "D 级来源数量", "来源发布时间", "公告与财报覆盖率"],
        "confidence": 0.74,
        "data_quality": build_data_quality(sources, warnings=warnings),
        "source_ratings": ratings,
        "grade_counts": grade_counts,
    }
