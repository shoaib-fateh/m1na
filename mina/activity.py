from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> float:
    """Return idle time using only Windows' last-input timestamp."""
    if sys.platform != "win32":
        raise OSError("Mina's activity detector is available only on Windows.")

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()

    get_tick_count = ctypes.windll.kernel32.GetTickCount64
    get_tick_count.restype = ctypes.c_ulonglong
    return idle_seconds_from_ticks(int(get_tick_count()), int(info.dwTime))


def idle_seconds_from_ticks(current_tick: int, last_input_tick: int) -> float:
    elapsed_ms = (current_tick - last_input_tick) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def is_user_active(max_idle_seconds: float) -> bool:
    return get_idle_seconds() <= max_idle_seconds
