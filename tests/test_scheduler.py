from datetime import date, timedelta
import random

from mina.scheduler import InterruptionScheduler, ScheduleSettings


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_scheduler(clock, active, limit=None):
    fired = []
    scheduler = InterruptionScheduler(
        ScheduleSettings((10, 10), (5, 5), limit, 300, 1000),
        active,
        lambda: fired.append(clock.now),
        random.Random(3),
        clock=clock,
        today=lambda: date(2026, 10, 30),
    )
    scheduler.start()
    return scheduler, fired


def test_waits_until_interval_and_only_triggers_when_active():
    clock = Clock()
    active = [False]
    scheduler, fired = make_scheduler(clock, lambda _limit: active[0])
    clock.now = 10
    assert not scheduler.poll()
    active[0] = True
    assert scheduler.poll()
    assert fired == [10]


def test_respects_random_cooldown_after_interrupt():
    clock = Clock()
    scheduler, fired = make_scheduler(clock, lambda _limit: True)
    clock.now = 10
    assert scheduler.poll()
    clock.now = 19
    assert not scheduler.poll()
    scheduler.finish_interruption()
    clock.now = 23
    assert not scheduler.poll()
    clock.now = 24
    assert scheduler.poll()
    assert len(fired) == 2


def test_cooldown_starts_when_interruption_finishes():
    clock = Clock()
    scheduler, _ = make_scheduler(clock, lambda _limit: True)
    clock.now = 10
    assert scheduler.poll()
    clock.now = 100
    assert not scheduler.poll()

    scheduler.finish_interruption()

    clock.now = 104
    assert not scheduler.poll()
    clock.now = 105
    assert scheduler.poll()


def test_none_daily_limit_is_unlimited():
    clock = Clock()
    scheduler, _ = make_scheduler(clock, lambda _limit: True, limit=None)
    clock.now = 10
    assert scheduler.poll()
    scheduler.finish_interruption()
    clock.now = 20
    assert scheduler.poll()


def test_daily_limit_is_applied():
    clock = Clock()
    scheduler, _ = make_scheduler(clock, lambda _limit: True, limit=1)
    clock.now = 10
    assert scheduler.poll()
    clock.now = 20
    assert not scheduler.poll()


def test_daily_limit_resets_on_local_date_change():
    clock = Clock()
    current_day = [date(2026, 10, 30)]
    scheduler, _ = make_scheduler(clock, lambda _limit: True, limit=1)
    scheduler.today = lambda: current_day[0]
    clock.now = 10
    assert scheduler.poll()
    scheduler.finish_interruption()
    current_day[0] += timedelta(days=1)
    clock.now = 20
    assert scheduler.poll()


def test_cancel_interruption_releases_slot_without_counting_a_missed_message():
    clock = Clock()
    scheduler, fired = make_scheduler(clock, lambda _limit: True, limit=1)
    clock.now = 10
    assert scheduler.poll()
    assert scheduler.daily_count == 1

    scheduler.cancel_interruption()
    scheduler.stop()
    scheduler.start()

    assert scheduler.daily_count == 0
    assert not scheduler._interruption_active
    clock.now = 19
    assert not scheduler.poll()
    clock.now = 20
    assert scheduler.poll()
    assert fired == [10, 20]
