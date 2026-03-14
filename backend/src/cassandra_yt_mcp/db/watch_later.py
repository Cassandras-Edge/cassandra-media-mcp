from __future__ import annotations

from typing import Any

from cassandra_yt_mcp.db.database import Database


class WatchLaterRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def register_user(self, user_id: str, cookies_b64: str) -> None:
        with self.db.lock:
            self.db.conn.execute(
                """
                INSERT INTO watch_later_users (user_id, cookies_b64)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  cookies_b64 = excluded.cookies_b64
                """,
                (user_id, cookies_b64),
            )
            self.db.conn.commit()

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = self.db.conn.execute(
            "SELECT * FROM watch_later_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_due_users(self) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM watch_later_users
            WHERE enabled = 1
              AND (last_sync_at IS NULL
                   OR datetime(last_sync_at, '+' || interval_minutes || ' minutes') <= datetime('now'))
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def is_seen(self, user_id: str, video_id: str) -> bool:
        row = self.db.conn.execute(
            "SELECT 1 FROM watch_later_seen WHERE user_id = ? AND video_id = ?",
            (user_id, video_id),
        ).fetchone()
        return row is not None

    def mark_seen_batch(self, user_id: str, entries: list[dict[str, str | None]]) -> None:
        with self.db.lock:
            self.db.conn.executemany(
                """
                INSERT INTO watch_later_seen (user_id, video_id, title)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, video_id) DO NOTHING
                """,
                [(user_id, e["video_id"], e.get("title")) for e in entries],
            )
            self.db.conn.commit()

    def list_seen(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            "SELECT * FROM watch_later_seen WHERE user_id = ? ORDER BY first_seen_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_seen(self, user_id: str) -> int:
        row = self.db.conn.execute(
            "SELECT COUNT(*) FROM watch_later_seen WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    def update_last_sync(self, user_id: str, error: str | None = None) -> None:
        with self.db.lock:
            self.db.conn.execute(
                """
                UPDATE watch_later_users
                SET last_sync_at = datetime('now'), last_error = ?
                WHERE user_id = ?
                """,
                (error, user_id),
            )
            self.db.conn.commit()
