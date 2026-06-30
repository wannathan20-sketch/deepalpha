import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
DEFAULT_TENANT_ID = "default"
DEFAULT_USER_ID = "anonymous"
DATABASE_PATH = Path(os.getenv("DEEPALPHA_DB_PATH", DATA_DIR / "deepalpha.sqlite3"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


@contextmanager
def _connect():
    DATA_DIR.mkdir(exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_schema(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def ensure_schema(connection: sqlite3.Connection | None = None) -> None:
    owns_connection = connection is None
    if connection is None:
        DATA_DIR.mkdir(exist_ok=True)
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DATABASE_PATH)

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            user_id TEXT NOT NULL DEFAULT 'anonymous',
            company_name TEXT NOT NULL,
            symbol TEXT,
            yahoo_symbol TEXT,
            data_provider TEXT,
            thread_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            recommendation TEXT,
            confidence REAL,
            sources_count INTEGER,
            summary TEXT,
            markdown_report TEXT DEFAULT '',
            result_json TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_research_history_tenant_company
            ON research_history (tenant_id, company_name, created_at DESC);

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            user_id TEXT NOT NULL DEFAULT 'anonymous',
            company_name TEXT NOT NULL,
            symbol TEXT,
            yahoo_symbol TEXT,
            data_provider TEXT,
            created_at TEXT NOT NULL,
            last_analyzed_at TEXT,
            UNIQUE (tenant_id, user_id, company_name)
        );

        CREATE INDEX IF NOT EXISTS idx_watchlist_tenant_user
            ON watchlist (tenant_id, user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS report_tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            steps_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_report_tasks_created_at
            ON report_tasks (created_at DESC);

        CREATE TABLE IF NOT EXISTS report_chat_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            company_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, task_id)
        );

        CREATE TABLE IF NOT EXISTS report_chat_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            strategy TEXT NOT NULL,
            search_mode TEXT NOT NULL,
            content_json TEXT NOT NULL,
            route_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES report_chat_sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_report_chat_messages_session
            ON report_chat_messages (session_id, created_at);
        """
    )

    # Migrate existing tables that lack the full-report columns added in a later version.
    # 兼容旧表：为已存在的 research_history 表补充全文报告列。
    for col, col_type in [
        ("markdown_report", "TEXT DEFAULT ''"),
        ("result_json", "TEXT DEFAULT '{}'"),
    ]:
        try:
            connection.execute(
                f"ALTER TABLE research_history ADD COLUMN {col} {col_type}"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists — fine.

    if owns_connection:
        connection.commit()
        connection.close()


def save_research_history(
    company_name: str,
    thread_id: str,
    final_report: dict,
    citation_check: dict,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
    symbol: str | None = None,
    yahoo_symbol: str | None = None,
    data_provider: str | None = None,
    markdown_report: str = "",
    result_json: dict | None = None,
) -> dict:
    created_at = _now_iso()
    record = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "company_name": company_name,
        "symbol": symbol,
        "yahoo_symbol": yahoo_symbol,
        "data_provider": data_provider,
        "thread_id": thread_id,
        "created_at": created_at,
        "recommendation": final_report.get("recommendation", ""),
        "confidence": final_report.get("confidence", 0),
        "sources_count": final_report.get(
            "sources_count",
            citation_check.get("total_sources", 0),
        ),
        "summary": final_report.get("summary", ""),
        "markdown_report": markdown_report,
        "result_json": json.dumps(result_json, ensure_ascii=False, separators=(",", ":")) if result_json else "{}",
    }

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO research_history (
                tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider,
                thread_id, created_at, recommendation, confidence, sources_count, summary,
                markdown_report, result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["tenant_id"],
                record["user_id"],
                record["company_name"],
                record["symbol"],
                record["yahoo_symbol"],
                record["data_provider"],
                record["thread_id"],
                record["created_at"],
                record["recommendation"],
                record["confidence"],
                record["sources_count"],
                record["summary"],
                record["markdown_report"],
                record["result_json"],
            ),
        )
        record["id"] = cursor.lastrowid
        _update_watchlist_last_analyzed_at(
            company_name,
            created_at,
            tenant_id=tenant_id,
            user_id=user_id,
            connection=connection,
        )

    return record


def get_research_history(
    company_name: str | None = None,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict]:
    query = """
        SELECT id, tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider,
               thread_id, created_at, recommendation, confidence, sources_count, summary
        FROM research_history
        WHERE tenant_id = ? AND user_id = ?
    """
    params: list[str] = [tenant_id, user_id]

    if company_name is not None:
        query += " AND lower(company_name) = ?"
        params.append(company_name.lower())

    query += " ORDER BY created_at DESC"

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_history_by_id(
    history_id: int,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
) -> dict | None:
    """Return a single history record with full report data (markdown + result JSON).
    返回单条历史记录，含完整报告正文与结构化结果 JSON。
    """
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider,
                   thread_id, created_at, recommendation, confidence, sources_count, summary,
                   markdown_report, result_json
            FROM research_history
            WHERE id = ? AND tenant_id = ? AND user_id = ?
            """,
            (history_id, tenant_id, user_id),
        ).fetchone()

    if row is None:
        return None

    record = _row_to_dict(row)
    # Parse result_json back into a dict for the caller.
    # 将 result_json 反序列化为 dict 以便调用方直接使用。
    try:
        record["result"] = json.loads(record.get("result_json", "{}") or "{}")
    except json.JSONDecodeError:
        record["result"] = {}
    return record


