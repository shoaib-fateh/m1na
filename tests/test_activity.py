from mina.activity import idle_seconds_from_ticks


def test_idle_seconds_handles_gettickcount_wraparound():
    assert idle_seconds_from_ticks(0x1_0000_0005, 0xFFFFFFF5) == 0.016


def test_idle_seconds_from_last_input():
    assert idle_seconds_from_ticks(12500, 2500) == 10.0
