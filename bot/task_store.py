from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from models import UserPreferences


@dataclass(slots=True)
class StoredTask:
    task_id: str
    user_id: int
    chat_id: int
    topic: str
    status: str
    output_url: str | None
    edit_url: str | None
    file_format: str | None
    created_at: str | None
    updated_at: str | None
    raw_json: str | None


class TaskStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_url TEXT,
                    edit_url TEXT,
                    file_format TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    raw_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    prefs_json TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON tasks(user_id, COALESCE(updated_at, created_at) DESC)")

    def upsert_task(
        self,
        *,
        task_id: str,
        user_id: int,
        chat_id: int,
        topic: str,
        status: str,
        output_url: str | None = None,
        edit_url: str | None = None,
        file_format: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        raw_json: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks(task_id, user_id, chat_id, topic, status, output_url, edit_url, file_format, created_at, updated_at, raw_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    output_url=COALESCE(excluded.output_url, tasks.output_url),
                    edit_url=COALESCE(excluded.edit_url, tasks.edit_url),
                    file_format=COALESCE(excluded.file_format, tasks.file_format),
                    updated_at=COALESCE(excluded.updated_at, tasks.updated_at),
                    raw_json=COALESCE(excluded.raw_json, tasks.raw_json)
                """,
                (
                    task_id,
                    user_id,
                    chat_id,
                    topic,
                    status,
                    output_url,
                    edit_url,
                    file_format,
                    created_at,
                    updated_at,
                    raw_json,
                ),
            )

    def get_latest_for_user(self, user_id: int) -> StoredTask | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return self._row_to_task(row)

    def get_task(self, task_id: str) -> StoredTask | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._row_to_task(row)

    def save_user_preferences(self, user_id: int, prefs: UserPreferences) -> None:
        payload = json.dumps(prefs.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences(user_id, prefs_json, updated_at)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    prefs_json=excluded.prefs_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (int(user_id), payload),
            )

    def get_user_preferences(self, user_id: int, default: UserPreferences) -> UserPreferences:
        with self._connect() as conn:
            row = conn.execute("SELECT prefs_json FROM user_preferences WHERE user_id = ?", (int(user_id),)).fetchone()
        if row is None:
            return UserPreferences.from_any(default.to_dict())
        try:
            raw = json.loads(row["prefs_json"])
        except Exception:
            return UserPreferences.from_any(default.to_dict())
        return UserPreferences.from_any(raw)

    def _row_to_task(self, row: sqlite3.Row | None) -> StoredTask | None:
        if row is None:
            return None
        return StoredTask(
            task_id=row["task_id"],
            user_id=int(row["user_id"]),
            chat_id=int(row["chat_id"]),
            topic=row["topic"],
            status=row["status"],
            output_url=row["output_url"],
            edit_url=row["edit_url"],
            file_format=row["file_format"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            raw_json=row["raw_json"],
        )
