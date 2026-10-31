from mina.activity import idle_seconds_from_ticks, is_fullscreen_rect


def test_idle_seconds_handles_gettickcount_wraparound():
    assert idle_seconds_from_ticks(0x1_0000_0005, 0xFFFFFFF5) == 0.016


def test_idle_seconds_from_last_input():
    assert idle_seconds_from_ticks(12500, 2500) == 10.0


def test_fullscreen_detection_matches_monitor_bounds_with_small_tolerance():
    monitor = (0, 0, 1920, 1080)
    assert is_fullscreen_rect((1, 0, 1920, 1079), monitor)
    assert not is_fullscreen_rect((0, 0, 1917, 1080), monitor)
