from __future__ import annotations

import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ScheduleSettings:
    interval_seconds: tuple[float, float]
    cooldown_seconds: tuple[float, float]
    daily_limit: int | None
    active_idle_limit_seconds: float
    poll_interval_ms: int
    state_path: Path | None = None


class InterruptionScheduler:
    def __init__(
        self,
        settings: ScheduleSettings,
        is_active: Callable[[float], bool],
        on_interrupt: Callable[[], None],
        random_source: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.settings = settings
        self.is_active = is_active
        self.on_interrupt = on_interrupt
        self.random = random_source or random.Random()
        self.clock = clock
        self.today = today
        self.enabled = False
        self.next_due = 0.0
        self.cooldown_until = 0.0
        self._interruption_active = False
        self._day = self.today()
        self._daily_count = 0
        if settings.state_path is not None:
            self._load_state(settings.state_path)

    @property
    def daily_count(self) -> int:
        self._reset_daily_count_if_needed()
        return self._daily_count

    def start(self) -> None:
        if self.enabled:
            return
        self._reset_daily_count_if_needed()
        self.enabled = True
        now = self.clock()
        if self.next_due <= now:
            self.next_due = now + self._random_delay(self.settings.interval_seconds)
        if self.cooldown_until <= now:
            self.cooldown_until = 0.0
        self._persist_state()

    def stop(self) -> None:
        self.enabled = False
        self._persist_state()

    def cancel_interruption(self) -> None:
        if not self._interruption_active:
            return
        self._reset_daily_count_if_needed()
        self._interruption_active = False
        self._daily_count = max(0, self._daily_count - 1)
        self.cooldown_until = 0.0
        self._persist_state()

    def poll(self) -> bool:
        if not self.enabled:
            return False
        self._reset_daily_count_if_needed()
        now = self.clock()
        if self.settings.daily_limit is not None and self._daily_count >= self.settings.daily_limit:
            return False
        if self._interruption_active or now < self.next_due or now < self.cooldown_until:
            return False
        if not self.is_active(self.settings.active_idle_limit_seconds):
            return False

        self._daily_count += 1
        self._interruption_active = True
        self.next_due = now + self._random_delay(self.settings.interval_seconds)
        self._persist_state()
        self.on_interrupt()
        return True

    def finish_interruption(self) -> None:
        if not self._interruption_active:
            return
        self._interruption_active = False
        self.cooldown_until = self.clock() + self._random_delay(
            self.settings.cooldown_seconds
        )
        self._persist_state()

    def _random_delay(self, value_range: tuple[float, float]) -> float:
        return self.random.uniform(*value_range)

    def _reset_daily_count_if_needed(self) -> None:
        current_day = self.today()
        if current_day != self._day:
            self._day = current_day
            self._daily_count = 0
            self._persist_state()

    def _load_state(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=5.0) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    scheduled_day TEXT NOT NULL,
                    daily_count INTEGER NOT NULL,
                    next_due REAL NOT NULL,
                    cooldown_until REAL NOT NULL
                )
                """
            )
            row = connection.execute(
                """
                SELECT scheduled_day, daily_count, next_due, cooldown_until
                FROM scheduler_state WHERE id = 1
                """
            ).fetchone()
        if row is not None:
            self._day = date.fromisoformat(row[0])
            self._daily_count = int(row[1])
            self.next_due = float(row[2])
            self.cooldown_until = float(row[3])

    def _persist_state(self) -> None:
        path = self.settings.state_path
        if path is None:
            return
        with sqlite3.connect(path, timeout=5.0) as connection:
            connection.execute(
                """
                INSERT INTO scheduler_state
                    (id, scheduled_day, daily_count, next_due, cooldown_until)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scheduled_day = excluded.scheduled_day,
                    daily_count = excluded.daily_count,
                    next_due = excluded.next_due,
                    cooldown_until = excluded.cooldown_until
                """,
                (
                    self._day.isoformat(),
                    self._daily_count,
                    self.next_due,
                    self.cooldown_until,
                ),
            )
