import json
from uuid import uuid4

from app.memory.store import _connect, _now_iso


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> dict:
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_turn(
    user_id: str,
    task_id: str,
    company_name: str,
    question: str,
    answer: dict,
    strategy: str,
    search_mode: str,
    route: dict,
) -> str:
    now = _now_iso()
    assistant_message_id = str(uuid4())
    with _connect() as connection:
        row = connection.execute(
            "SELECT session_id FROM report_chat_sessions WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        ).fetchone()
        session_id = row["session_id"] if row else str(uuid4())
        if row is None:
            connection.execute(
                """
                INSERT INTO report_chat_sessions
                    (session_id, user_id, task_id, company_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, task_id, company_name, now, now),
            )
        else:
            connection.execute(
                "UPDATE report_chat_sessions SET company_name = ?, updated_at = ? WHERE session_id = ?",
                (company_name, now, session_id),
            )
        connection.executemany(
            """
            INSERT INTO report_chat_messages
                (message_id, session_id, role, strategy, search_mode, content_json, route_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid4()),
                    session_id,
                    "user",
                    strategy,
                    search_mode,
                    _dump({"question": question}),
                    _dump(route),
                    now,
                ),
                (
                    assistant_message_id,
                    session_id,
                    "assistant",
                    strategy,
                    search_mode,
                    _dump(answer),
                    _dump(route),
                    now,
                ),
            ],
        )
    return assistant_message_id


def get_history(user_id: str, task_id: str) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT m.role, m.strategy, m.search_mode, m.content_json, m.route_json,
                   m.created_at, m.message_id
            FROM report_chat_messages m
            JOIN report_chat_sessions s ON s.session_id = m.session_id
            WHERE s.user_id = ? AND s.task_id = ?
            ORDER BY m.created_at, m.rowid
            """,
            (user_id, task_id),
        ).fetchall()
    turns = []
    pending_question = None
    for row in rows:
        content = _load(row["content_json"])
        if row["role"] == "user":
            pending_question = content.get("question", "")
            continue
        turns.append(
            {
                **content,
                "message_id": row["message_id"],
                "question": pending_question or "",
                "strategy": row["strategy"],
                "search_mode": row["search_mode"],
                "route": _load(row["route_json"]),
                "created_at": row["created_at"],
            }
        )
        pending_question = None
    return turns


def get_recent_turns(user_id: str, task_id: str, limit: int = 6) -> list[dict]:
    history = get_history(user_id, task_id)
    return history[-max(0, limit):]


def delete_history(user_id: str, task_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM report_chat_sessions WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        )
    return cursor.rowcount > 0
