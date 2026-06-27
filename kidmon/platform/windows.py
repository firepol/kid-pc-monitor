"""Windows backend for the platform abstraction.

Uses only the standard library (ctypes + winsound + subprocess), so no
third-party Windows package is required. ``psutil`` is used opportunistically
for the foreground process name if it happens to be installed, but the backend
degrades gracefully without it.
"""
import ctypes
import getpass
import logging
import subprocess
import threading

from .base import PlatformOps

logger = logging.getLogger("kidmon.platform.windows")


class WindowsOps(PlatformOps):
    def current_user(self):
        return getpass.getuser()

    def is_locked(self):
        """True if LogonUI.exe is present (the lock/login screen is showing)."""
        try:
            out = subprocess.check_output(
                'tasklist /FI "IMAGENAME eq LogonUI.exe" /NH',
                shell=True, text=True)
            return "LogonUI.exe" in out
        except Exception as e:
            logger.error("is_locked check failed: %s", e)
            return False

    def lock(self):
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            logger.error("lock failed: %s", e)

    def foreground_app(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Window title.
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""

            # Owning process id, then resolve to an executable name.
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process = self._process_name(pid.value)
            return (process, title)
        except Exception as e:
            logger.error("foreground_app failed: %s", e)
            return None

    def _process_name(self, pid):
        if not pid:
            return None
        try:
            import psutil  # optional
            return psutil.Process(pid).name()
        except Exception:
            pass
        # Stdlib fallback: OpenProcess + GetModuleBaseNameW via psapi.
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return None
            try:
                buf = ctypes.create_unicode_buffer(260)
                psapi.GetModuleBaseNameW(handle, None, buf, 260)
                return buf.value or None
            finally:
                kernel32.CloseHandle(handle)
        except Exception as e:
            logger.debug("process name lookup failed for pid %s: %s", pid, e)
            return None

    def play_sound(self, wav_path=None):
        def _play():
            try:
                import winsound
                if wav_path:
                    winsound.PlaySound(
                        wav_path,
                        winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception as e:
                logger.error("play_sound failed: %s", e)

        threading.Thread(target=_play, daemon=True).start()

    def notify(self, title, message):
        def _show():
            try:
                MB_OK = 0x0
                MB_ICONWARNING = 0x30
                MB_TOPMOST = 0x40000
                ctypes.windll.user32.MessageBoxW(
                    0, message, title, MB_OK | MB_ICONWARNING | MB_TOPMOST)
            except Exception as e:
                logger.error("notify failed: %s", e)

        threading.Thread(target=_show, daemon=True).start()
