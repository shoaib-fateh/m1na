import ctypes
import logging
import sys
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _acquire_instance_mutex():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_wchar_p,
    ]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.ReleaseMutex.restype = ctypes.c_bool
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, "Local\\MinaDesktopCompanion")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _release_instance_mutex(handle):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.ReleaseMutex.restype = ctypes.c_bool
    kernel32.ReleaseMutex(handle)
    kernel32.CloseHandle(handle)


def _log_failure() -> None:
    log_path = Path(__file__).resolve().parent / "data" / "mina.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("mina")
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    logger.exception("Mina stopped after an unhandled startup or runtime error.")
    handler.close()
    logger.removeHandler(handler)


def main() -> None:
    if sys.platform != "win32":
        raise OSError("Mina is a Windows desktop companion and requires Windows.")
    instance_mutex = _acquire_instance_mutex()
    if instance_mutex is None:
        return
    try:
        try:
            from mina.app import MinaApp

            MinaApp().run()
        except Exception:
            try:
                _log_failure()
            except OSError:
                pass
            raise
    finally:
        _release_instance_mutex(instance_mutex)


if __name__ == "__main__":
    main()
