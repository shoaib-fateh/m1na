from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class TimeBehaviorMonitor:
    """Persist and prioritize local time-based behavior events."""

    def __init__(
        self,
        path: str | Path,
        rules: list[dict[str, Any]],
        cooldown_seconds: tuple[float, float],
        delay_seconds: tuple[float, float],
        random_source: random.Random | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rules = sorted(
            (rule for rule in rules if rule.get("enabled", True)),
            key=lambda rule: float(rule.get("priority", 0)),
            reverse=True,
        )
        self.cooldown_seconds = cooldown_seconds
        self.delay_seconds = delay_seconds
        self.random = random_source or random.Random()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS behavior_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS behavior_fired (
                    rule_id TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    group_id TEXT,
                    fired_at TEXT NOT NULL,
                    PRIMARY KEY (rule_id, event_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS behavior_pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_json TEXT NOT NULL,
                    due_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def poll(
        self,
        now: datetime,
        uptime_seconds: float,
        idle_seconds: float,
    ) -> dict[str, Any] | None:
        if now.tzinfo is None:
            now = now.astimezone()
        now = now.replace(microsecond=0)
        with self._connect() as connection:
            pending = connection.execute(
                "SELECT id, event_json, due_at FROM behavior_pending ORDER BY id LIMIT 1"
            ).fetchone()
            if pending is not None:
                if now >= datetime.fromisoformat(pending[2]):
                    event = json.loads(pending[1])
                    event["id"] = int(pending[0])
                    return event
                return None

            boot_id = self._boot_id(now, uptime_seconds)
            previous_boot_id = self._get_meta(connection, "boot_id")
            boot_changed = previous_boot_id != boot_id
            if boot_changed and not any(
                rule["type"] == "startup" for rule in self.rules
            ):
                self._set_meta(connection, "boot_id", boot_id)

            current_period = self._day_period(now.hour)
            if self._get_meta(connection, "last_period") is None:
                self._set_meta(connection, "last_period", current_period)
            if self._get_meta(connection, "last_date") is None:
                self._set_meta(connection, "last_date", now.date().isoformat())

            cooldown_until = self._get_meta(connection, "cooldown_until")
            if cooldown_until and now < datetime.fromisoformat(cooldown_until):
                return None

            last_spoke_value = self._get_meta(connection, "last_spoke_at")
            last_spoke = (
                datetime.fromisoformat(last_spoke_value)
                if last_spoke_value
                else None
            )
            interaction_at = now - timedelta(seconds=max(0.0, idle_seconds))
            context = {
                "local_datetime": now.isoformat(timespec="seconds"),
                "date": now.date().isoformat(),
                "time": now.strftime("%H:%M"),
                "time_period": current_period,
                "uptime_seconds": max(0.0, uptime_seconds),
                "uptime_hours": max(0.0, uptime_seconds) / 3600,
                "idle_seconds": max(0.0, idle_seconds),
                "seconds_since_last_interaction": max(0.0, idle_seconds),
                "last_interaction_at": interaction_at.isoformat(timespec="seconds"),
                "last_spoke_at": (
                    last_spoke.isoformat(timespec="seconds") if last_spoke else None
                ),
                "seconds_since_last_spoke": (
                    max(0.0, (now - last_spoke).total_seconds())
                    if last_spoke
                    else None
                ),
            }

            for rule in self.rules:
                event_key = self._matching_event_key(
                    rule,
                    now,
                    context,
                    boot_id,
                    boot_changed,
                    connection,
                )
                if event_key is None:
                    continue
                event = {
                    "rule_id": str(rule["id"]),
                    "name": str(rule.get("name", rule["id"])),
                    "context": context,
                }
                delay = self.random.uniform(*self.delay_seconds)
                due_at = now + timedelta(seconds=delay)
                pending_cursor = connection.execute(
                    "INSERT INTO behavior_pending (event_json, due_at) VALUES (?, ?)",
                    (json.dumps(event, ensure_ascii=False), due_at.isoformat()),
                )
                pending_id = int(pending_cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO behavior_fired (rule_id, event_key, group_id, fired_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(rule["id"]),
                        event_key,
                        rule.get("exclusive_group"),
                        now.isoformat(),
                    ),
                )
                if rule.get("type") == "startup":
                    self._set_meta(connection, "boot_id", boot_id)
                cooldown = self.random.uniform(*self.cooldown_seconds)
                self._set_meta(
                    connection,
                    "cooldown_until",
                    (now + timedelta(seconds=cooldown)).isoformat(),
                )
                if rule.get("type") == "new_day":
                    self._set_meta(connection, "last_date", now.date().isoformat())
                if rule.get("type") == "time_period":
                    self._set_meta(connection, "last_period", current_period)
                if now >= due_at:
                    event["id"] = pending_id
                    return event
                return None
        return None

    def acknowledge(self, event_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM behavior_pending WHERE id = ?", (event_id,))

    def mark_spoken(self, when: datetime | None = None) -> None:
        when = when or datetime.now().astimezone()
        if when.tzinfo is None:
            when = when.astimezone()
        with self._connect() as connection:
            self._set_meta(
                connection,
                "last_spoke_at",
                when.replace(microsecond=0).isoformat(),
            )

    def _matching_event_key(
        self,
        rule: dict[str, Any],
        now: datetime,
        context: dict[str, Any],
        boot_id: str,
        boot_changed: bool,
        connection: sqlite3.Connection,
    ) -> str | None:
        rule_id = str(rule["id"])
        rule_type = rule["type"]
        event_key: str | None = None

        if rule_type == "startup":
            if boot_changed:
                event_key = boot_id
        elif rule_type == "uptime":
            if context["uptime_seconds"] >= float(rule["hours"]) * 3600:
                event_key = boot_id
        elif rule_type == "time_range":
            start = self._minutes(rule["start"])
            end = self._minutes(rule["end"])
            current = now.hour * 60 + now.minute
            in_range = start <= current < end if start < end else current >= start or current < end
            if in_range:
                event_key = now.date().isoformat()
        elif rule_type in {"idle", "no_interaction"}:
            if context["idle_seconds"] >= float(rule["seconds"]):
                event_key = context["last_interaction_at"][:16]
        elif rule_type == "new_day":
            if self._get_meta(connection, "last_date") != now.date().isoformat():
                event_key = now.date().isoformat()
        elif rule_type == "time_period":
            if self._get_meta(connection, "last_period") != context["time_period"]:
                event_key = f"{now.date().isoformat()}:{context['time_period']}"
        elif rule_type == "since_spoke":
            seconds_since_spoke = context["seconds_since_last_spoke"]
            if (
                seconds_since_spoke is not None
                and seconds_since_spoke >= float(rule["seconds"])
            ):
                event_key = now.date().isoformat()

        if event_key is None:
            return None
        fired = connection.execute(
            "SELECT 1 FROM behavior_fired WHERE rule_id = ? AND event_key = ?",
            (rule_id, event_key),
        ).fetchone()
        if fired:
            return None
        exclusive_group = rule.get("exclusive_group")
        if exclusive_group and connection.execute(
            "SELECT 1 FROM behavior_fired WHERE group_id = ? AND event_key = ?",
            (str(exclusive_group), event_key),
        ).fetchone():
            return None
        return event_key

    @staticmethod
    def _boot_id(now: datetime, uptime_seconds: float) -> str:
        boot_timestamp = now.timestamp() - max(0.0, uptime_seconds)
        return str(round(boot_timestamp / 60))

    @staticmethod
    def _day_period(hour: int) -> str:
        if hour < 5:
            return "late_night"
        if hour < 12:
            return "morning"
        if hour < 17:
            return "afternoon"
        if hour < 21:
            return "evening"
        return "night"

    @staticmethod
    def _minutes(value: str) -> int:
        hour_text, minute_text = value.split(":", maxsplit=1)
        return int(hour_text) * 60 + int(minute_text)

    @staticmethod
    def _get_meta(connection: sqlite3.Connection, key: str) -> str | None:
        row = connection.execute(
            "SELECT value FROM behavior_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO behavior_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
