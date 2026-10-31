from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ScheduleSettings:
    interval_seconds: tuple[float, float]
    cooldown_seconds: tuple[float, float]
    daily_limit: int | None
    active_idle_limit_seconds: float
    poll_interval_ms: int


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

    @property
    def daily_count(self) -> int:
        self._reset_daily_count_if_needed()
        return self._daily_count

    def start(self) -> None:
        if self.enabled:
            return
        self.enabled = True
        self.next_due = self.clock() + self._random_delay(self.settings.interval_seconds)

    def stop(self) -> None:
        self.enabled = False

    def cancel_interruption(self) -> None:
        if not self._interruption_active:
            return
        self._reset_daily_count_if_needed()
        self._interruption_active = False
        self._daily_count = max(0, self._daily_count - 1)
        self.cooldown_until = 0.0

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
        self.on_interrupt()
        return True

    def finish_interruption(self) -> None:
        if not self._interruption_active:
            return
        self._interruption_active = False
        self.cooldown_until = self.clock() + self._random_delay(
            self.settings.cooldown_seconds
        )

    def _random_delay(self, value_range: tuple[float, float]) -> float:
        return self.random.uniform(*value_range)

    def _reset_daily_count_if_needed(self) -> None:
        current_day = self.today()
        if current_day != self._day:
            self._day = current_day
            self._daily_count = 0
