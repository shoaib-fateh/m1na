from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class PersonalDataset:
    """Local-only archive of Mina's generated messages and chat conversation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('thought', 'chat')),
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    text TEXT NOT NULL,
                    active_applications TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS messages_kind_id ON messages(kind, id)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def add_message(
        self,
        kind: str,
        role: str,
        text: str,
        active_applications: list[str] | None = None,
    ) -> None:
        if kind not in {"thought", "chat"}:
            raise ValueError(f"Unsupported dataset message kind: {kind!r}")
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported dataset message role: {role!r}")
        if not text.strip():
            raise ValueError("Dataset messages cannot be empty.")
        applications = json.dumps(active_applications or [], ensure_ascii=False)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages
                    (timestamp, kind, role, text, active_applications)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, kind, role, text, applications),
            )

    def recent_chat(self, limit: int) -> list[dict[str, str]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("Chat memory limit must be a positive integer.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, text
                FROM messages
                WHERE kind = 'chat'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [{"role": role, "text": text} for role, text in reversed(rows)]