def delete_history_by_id(
    history_id: int,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
) -> bool:
    """Delete a single history record by id. Returns True if deleted, False if not found.
    按 id 删除单条历史记录。
    """
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM research_history WHERE id = ? AND tenant_id = ? AND user_id = ?",
            (history_id, tenant_id, user_id),
        )
        return cursor.rowcount > 0


def add_to_watchlist(
    company_name: str,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
    symbol: str | None = None,
    yahoo_symbol: str | None = None,
    data_provider: str | None = None,
) -> dict:
    created_at = _now_iso()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO watchlist (
                tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, user_id, company_name) DO UPDATE SET
                symbol = COALESCE(excluded.symbol, watchlist.symbol),
                yahoo_symbol = COALESCE(excluded.yahoo_symbol, watchlist.yahoo_symbol),
                data_provider = COALESCE(excluded.data_provider, watchlist.data_provider)
            """,
            (tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider, created_at),
        )
        row = connection.execute(
            """
            SELECT id, tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider,
                   created_at, last_analyzed_at
            FROM watchlist
            WHERE tenant_id = ? AND user_id = ? AND company_name = ?
            """,
            (tenant_id, user_id, company_name),
        ).fetchone()

    return _row_to_dict(row)


def get_watchlist(
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, tenant_id, user_id, company_name, symbol, yahoo_symbol, data_provider,
                   created_at, last_analyzed_at
            FROM watchlist
            WHERE tenant_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (tenant_id, user_id),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def _update_watchlist_last_analyzed_at(
    company_name: str,
    analyzed_at: str,
    *,
    tenant_id: str,
    user_id: str,
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        UPDATE watchlist
        SET last_analyzed_at = ?
        WHERE tenant_id = ? AND user_id = ? AND lower(company_name) = ?
        """,
        (analyzed_at, tenant_id, user_id, company_name.lower()),
    )


def get_db_info() -> dict:
    """Return database stats: path, size, table names, row counts, schema.
    返回数据库统计信息，方便线上查看数据库状态。
    """
    path = DATABASE_PATH
    size_bytes = path.stat().st_size if path.exists() else 0
    tables = []
    with _connect() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        for (name,) in rows:
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{name}"'
            ).fetchone()[0]
            cols = connection.execute(f"PRAGMA table_info('{name}')").fetchall()
            tables.append({
                "name": name,
                "row_count": count,
                "columns": [{"name": c[1], "type": c[2]} for c in cols],
            })
    return {
        "db_path": str(path),
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024, 1),
        "tables": tables,
    }
