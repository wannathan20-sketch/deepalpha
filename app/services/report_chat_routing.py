import re


TEMPORAL_TERMS = (
    "最新",
    "今天",
    "今日",
    "现在",
    "当前",
    "刚刚",
    "近期",
    "最近",
    "本周",
    "本月",
    "盘前",
    "盘后",
    "截至目前",
    "有没有新消息",
    "latest",
    "today",
    "now",
    "current",
    "recent",
    "this week",
    "this month",
    "premarket",
    "after hours",
    "since the report",
    "new update",
)
DATE_PATTERN = re.compile(r"\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\b")


def _temporal_match(question: str) -> str:
    lowered = question.casefold()
    for term in TEMPORAL_TERMS:
        if term.casefold() in lowered:
            return term
    match = DATE_PATTERN.search(question)
    return match.group(0) if match else ""


def route_report_question(question: str, strategy: str, search_mode: str) -> dict:
    match = _temporal_match(question)
    temporal_intent = bool(match)
    if search_mode == "web":
        mode = "report_web_qa"
        reason = "Web search was explicitly requested."
    elif search_mode == "report_only":
        mode = "report_qa"
        reason = "Report-only mode was explicitly requested."
    elif temporal_intent:
        mode = "report_web_qa"
        reason = f"Temporal intent matched: {match}"
    else:
        mode = "report_qa"
        reason = "No temporal intent was detected."
    return {
        "mode": mode,
        "strategy": strategy,
        "temporal_intent": temporal_intent,
        "web_status": "not_requested",
        "reason": reason,
    }
