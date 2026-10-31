from datetime import datetime, timedelta, timezone

from mina.time_behavior import TimeBehaviorMonitor


class FixedRandom:
    def uniform(self, low, _high):
        return low


def create_monitor(path, rules, delay=(0, 0), cooldown=(0, 0)):
    return TimeBehaviorMonitor(
        path,
        rules,
        cooldown,
        delay,
        random_source=FixedRandom(),
    )


def test_startup_is_persisted_once_per_boot(tmp_path):
    rules = [{"id": "startup", "type": "startup", "name": "startup"}]
    monitor = create_monitor(tmp_path / "behavior.sqlite3", rules)
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

    event = monitor.poll(now, uptime_seconds=60, idle_seconds=0)

    assert event["rule_id"] == "startup"
    monitor.acknowledge(event["id"])
    assert monitor.poll(now + timedelta(seconds=1), 61, 0) is None


def test_uptime_rules_choose_highest_priority_and_fire_once(tmp_path):
    rules = [
        {"id": "two", "type": "uptime", "hours": 2, "priority": 1},
        {"id": "twelve", "type": "uptime", "hours": 12, "priority": 3},
        {"id": "six", "type": "uptime", "hours": 6, "priority": 2},
    ]
    monitor = create_monitor(tmp_path / "behavior.sqlite3", rules)
    now = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)

    first = monitor.poll(now, 13 * 3600, 0)
    assert first["rule_id"] == "twelve"
    monitor.acknowledge(first["id"])

    second = monitor.poll(now + timedelta(seconds=1), 13 * 3600 + 1, 0)
    assert second["rule_id"] == "six"


def test_inactivity_group_prevents_duplicate_idle_events(tmp_path):
    rules = [
        {
            "id": "no_interaction",
            "type": "no_interaction",
            "seconds": 1800,
            "exclusive_group": "inactivity",
            "priority": 2,
        },
        {
            "id": "idle",
            "type": "idle",
            "seconds": 1200,
            "exclusive_group": "inactivity",
            "priority": 1,
        },
    ]
    monitor = create_monitor(tmp_path / "behavior.sqlite3", rules)
    now = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)

    event = monitor.poll(now, 3600, 1200)
    assert event["rule_id"] == "idle"
    monitor.acknowledge(event["id"])
    assert monitor.poll(now + timedelta(minutes=11), 4260, 1860) is None


def test_late_night_range_and_period_change(tmp_path):
    rules = [
        {
            "id": "late",
            "type": "time_range",
            "start": "00:00",
            "end": "05:00",
            "priority": 2,
        },
        {"id": "period", "type": "time_period", "priority": 1},
    ]
    monitor = create_monitor(tmp_path / "behavior.sqlite3", rules)
    morning = datetime(2026, 1, 1, 4, 59, tzinfo=timezone.utc)
    startup = monitor.poll(morning, 600, 0)
    assert startup["rule_id"] == "late"
    monitor.acknowledge(startup["id"])

    after_dawn = datetime(2026, 1, 1, 5, 1, tzinfo=timezone.utc)
    event = monitor.poll(after_dawn, 720, 0)
    assert event["rule_id"] == "period"


def test_new_day_and_last_spoken_context_persist(tmp_path):
    path = tmp_path / "behavior.sqlite3"
    rules = [{"id": "day", "type": "new_day"}]
    monitor = create_monitor(path, rules)
    yesterday = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert monitor.poll(yesterday, 60, 0) is None
    spoken_at = yesterday + timedelta(minutes=1)
    monitor.mark_spoken(spoken_at)

    next_day = yesterday + timedelta(days=1)
    event = monitor.poll(next_day, 86460, 0)

    assert event["rule_id"] == "day"
    assert event["context"]["last_spoke_at"] == spoken_at.isoformat()
    assert event["context"]["seconds_since_last_spoke"] == 86340


def test_pending_random_delay_survives_monitor_restart(tmp_path):
    path = tmp_path / "behavior.sqlite3"
    rules = [{"id": "startup", "type": "startup"}]
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    first_monitor = create_monitor(path, rules, delay=(10, 10))

    assert first_monitor.poll(now, 60, 0) is None
    restarted_monitor = create_monitor(path, rules, delay=(10, 10))
    assert restarted_monitor.poll(now + timedelta(seconds=9), 69, 0) is None
    event = restarted_monitor.poll(now + timedelta(seconds=10), 70, 0)

    assert event["rule_id"] == "startup"
    assert event["context"]["time_period"] == "morning"


def test_cooldown_survives_monitor_restart(tmp_path):
    path = tmp_path / "behavior.sqlite3"
    rules = [
        {"id": "six", "type": "uptime", "hours": 6, "priority": 2},
        {"id": "two", "type": "uptime", "hours": 2, "priority": 1},
    ]
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    monitor = create_monitor(path, rules, cooldown=(3600, 3600))
    event = monitor.poll(now, 6 * 3600, 0)
    assert event["rule_id"] == "six"
    monitor.acknowledge(event["id"])

    restarted_monitor = create_monitor(path, rules, cooldown=(3600, 3600))
    assert restarted_monitor.poll(now + timedelta(minutes=30), 6.5 * 3600, 0) is None
    next_event = restarted_monitor.poll(now + timedelta(hours=1, seconds=1), 7 * 3600, 0)
    assert next_event["rule_id"] == "two"
