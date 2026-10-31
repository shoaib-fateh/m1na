from __future__ import annotations

import ctypes
import os
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


def get_system_uptime_seconds() -> float:
    """Return elapsed Windows boot time, including time spent suspended."""
    if sys.platform != "win32":
        raise OSError("Mina's uptime detector is available only on Windows.")
    get_tick_count = ctypes.windll.kernel32.GetTickCount64
    get_tick_count.restype = ctypes.c_ulonglong
    return int(get_tick_count()) / 1000.0


def idle_seconds_from_ticks(current_tick: int, last_input_tick: int) -> float:
    elapsed_ms = (current_tick - last_input_tick) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def is_user_active(max_idle_seconds: float) -> bool:
    return get_idle_seconds() <= max_idle_seconds


def is_fullscreen_rect(
    window_rect: tuple[int, int, int, int],
    monitor_rect: tuple[int, int, int, int],
    tolerance: int = 2,
) -> bool:
    return all(
        abs(window_edge - monitor_edge) <= tolerance
        for window_edge, monitor_edge in zip(window_rect, monitor_rect)
    )


def get_fullscreen_game(excluded_processes: set[str] | None = None) -> str | None:
    """Return the foreground fullscreen app's executable name, if not excluded."""
    if sys.platform != "win32":
        raise OSError("Fullscreen application detection is available only on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hwnd_type = wintypes.HWND
    user32.GetForegroundWindow.restype = hwnd_type
    user32.IsWindowVisible.argtypes = [hwnd_type]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [hwnd_type]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [hwnd_type, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [hwnd_type, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        hwnd_type,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None

    window_rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if not monitor:
        return None

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    monitor_info = MonitorInfo()
    monitor_info.cbSize = ctypes.sizeof(monitor_info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
        raise ctypes.WinError(ctypes.get_last_error())
    bounds = lambda rect: (rect.left, rect.top, rect.right, rect.bottom)
    if not is_fullscreen_rect(bounds(window_rect), bounds(monitor_info.rcMonitor)):
        return None

    process_id = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
        return None
    if int(process_id.value) == os.getpid():
        return None
    process = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return None
    try:
        image_path = ctypes.create_unicode_buffer(32768)
        image_size = wintypes.DWORD(len(image_path))
        if not kernel32.QueryFullProcessImageNameW(
            process, 0, image_path, ctypes.byref(image_size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        name = os.path.splitext(os.path.basename(image_path.value[: image_size.value]))[0]
    finally:
        kernel32.CloseHandle(process)
    excluded = {
        os.path.splitext(item.strip())[0].casefold()
        for item in (excluded_processes or set())
    }
    if name.casefold() in excluded:
        return None
    return name


def get_visible_applications(limit: int = 5) -> list[str]:
    """Return visible foreground applications by executable name, in z-order."""
    if sys.platform != "win32":
        raise OSError("Application detection is available only on Windows.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_query_limited_information = 0x1000
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    foreground = user32.GetForegroundWindow()
    process_id = wintypes.DWORD()
    applications: list[str] = []
    seen: set[str] = set()

    def add_window(hwnd: int) -> None:
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
            return
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return
        if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
            return
        pid = int(process_id.value)
        if pid == os.getpid():
            return
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return
            name = os.path.splitext(os.path.basename(buffer.value[: size.value]))[0]
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                applications.append(name)
        finally:
            kernel32.CloseHandle(handle)

    if foreground:
        add_window(foreground)

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    def visit(hwnd: int, _parameter: int) -> bool:
        if len(applications) < limit:
            add_window(hwnd)
        return len(applications) < limit

    callback = callback_type(visit)
    if len(applications) < limit:
        ctypes.set_last_error(0)
        succeeded = user32.EnumWindows(callback, 0)
        error = ctypes.get_last_error()
        if not succeeded and len(applications) < limit:
            if error:
                raise ctypes.WinError(error)
            raise OSError("Could not enumerate visible application windows.")
    return applications[:limit]
