"""Platform backend selection.

``get_platform()`` returns the right :class:`PlatformOps` implementation for the
host OS. Importing the backend modules is deferred until selection so that, for
example, the Windows backend's ``winsound``/``ctypes`` usage is never imported
on Linux and vice versa.
"""
import sys

from .base import PlatformOps


def get_platform():
    """Return a PlatformOps backend for the current operating system."""
    if sys.platform.startswith("win"):
        from .windows import WindowsOps
        return WindowsOps()
    if sys.platform.startswith("linux"):
        from .linux import LinuxOps
        return LinuxOps()
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


__all__ = ["PlatformOps", "get_platform"]
