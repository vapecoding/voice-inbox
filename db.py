from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("voice_inbox.db")


def set_database_path(path: str | Path) -> None:
    global DB_PATH
    DB_PATH = Path(path)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP NULL
            );

            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NULL REFERENCES topics(id) ON DELETE CASCADE,
                telegram_message_id INTEGER NOT NULL,
                telegram_chat_id INTEGER NOT NULL,
                telegram_file_id TEXT NOT NULL,
                duration INTEGER NOT NULL,
                transcript TEXT NOT NULL,
                forward_from TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (telegram_chat_id, telegram_message_id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id INTEGER NULL REFERENCES recordings(id) ON DELETE CASCADE,
                topic_id INTEGER NULL REFERENCES topics(id) ON DELETE CASCADE,
                summary TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def close_open_topics() -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE topics
            SET closed_at = CURRENT_TIMESTAMP
            WHERE closed_at IS NULL
            """
        )
        connection.commit()
        return cursor.rowcount


def save_recording(
    *,
    topic_id: int | None,
    telegram_message_id: int,
    telegram_chat_id: int,
    telegram_file_id: str,
    duration: int,
    transcript: str,
    forward_from: str | None,
) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO recordings (
                topic_id,
                telegram_message_id,
                telegram_chat_id,
                telegram_file_id,
                duration,
                transcript,
                forward_from
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic_id,
                telegram_message_id,
                telegram_chat_id,
                telegram_file_id,
                duration,
                transcript,
                forward_from,
            ),
        )
        connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)

        row = connection.execute(
            """
            SELECT id
            FROM recordings
            WHERE telegram_chat_id = ? AND telegram_message_id = ?
            """,
            (telegram_chat_id, telegram_message_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to save recording")
        return int(row["id"])


def get_recordings(page: int, per_page: int = 20) -> tuple[list[sqlite3.Row], int]:
    offset = max(page - 1, 0) * per_page
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM recordings
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()
        total = int(connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0])
    return rows, total


def get_recording(recording_id: int) -> sqlite3.Row | None:
    with _connect() as connection:
        return connection.execute(
            "SELECT * FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()


def delete_recording(recording_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM recordings WHERE id = ?",
            (recording_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


def search_recordings(query: str, limit: int = 50) -> list[sqlite3.Row]:
    with _connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM recordings
            WHERE transcript LIKE ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        ).fetchall()


def create_topic(title: str | None = None) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO topics (title) VALUES (?)",
            (title,),
        )
        connection.commit()
        return int(cursor.lastrowid)


def close_topic(topic_id: int) -> None:
    with _connect() as connection:
        connection.execute(
            """
            UPDATE topics
            SET closed_at = COALESCE(closed_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (topic_id,),
        )
        connection.commit()


def get_topic(topic_id: int) -> sqlite3.Row | None:
    with _connect() as connection:
        return connection.execute(
            "SELECT * FROM topics WHERE id = ?",
            (topic_id,),
        ).fetchone()


def get_topic_with_recordings(topic_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with _connect() as connection:
        topic = connection.execute(
            "SELECT * FROM topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
        recordings = connection.execute(
            """
            SELECT *
            FROM recordings
            WHERE topic_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (topic_id,),
        ).fetchall()
    return topic, recordings


def delete_topic(topic_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM topics WHERE id = ?",
            (topic_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


def save_summary(
    *,
    text: str,
    recording_id: int | None = None,
    topic_id: int | None = None,
) -> int:
    if not recording_id and not topic_id:
        raise ValueError("recording_id or topic_id is required")

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO summaries (recording_id, topic_id, summary)
            VALUES (?, ?, ?)
            """,
            (recording_id, topic_id, text),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_summaries_for_recording(recording_id: int) -> list[sqlite3.Row]:
    with _connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM summaries
            WHERE recording_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (recording_id,),
        ).fetchall()


def get_summaries_for_topic(topic_id: int) -> list[sqlite3.Row]:
    with _connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM summaries
            WHERE topic_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (topic_id,),
        ).fetchall()


def get_latest_summary_for_recording(recording_id: int) -> sqlite3.Row | None:
    summaries = get_summaries_for_recording(recording_id)
    return summaries[0] if summaries else None


def get_latest_summary_for_topic(topic_id: int) -> sqlite3.Row | None:
    summaries = get_summaries_for_topic(topic_id)
    return summaries[0] if summaries else None


def get_topic_stats(topic_id: int) -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS recording_count,
                COALESCE(SUM(duration), 0) AS total_duration
            FROM recordings
            WHERE topic_id = ?
            """,
            (topic_id,),
        ).fetchone()
    return {
        "recording_count": int(row["recording_count"]) if row else 0,
        "total_duration": int(row["total_duration"]) if row else 0,
    }


def get_archive_stats() -> dict[str, int]:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM recordings) AS recording_count,
                (SELECT COUNT(*) FROM topics) AS topic_count
            """
        ).fetchone()
    return {
        "recording_count": int(row["recording_count"]) if row else 0,
        "topic_count": int(row["topic_count"]) if row else 0,
    }


def get_feed_items(page: int, per_page: int = 20) -> tuple[list[dict[str, Any]], int]:
    with _connect() as connection:
        standalone_rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                duration,
                transcript,
                forward_from
            FROM recordings
            WHERE topic_id IS NULL
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        topic_rows = connection.execute(
            """
            SELECT
                t.id,
                t.title,
                t.created_at,
                t.closed_at,
                COALESCE(MAX(r.created_at), t.created_at) AS sort_created_at,
                COUNT(r.id) AS recording_count,
                COALESCE(SUM(r.duration), 0) AS total_duration
            FROM topics t
            LEFT JOIN recordings r ON r.topic_id = t.id
            GROUP BY t.id, t.title, t.created_at, t.closed_at
            ORDER BY sort_created_at DESC, t.id DESC
            """
        ).fetchall()

        items: list[dict[str, Any]] = []
        for row in standalone_rows:
            items.append(
                {
                    "kind": "recording",
                    "id": int(row["id"]),
                    "created_at": row["created_at"],
                    "duration": int(row["duration"]),
                    "transcript": row["transcript"],
                    "forward_from": row["forward_from"],
                }
            )
        for row in topic_rows:
            items.append(
                {
                    "kind": "topic",
                    "id": int(row["id"]),
                    "title": row["title"],
                    "created_at": row["sort_created_at"],
                    "topic_created_at": row["created_at"],
                    "closed_at": row["closed_at"],
                    "recording_count": int(row["recording_count"]),
                    "total_duration": int(row["total_duration"]),
                    "recordings": [],
                }
            )

        items.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        total = len(items)
        offset = max(page - 1, 0) * per_page
        paginated_items = items[offset : offset + per_page]

        topic_ids = [item["id"] for item in paginated_items if item["kind"] == "topic"]
        recordings_map: dict[int, list[sqlite3.Row]] = {topic_id: [] for topic_id in topic_ids}
        if topic_ids:
            placeholders = ",".join("?" for _ in topic_ids)
            rows = connection.execute(
                f"""
                SELECT *
                FROM recordings
                WHERE topic_id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                topic_ids,
            ).fetchall()
            for row in rows:
                recordings_map[int(row["topic_id"])].append(row)

        for item in paginated_items:
            if item["kind"] == "topic":
                item["recordings"] = recordings_map.get(item["id"], [])

        return paginated_items, total
