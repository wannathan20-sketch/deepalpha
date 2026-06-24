import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_auto_routes_temporal_questions_to_web() -> None:
    from app.services.report_chat_routing import route_report_question

    route = route_report_question("今天有没有新消息？", "risk", "auto")

    assert route["mode"] == "report_web_qa"
    assert route["temporal_intent"] is True
    assert "今天" in route["reason"]


def test_report_only_overrides_temporal_intent() -> None:
    from app.services.report_chat_routing import route_report_question

    route = route_report_question("latest update today", "news", "report_only")

    assert route["mode"] == "report_qa"
    assert route["temporal_intent"] is True


def test_web_mode_forces_search_without_temporal_words() -> None:
    from app.services.report_chat_routing import route_report_question

    route = route_report_question("Explain the margin risk.", "risk", "web")

    assert route["mode"] == "report_web_qa"
    assert route["temporal_intent"] is False

